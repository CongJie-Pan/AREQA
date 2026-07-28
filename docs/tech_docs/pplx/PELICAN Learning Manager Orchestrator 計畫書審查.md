此計畫將 PELICAN 從固定六階段管線改為「orchestrator 提案 + engine 驗證裁決」的架構，整體設計方向正確（單一狀態擁有者、bounded proposal、deterministic fallback），但仍有多處常見 agent/orchestration 實作坑位需要在 Phase 2-4 落地前補強。以下依照計畫的四個 Phase 逐一比對業界已知的 orchestration 失敗模式進行審查。

## 整體架構評估

計畫採用「centralized orchestration」而非「choreography」，這在需要單一真相來源、可回溯、規則穩定的教學系統中是正確選擇，因為集中式協調在可觀測性與回滾能力上明顯優於事件驅動式的多代理協作。研究顯示，缺乏正式 orchestration 框架的多代理系統在生產環境中失敗率可達 41%–86.7%，而本計畫已經在架構上刻意避免「orchestrator 直接改狀態」這一類常見錯誤，值得肯定。但 LangChain/CrewAI 等框架的實證研究指出，逾半數的 bug 集中在「Self-Action」階段（API 誤用、契約不一致、序列化錯誤），這正好對應本計畫 Phase 2-3 的「LLM 提案 → 本地驗證 → engine 執行」鏈路，是本計畫風險最高的環節。[^1][^2][^3]

## Phase 1 模型路由：隱藏風險

Phase 1 把 tutor 與 orchestrator 路由同時預設指向同一個模型 slug（`google/gemini-3.5-flash-lite`），計畫本身也承認若 OpenRouter 對此模型的 `response_format=json_schema` 支援不穩定，需要 fallback 到 JSON-object prompting。這類「structured output 相容性」問題在實務上是常見地雷——多個實測案例顯示，將自由文字輸出改為嚴格 structured JSON 幾乎能消除大部分的解析錯誤，但前提是必須做「live health check」而非假設模型永遠支援。目前計畫把這個驗證動作放在 Phase 4 才「remaining deployment decisions」提及，建議提前到 Phase 1 或 Phase 2 就做一次自動化探測，否則 orchestrator 在生產環境可能會靜默降級成規則式 fallback，卻沒有任何告警。[^4]

## Phase 2 Decision Schema：核心坑位

這是整個計畫最容易出 bug 的地方，因為它涉及「LLM 提案 + 本地驗證 + 確定性 fallback」三段式邏輯，正是實證研究中「API 誤用 / 契約不一致」高發區。具體風險點：[^1]

- **Route 枚舉漂移**：`LearningManagerRoute` 列出 6 種路由（diagnose_answer、clarify_current_prompt 等），但沒有版本化機制。日後若新增路由而 engine 端的 dispatcher 未同步更新合法性檢查，會出現「orchestrator 選了一個 engine 不認得的合法枚舉值」的靜默錯誤——這類「specification 失配」在多代理系統故障中占比約 42%。[^2]
- **Confidence 閾值未定義**：計畫提到 decision 含 confidence，但未說明低信心時的行為（是否強制 fallback、是否要求二次確認）。這是常見的「unclear ownership」問題——誰在信心不足時做最終裁決，若沒有明確的 tiebreaker 邏輯，系統容易卡住或隨機選擇。[^5]
- **Prompt-Schema 耦合**：`orchestrate_turn_decision()` 依賴 strict JSON schema，但測試計畫只覆蓋「valid / invalid / unavailable」三種 payload，沒有覆蓋「schema 驗證通過但語意錯誤」（例如模型回傳合法 enum 卻選錯階段）的情境，這類語意層錯誤是 structured output 驗證無法防止的。
- **Race between proposal and session mutation**：文件強調 orchestrator 不可直接改 SessionState，但沒有描述如果同一 turn 內 engine 因某些例外提前 mutate 狀態（例如 timeout 導致部分寫入），orchestrator 的 decision 是否會基於過期 context 做判斷。分散式系統中「immutable state snapshot + 版本號」是業界推薦的修法，值得在 `LearningManagerTurnContext` 中加入 context 版本戳記。[^3]

## Phase 3 Engine Wiring：契約與回退

Phase 3 把 dispatcher 邏輯放進 `engine.py`，並要求「非法路由被拒絕」，這符合「contract enforcement」的最佳實踐（如 Databricks 案例中「驗證 schema、檢查 agent A output 是否符合 agent B input 契約」）。但幾個潛在盲點：[^3]

- **Legacy fallback 的隱性行為差異**：計畫要求 `fallback_legacy_pipeline` 要「delegate 到現有 phase handler 而不能有行為損失」，但沒有明確的自動化「行為對等測試」（behavioral equivalence test），只靠 Act 03 的單一手動場景驗證，覆蓋率不足以保證真正等價，建議加入 snapshot-diff 測試比對 orchestrator 開/關兩種路徑的輸出。
- **Clarification 路徑的 mastery evidence 洩漏風險**：`clarify_current_prompt` / `interrupt_and_explain` 被要求「不可更新 mastery evidence」，但若這兩條路徑仍然呼叫到會寫入 evidence 的共用函式（例如 `_handle_diagnostic()` 被誤用複用），會產生「shared state 被意外污染」的 bug，這正是多代理系統中最常見的「shared mutable state race」問題之一。務必在單元測試中加入「呼叫次數斷言」（assert mastery-write function 未被呼叫），而非只驗證最終回應文字。[^3]
- **Route 合法性 vs 階段耦合的組合爆炸**：6 種路由 × N 個階段的合法性矩陣未在文件中列出，只描述了 diagnosis/tutoring 兩個階段的映射；onboarding 明確說「先 fallback」，但沒有列出其他階段（如尚未涵蓋的 onboarding 之外階段）default 是否安全，這種「未列舉組合」容易在後續擴充時產生 silent misroute。

## Phase 4 觀測性：延後驗證的風險

把「模型 structured output 相容性驗證」與「orchestrator 是否預設啟用」都推到 Phase 4 才決策，意味著前三個 Phase 的所有測試都是在「假設模型行為穩定」的前提下進行，如果 Phase 4 才發現 Gemini 3.5 Flash Lite 在正式環境不支援 strict schema，前面三個 Phase 的 fallback 路徑可能從未在真實流量下被觸發測試過。日誌事件命名（`pelican_learning_orchestrator_decided/fallback/route_applied`）設計合理，但缺少「same-turn 事件去重」機制——若一次 turn 內因重試導致 decided 事件被觸發兩次，觀測資料會失真，這對應「Memory overwrite / 重複 handshake」這類已知的協調失敗症狀。[^6]

## 跨階段共通性風險總表

| 風險類別 | 對應計畫位置 | 建議緩解措施 |
|---|---|---|
| API/契約不相容（structured output） | Phase 1-2 模型路由與 JSON schema | 提前做 live health check，非到 Phase 4 才驗證[^4] |
| Specification 漂移（route enum 擴充） | Phase 2 decision schema | 為 route enum 建立版本化與 engine 端同步契約測試[^2] |
| 責任不清 / 無 tiebreaker | Phase 2 confidence 未定義行為 | 明訂低信心閾值與強制 fallback 規則[^5] |
| 共享狀態污染 | Phase 3 clarification 路徑誤觸 mastery 寫入 | 用呼叫次數斷言測試取代僅驗證輸出文字[^3] |
| 觀測事件重複/遺漏 | Phase 4 log 事件 | 加入 turn-level idempotency key 防止重複觸發[^6] |
| Self-Action 階段高發 bug | Phase 2-3 執行語意 | 針對 route dispatch 加大測試覆蓋（尤其非法但語意合理的邊界案例）[^1] |

## 是否會衍生後續問題或 bug

會，最可能出現的後續問題集中在三處：一是 Gemini 3.5 Flash Lite 對 strict JSON schema 的相容性若在 Phase 4 才被發現不支援，將導致前三個 Phase 建立的「orchestrator 優先」流程實際上長期跑在 fallback legacy 路徑上，卻沒有明顯告警；二是 route enum 與 engine 端合法性矩陣缺乏正式契約測試，未來新增路由或階段時容易出現 silent misroute，這是實證研究中最大宗的 bug 來源；三是 clarification/interrupt 路徑若共用到會寫入 mastery evidence 的既有函式，會產生難以察覺的資料污染，需要專門的「未呼叫斷言」測試而非只看回應文字是否正確。建議在 Phase 2 結束前先補上模型健康檢查與 route 版本契約測試，再進入 Phase 3 的 engine wiring，可大幅降低後續回歸風險。[^4][^1][^3]

---

## References

1. [Bugs in Modern LLM Agent Frameworks: An Empirical Study](https://arxiv.org/html/2602.21806v2) - Our findings show that agent framework bugs mainly arise from 'API misuse', 'API incompatibility', a...

2. [Why Multi-Agent AI Systems Fail and How to Fix Them](https://galileo.ai/blog/multi-agent-ai-failures-prevention) - Studies document failure rates of 41-86.7% without proper orchestration. State synchronization failu...

3. [From Chaos to Choreography: Multi-Agent Orchestration ...](https://www.youtube.com/watch?v=2czYyrTzILg) - teams build one agent, then five, then drown in coordination problems unrelated to LLMs. Agent hando...

4. [70% of My LangChain Bugs Came From Agents — Not the LLM. Anyone ...](https://www.reddit.com/r/LangChain/comments/1sqrcoj/70_of_my_langchain_bugs_came_from_agents_not_the/) - 70% of My LangChain Bugs Came From Agents — Not the LLM. Anyone Else?

5. [LLM Performance Issues: Orchestration Over Prompts - LinkedIn](https://www.linkedin.com/posts/tandava-appadoo_stop-blaming-the-llm-your-ai-agent-doesnt-activity-7424431496532230144-fj6u) - Stop blaming the LLM. Your AI agent doesn't suck because of the model. It sucks because you can't ar...

6. [# Why Multi-Agent AI Systems Deadlock: Debugging ...](https://psbigbig.medium.com/why-multi-agent-ai-systems-deadlock-debugging-orchestration-failures-in-llm-pipelines-c17b4cbc5393) - When developers experiment with **multi-agent orchestration frameworks** — AutoGen, crewAI, LangChai...

