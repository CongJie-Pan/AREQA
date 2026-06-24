import asyncio
import os
from dotenv import load_dotenv
from app.memory_store import MemoryStore
from app.agent import Agent
from app.background_review import background_worker

async def main():
    load_dotenv("app/.env")
    if not os.getenv("OPENROUTER_API_KEY"):
        print("請在 .env 檔案中設定 OPENROUTER_API_KEY")
        return

    memory_store = MemoryStore()
    agent = Agent(memory_store)
    
    # 啟動背景線程 (防抖與自動記憶抽取)
    bg_task = asyncio.create_task(background_worker(memory_store))
    
    print("===========================================")
    print("Hermes Memory PoC MVP 已啟動！")
    print("設定檔案: app/memories/USER.jsonl, app/memories/MEMORY.jsonl")
    print("輸入 'exit' 或 'quit' 離開。")
    print("===========================================\n")
    
    # 模擬主循環
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ['exit', 'quit']:
                break
            if not user_input.strip():
                continue
                
            reply = await agent.chat(user_input)
            print(f"Agent: {reply}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            
    # 結束前取消背景任務
    bg_task.cancel()
    
if __name__ == "__main__":
    asyncio.run(main())
