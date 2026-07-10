1. [x] 會員功能完成且沒問題
    - [x] docs/worklog/202607/2026_07_07_08.md - 通過第三關、第四關測試
2. [x] 將Compeer 機制開啟，並且改為透過 GUM記憶模塊 記住學生的狀態（例如：知道學生昨天文言文卡很久、心情焦慮），並透過系統的Compeer與mailbox「主動關懷 / 信件功能」，在隔天主動推播訊息或寫信鼓勵學生。這種「非同步的關懷感」是其他對話框產品完全做不到的。
3. [x] 改優化logo與icon
4. [x] mailbox 資料持久化與可靠性調整：信件本體不要只存 Redis，應改為以 Supabase/Postgres 作為 source of truth，Redis 只保留快取與 delayed queue；這樣即使 Redis 清除、過期或重啟，使用者信件也不會遺失。
5. (選擇性) 系統 agentic 化 : docs/tech_docs/implementation_plan/multi_agent_implementation_plan.md
6. 將網站新增英文語言選項，並且可以按照GPS，然自動切換語言。
7. 建立實際系統使用案例，並拍成影片。(英文為主)
8. 建立並修改intro Page : docs/tech_docs/implementation_plan/introPage_implementationPlan.md。如ChatGPT產出的模板 : misc/AREQA-Landing-Template
