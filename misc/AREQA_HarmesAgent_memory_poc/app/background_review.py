import asyncio
import os
import json
from typing import List, Dict
from openai import AsyncOpenAI
from app.memory_store import MemoryStore
from app.vector_store import VectorStore

_vector_store = VectorStore()

MODEL = "qwen/qwen3-235b-a22b-2507"

review_queue = []
last_added_time = 0.0

def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

async def add_to_review_queue(messages: List[Dict]):
    global last_added_time
    review_queue.extend(messages)
    last_added_time = asyncio.get_event_loop().time()

async def background_worker(memory_store: MemoryStore):
    global review_queue, last_added_time
    while True:
        await asyncio.sleep(1)
        if not review_queue:
            continue
            
        current_time = asyncio.get_event_loop().time()
        # 防抖：等待 3 秒鐘內沒有新訊息才執行
        if current_time - last_added_time >= 3:
            messages_to_process = review_queue.copy()
            review_queue.clear()
            print(f"\n[Background Worker] Processing {len(messages_to_process)} queued messages for memory extraction...")
            await process_memories(messages_to_process, memory_store)

async def process_memories(messages: List[Dict], memory_store: MemoryStore):
    chat_history = ""
    for m in messages:
        chat_history += f"{m['role']}: {m['content']}\n"
        
    prompt = f"""
請分析以下的對話紀錄與當前記憶，判斷是否需要新增、修改或刪除任何具有「長期價值」的使用者偏好、學習狀態或核心事實。

如果有，請以 JSON 格式回傳，格式如下：
{{
  "memories": [
    {{"action": "add", "target": "user", "content": "使用者正在研究紅樓夢前八十回"}},
    {{"action": "replace", "target": "user", "old_content": "最喜歡林黛玉", "content": "最喜歡薛寶釵"}},
    {{"action": "remove", "target": "memory", "old_content": "提醒我明天去買牛奶"}}
  ]
}}
如果沒有，或是內容屬於短暫閒聊，請直接回傳 {{"memories": []}}。

⚠️【極度重要：雜訊過濾與拒絕閒聊原則】⚠️
絕對禁止記錄以下內容，若遇到請一律忽略：
1. 短暫狀態與日常閒聊（例如：「今天天氣真好」、「我剛吃了一個漢堡」、「我現在有點累」、「早安」）。
2. 沒有長期追蹤價值的流水帳。
3. 已經存在且語意重複的記憶。
只有當資訊對於「未來的長期互動」或「了解使用者核心特質（如：學習進度、熟練度、長期喜好、身份背景）」有幫助時，才允許執行記憶操作。

注意：
1. 'action' 必須是 'add', 'replace' 或 'remove'。
2. 'target' 只能是 'user' (用於個人檔案、熟練度追蹤等) 或 'memory' (用於重要筆記、長期任務等)。
3. 若執行 'replace' 或 'remove'，必須提供 'old_content' (要被替換或刪除的原始文字)。

目前的 USER 記憶：
{memory_store.get_raw_memories("user")}

目前的 MEMORY 記憶：
{memory_store.get_raw_memories("memory")}

對話紀錄：
{chat_history}
"""
    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            content = content.replace("```json", "").replace("```", "").strip()
            result = json.loads(content)
        
        for mem in result.get("memories", []):
            action = mem.get("action", "add")
            target = mem.get("target")
            content = mem.get("content")
            old_content = mem.get("old_content")
            
            if target in ["user", "memory"]:
                res = {"success": False, "error": "Unknown action"}
                if action == "add" and content:
                    print(f"[Background Review] 嘗試新增記憶到 {target}: {content}")
                    res = memory_store.add(target, content)
                elif action == "replace" and content and old_content:
                    print(f"[Background Review] 嘗試替換記憶 {target}: '{old_content}' -> '{content}'")
                    res = memory_store.replace(target, old_content, content)
                elif action == "remove" and old_content:
                    print(f"[Background Review] 嘗試刪除記憶 {target}: '{old_content}'")
                    res = memory_store.remove(target, old_content)
                
                if not res.get("success") and "Memory full" in res.get("error", ""):
                    print(f"[Background Review] {target} 容量已滿。觸發 Compact...")
                    await compact_memory(target, content, memory_store)
                elif res.get("success"):
                    print(f"[Background Review] 成功執行 {action} 於 {target}.")
                    
    except Exception as e:
        print(f"[Background Review] Error: {e}")

async def compact_memory(target: str, new_content: str, memory_store: MemoryStore):
    current_memories = memory_store.get_raw_memories(target)
    limit = memory_store.memory_char_limit if target == "memory" else memory_store.user_char_limit
    
    # [DEMOTE]: Backup the full details of current memories and the overflowing new memory into Cold Storage
    print(f"[Compact] Demoting details to Cold Memory for {target} before compression...")
    for m in current_memories:
        _vector_store.demote_to_cold_memory(target, m)
    if new_content:
        _vector_store.demote_to_cold_memory(target, new_content)
    
    prompt = f"""
以下是目前的記憶清單，以及一條嘗試加入但因為超出容量限制而被拒絕的新記憶。
目前的總字元上限為 {limit} 字元。
請將這些記憶進行摘要、壓縮與整合，極度精簡，去除所有冗餘的形容詞與重複資訊。
請確保所有內容加起來的總字數「絕對不能超過 {limit - 50} 字元」。
請以 JSON 格式回傳一個數量更少、字數更精簡的新記憶清單，格式如下：
{{
  "compacted_memories": [
    "極度濃縮後的記憶 1",
    "極度濃縮後的記憶 2"
  ]
}}

目前的記憶：
{current_memories}

新加入的記憶：
{new_content}
"""
    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            content = content.replace("```json", "").replace("```", "").strip()
            result = json.loads(content)

        compacted = result.get("compacted_memories", [])
        if compacted:
            res = memory_store.overwrite_memories(target, compacted)
            if res["success"]:
                print(f"[Compact] Successfully compacted memory for {target}.")
            else:
                print(f"[Compact] Compact failed: {res.get('error')}")
    except Exception as e:
        print(f"[Compact] Error: {e}")
