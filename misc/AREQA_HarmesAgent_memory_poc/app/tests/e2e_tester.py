import asyncio
import os
import sys
from dotenv import load_dotenv

# Force utf-8 encoding for stdout on Windows to support emojis
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from app.memory_store import MemoryStore
from app.agent import Agent
from app.background_review import background_worker

async def wait_for_bg(seconds=5):
    print(f"\n--- 等待背景處理 ({seconds} 秒) ---")
    await asyncio.sleep(seconds)

async def main():
    load_dotenv("app/.env")
    if not os.getenv("OPENROUTER_API_KEY"):
        print("請在 .env 檔案中設定 OPENROUTER_API_KEY")
        return

    # 清空現有記憶以確保測試乾淨
    memory_store = MemoryStore()
    memory_store._write_jsonl("user", [])
    memory_store._write_jsonl("memory", [])
    
    from app.agent import _vector_store
    _vector_store.db.close()
    
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memories", "episodic_memory.db")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception as e:
            print(f"Warning: could not remove db {e}")
            
    _vector_store._init_db()

    agent = Agent(memory_store)
    
    # 啟動背景線程
    bg_task = asyncio.create_task(background_worker(memory_store))
    
    print("\n\n=======================================================")
    print("==== 階段三：端到端實境測試 (E2E Efficacy Testing) ====")
    print("=======================================================\n")
    
    # 測試 1: 事實注入
    print(">> Turn 1: 測試事實注入")
    reply = await agent.chat("你好，我是 Alice，我在準備微積分考試。")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    # 新 Agent (模擬重開程式)
    agent = Agent(memory_store)
    print(">> Turn 3: 重新執行，測試持久化")
    reply = await agent.chat("你知道我是誰、我在幹嘛嗎？")
    print(f"Agent: {reply}")
    
    print("\n-------------------------------------------------\n")
    
    # 測試 2: 記憶覆蓋與矛盾解決
    print(">> Turn 1: 寫入喜好")
    reply = await agent.chat("我最喜歡的語言是 Python。")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(">> Turn 2: 改變喜好")
    reply = await agent.chat("我改變主意了，Python 太慢，我現在最愛 Rust。")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(f"\n[目前 USER 記憶內容]:")
    for u in memory_store.get_raw_memories('user'):
        print(f"  - {u}")
    
    print("\n-------------------------------------------------\n")
    
    # 測試 3: 無效資訊過濾測試
    print(">> Turn 1: 閒聊 (測試雜訊過濾)")
    reply = await agent.chat("今天天氣真好，我剛剛吃了一個漢堡。")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(f"\n[目前 MEMORY 內容] (應排除雜訊):")
    for m in memory_store.get_raw_memories('memory'):
        print(f"  - {m}")
        
    print("\n\n=======================================================")
    print("==== 階段四：AREQA 業務場景適配測試 (Domain-Specific Testing) ====")
    print("=======================================================\n")
    
    print(">> Turn 1: 熟練度追蹤")
    reply = await agent.chat("我一直搞不懂餘弦定理公式怎麼背。")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(f"\n[目前 USER 記憶內容] (應紀錄不熟練):")
    for u in memory_store.get_raw_memories('user'):
        print(f"  - {u}")
    
    print("\n-------------------------------------------------\n")
    
    print(">> 模擬手動修改記憶: 寫入已達專家級")
    memory_store.add("user", "該學生的餘弦定理熟練度已達專家級，提示時請給予最精簡的公式，不需解釋基礎概念。")
    
    # 需要先讀取讓快照更新
    memory_store.load_from_disk()
    
    print("\n>> 鷹架消退行為驗證 (期待只回傳公式)")
    reply = await agent.chat("提醒我一下餘弦定理。")
    print(f"Agent: {reply}")
    print("\n\n=======================================================")
    print("==== 階段五：冷熱雙層記憶架構測試 (Bilevel Memory Testing) ====")
    print("=======================================================\n")
    
    print(">> Turn 1: 寫入特定記憶細節")
    reply = await agent.chat("幫我記下來，我國小三年的導師叫張美麗，她非常喜歡吃香蕉。")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(">> Turn 2: 寫入長篇資料之一")
    text_1 = "幫我筆記一段很長的資料：《紅樓夢》又名《石頭記》、《情僧錄》、《風月寶鑑》、《金陵十二釵》。它被認為是中國古典小說的巔峰之作。全書以賈、史、王、薛四大家族的興衰為背景，以富貴雙全的賈寶玉為視角，描繪了一批舉止見識出於鬚眉之上的閨閣佳人。"
    reply = await agent.chat(text_1)
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(">> Turn 3: 寫入長篇資料之二")
    text_2 = "再幫我記一個筆記：林黛玉，字顰顰，原籍姑蘇，是巡鹽御史林如海與賈敏的獨女。林黛玉自幼體弱多病，多愁善感，寄人籬下。她才華橫溢，作詩往往奪魁。她與賈寶玉前世為神瑛侍者與絳珠仙草，有木石前盟之約，因此今生以淚還債。"
    reply = await agent.chat(text_2)
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(">> Turn 4: 寫入長篇資料之三")
    text_3 = "再幫我筆記：關於《紅樓夢》的第五回，這是全書最重要的總綱。賈寶玉在太虛幻境中，看了金陵十二釵的正冊、副冊、又副冊的判詞，並聽了《紅樓夢》十二支曲子。這些判詞和曲子，暗示了書中所有主要女性角色的最終命運。例如黛玉的「玉帶林中掛」、寶釵的「金簪雪裡埋」、王熙鳳的「機關算盡太聰明，反算了卿卿性命」。這一回奠定了小說「千紅一哭，萬艷同悲」的悲劇基調。"
    reply = await agent.chat(text_3)
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(">> Turn 5: 寫入長篇資料之四 (預期這時會擠爆熱記憶並觸發 Compact)")
    text_4 = "再幫我筆記：《紅樓夢》的結局至今仍是文學界爭論不休的話題。前八十回由曹雪芹所作，後四十回一般認為是高鶚或無名氏續寫。在續書中，賈家雖然經歷抄家，但最終「蘭桂齊芳」，賈寶玉中舉後出家，賈府得到復興。然而，根據前八十回的脂批以及各人物的判詞，曹雪芹原本的構想應該是更徹底的悲劇——「落了片白茫茫大地真乾淨」。賈府最終徹底敗落，子孫流散。這種「草蛇灰線，伏脈千里」的寫作手法，使得探尋原意的「紅學」成為專門學問。"
    reply = await agent.chat(text_4)
    print(f"Agent: {reply}")
    await wait_for_bg(10) # 預留較長的時間給 Demote 還有 LLM 壓縮
    
    print("\n>> 模擬重新啟動並提問冷記憶細節")
    agent = Agent(memory_store)
    reply = await agent.chat("請問我小學時喜歡吃香蕉的老師叫什麼名字？")
    print(f"Agent: {reply}")
    await wait_for_bg(6)

    print("\n>> Turn 6: 從冷知識庫中檢索資料，並確保熱記憶不會被覆蓋")
    print(f"\n[目前 USER 記憶內容] (檢索前):")
    user_mems_before = memory_store.get_raw_memories('user')
    for u in user_mems_before:
        print(f"  - {u}")
        
    reply = await agent.chat("再問一次，那位喜歡吃香蕉的老師叫什麼名字？請根據你的長期記憶回答我。")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print(f"\n[目前 USER 記憶內容] (檢索後，應與檢索前相同):")
    user_mems_after = memory_store.get_raw_memories('user')
    for u in user_mems_after:
        print(f"  - {u}")
        
    if user_mems_before == user_mems_after:
        print("\n✅ 測試成功：熱記憶並未被覆蓋！")
    else:
        print("\n❌ 測試失敗：熱記憶發生了變更！")
        
    print("\n>> Turn 7: 測試已被壓縮出熱區、僅存在於冷知識庫的獨有記憶（紅樓夢結局與高鶚）")
    reply = await agent.chat("對了，你可以告訴我《紅樓夢》後半部（後四十回）一般是誰寫的嗎？還有曹雪芹原本設想的結局是什麼？")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    print("\n>> Turn 8: 跨冷熱記憶檢索與整合測試（結合冷記憶的結局作者與熱記憶的導師偏好）")
    reply = await agent.chat("想像一下，如果我國小三年級的導師張美麗去讀了《紅樓夢》的結局，她會看到誰續寫的版本？她一邊讀的時候最可能想吃什麼水果？")
    print(f"Agent: {reply}")
    await wait_for_bg(6)
    
    # 結束前取消背景任務
    bg_task.cancel()
    
if __name__ == "__main__":
    asyncio.run(main())
