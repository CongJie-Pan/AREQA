import json
from typing import List, Dict
from openai import AsyncOpenAI
import os
from app.memory_store import MemoryStore
from app.prompt_builder import build_system_prompt, BASE_SYSTEM_PROMPT
from app.background_review import add_to_review_queue, compact_memory
from app.vector_store import VectorStore

_vector_store = VectorStore()

MODEL = "qwen/qwen3-235b-a22b-2507"

def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_memory",
            "description": "主動新增記憶到 USER 或 MEMORY 中。適用於使用者明確要求記錄偏好或事實時。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["user", "memory"]},
                    "content": {"type": "string", "description": "要新增的記憶內容。"}
                },
                "required": ["target", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_memory",
            "description": "更新或修改已存在的記憶。適用於使用者指正、修改舊有記憶時。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["user", "memory"]},
                    "old_text": {"type": "string", "description": "現有記憶中，能唯一識別要被替換段落的關鍵字或句子。"},
                    "new_content": {"type": "string", "description": "要替換成的新記憶內容。"}
                },
                "required": ["target", "old_text", "new_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_memory",
            "description": "刪除已存在的記憶。適用於使用者要求忘記、刪除特定筆記或偏好時。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["user", "memory"]},
                    "old_text": {"type": "string", "description": "現有記憶中，能識別要被刪除段落的關鍵字或句子。"}
                },
                "required": ["target", "old_text"]
            }
        }
    }
]

class Agent:
    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store
        self.chat_history: List[Dict] = []
        self.client = get_client()

    async def chat(self, user_input: str) -> str:
        # 1. 載入最新的快照 (這樣每次對話都能拿到背景線程更新後的最新記憶)
        self.memory_store.load_from_disk()
        user_snapshot = self.memory_store.get_snapshot("user")
        memory_snapshot = self.memory_store.get_snapshot("memory")
        
        # 印出目前熱記憶快照狀態，讓使用者一目了然
        print(f"\n[Hot Memory Status] 目前載入的熱記憶快照：")
        print(f"  - USER PROFILE: {len(user_snapshot)} 字元")
        if user_snapshot:
            for line in user_snapshot.split('\n'):
                if line.strip() and not line.startswith('#'):
                    print(f"    {line.strip()}")
        print(f"  - MEMORY: {len(memory_snapshot)} 字元")
        if memory_snapshot:
            for line in memory_snapshot.split('\n'):
                if line.strip() and not line.startswith('#'):
                    print(f"    {line.strip()}")
        
        # 2. 檢索冷記憶 (Cold Memory)
        cold_memories = _vector_store.search_cold_memory(user_input, top_k=3)
        if cold_memories:
            print(f"\n[Cold Memory Retrieval] 成功從 SQLite 向量庫喚醒 {len(cold_memories)} 筆長期記憶！")
            retrieved_text = "\n".join([f"- {m}" for m in cold_memories])
            memory_snapshot += f"\n\n# RETRIEVED LONG-TERM MEMORIES\n{retrieved_text}"
            
        # 3. 構建 System Prompt
        system_prompt = build_system_prompt(BASE_SYSTEM_PROMPT, user_snapshot, memory_snapshot)
        
        # 準備送給 API 的訊息
        api_messages = [{"role": "system", "content": system_prompt}] + self.chat_history + [{"role": "user", "content": user_input}]
        
        # 3. 呼叫前台 LLM
        response = await self.client.chat.completions.create(
            model=MODEL,
            messages=api_messages,
            tools=TOOLS,
            tool_choice="auto"
        )
        
        message = response.choices[0].message
        
        # 處理 Tool Call (前台主動記憶)
        if message.tool_calls:
            api_messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": t.id,
                        "type": t.type,
                        "function": {
                            "name": t.function.name,
                            "arguments": t.function.arguments
                        }
                    } for t in message.tool_calls
                ]
            })
            
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                target = args.get("target")
                
                tool_res_msg = "已成功紀錄該資訊。"
                if func_name == "add_memory":
                    content = args.get("content")
                    print(f"\n[Foreground Tool] LLM 主動呼叫新增記憶到 {target}: {content}")
                    res = self.memory_store.add(target, content)
                    if not res["success"]:
                        if "Memory full" in res.get("error", ""):
                            print(f"[Foreground Tool] 容量已滿，交由背景 Compact 處理...")
                            await compact_memory(target, content, self.memory_store)
                            tool_res_msg = "系統偵測到記憶空間已滿，已自動在背景進行壓縮與整合！"
                        else:
                            tool_res_msg = f"新增記憶失敗：{res.get('error')}"
                            
                elif func_name == "replace_memory":
                    old_text = args.get("old_text")
                    new_content = args.get("new_content")
                    print(f"\n[Foreground Tool] LLM 主動呼叫修改 {target} 中的 '{old_text}' 為 '{new_content}'")
                    res = self.memory_store.replace(target, old_text, new_content)
                    if not res["success"]:
                        tool_res_msg = f"修改記憶失敗：{res.get('error')}"
                        if "Memory full" in res.get("error", ""):
                            print(f"[Foreground Tool] 容量已滿，交由背景 Compact 處理...")
                            await compact_memory(target, new_content, self.memory_store)
                            tool_res_msg = "系統偵測到記憶空間已滿，已自動在背景進行壓縮與整合！"
                            
                elif func_name == "remove_memory":
                    old_text = args.get("old_text")
                    print(f"\n[Foreground Tool] LLM 主動呼叫刪除 {target} 中的 '{old_text}'")
                    res = self.memory_store.remove(target, old_text)
                    if not res["success"]:
                        tool_res_msg = f"刪除記憶失敗：{res.get('error')}"
                        
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": tool_res_msg
                })
                
            # 將工具執行結果回傳給 LLM，強制它產生自然語言回答
            response2 = await self.client.chat.completions.create(
                model=MODEL,
                messages=api_messages
            )
            reply = response2.choices[0].message.content
        else:
            reply = message.content
            
        # 4. 更新歷史與派生背景任務
        self.chat_history.append({"role": "user", "content": user_input})
        self.chat_history.append({"role": "assistant", "content": reply})
        
        # 將最新的對話推入背景審查佇列
        await add_to_review_queue([{"role": "user", "content": user_input}, {"role": "assistant", "content": reply}])
        
        return reply
