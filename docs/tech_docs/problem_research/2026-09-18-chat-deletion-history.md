# 單輪刪除與歷史對話研究

日期：2026-09-18。研究基準：`2c39462`。

## Research Question

為何刪除聊天中的一輪問答會殘留無法繼續刪除的用戶 query？開啟或切換歷史對話的卡頓發生在哪一層？

## Observations

- 用戶確認操作是刪除單輪問答，卡頓集中在開啟或切換歷史對話。
- 預期：刪除問答後，重開、切換、同步均不應讓已刪內容復活；殘留的未完成提問應有可用的清理入口。
- 預期：快速依序選 A、B，最終畫面應保持 B，不受 A 較晚完成影響。
- 單輪刪除與一般歷史切換使用前端 Zustand、Dexie/IndexedDB；雲端同步由瀏覽器直接呼叫 Supabase。這些路徑不經 FastAPI。
- 本研究沒有操作正式用戶資料、連線正式資料庫或取得正式瀏覽器效能追蹤，也未驗證雲端部署版本與此提交一致。

## Evidence Map

| 證據 | 來源 | 意義 | 信心 |
|---|---|---|---|
| 本機刪除後逐筆啟動雲端刪除，未等待完成 | `frontend/src/database/repositories/messageRepo.ts:172` | 單輪問答在雲端不是同一個原子刪除操作 | 高 |
| 刪除沒有檢查回傳的 `error` | `frontend/src/services/syncService.ts:439` | 回傳失敗物件時仍正常完成，沒有失敗通知 | 高 |
| 安裝的 PostgREST builder 預設不拋出查詢錯誤 | `frontend/node_modules/@supabase/postgrest-js/src/PostgrestBuilder.ts` | `try/catch` 不足以偵測一般回傳錯誤 | 高，本機套件來源 |
| 同步只 bulkPut，沒有刪除紀錄與刪除合併 | `frontend/src/services/syncService.ts:196` | 過期快照可復活本機已刪訊息；其他裝置刪除不會清掉本機資料 | 高 |
| 僅最後一則 assistant 有刪除入口 | `frontend/src/components/MessageList/index.tsx:480` | 只剩 user 時無法用單輪刪除清理 | 高 |
| 服務也拒絕 user 作為刪除目標 | `frontend/src/services/chat/index.ts:755` | 不只是按鈕缺失，服務契約也限制修復 | 高 |
| 本機持久化失敗被吞掉，仍記錄 deleted | `frontend/src/services/chat/index.ts:804` | UI 成功與真正持久化脫節；`persisted` 僅代表可以持久化 | 高 |
| 切換沒有請求序號或過期結果保護 | `frontend/src/services/chat/index.ts:701` | 較慢舊請求會覆蓋最後一次選擇 | 高 |
| 每次切換載入整段對話並排序 | `frontend/src/database/repositories/messageRepo.ts:85` | 資料量可能增加讀取與排序成本 | 中，未測正式耗時 |
| 訊息一次全部 map 成元件，無列表虛擬化 | `frontend/src/components/MessageList/index.tsx:439` | 長對話首次掛載可能增加 DOM、Markdown 與版面計算成本；MessageItem 已有 memo | 中，未測正式耗時 |
| 啟動後背景查詢所有對話、訊息與筆記，串行執行並比對本機資料 | `frontend/src/services/syncService.ts:65` | 同步可能與本機操作競爭資源；未見分頁或增量游標 | 中，未測正式耗時 |
| 本機先就緒，再啟動雲端同步 | `frontend/src/components/ChatContainer/index.tsx:255` | 不能把全部網路時間直接當作畫面阻塞時間 | 高 |

## Hypotheses

| 假說 | 狀態 | 可否證預測 | 缺少證據 |
|---|---|---|---|
| H1：用戶訊息的雲端刪除失敗，回答刪除成功，下一次同步只帶回 query | Confirmed，隔離重現 | 故障注入後本機先為空，同步後只剩 user | 正式環境當次錯誤與請求紀錄 |
| H2：較晚完成的舊同步覆蓋刪除 | Confirmed，隔離重現 | 雲端刪除成功後，放行舊快照仍恢復本機資料 | 正式事件時序 |
| H3：孤立 user 無單輪刪除入口 | Confirmed，服務測試與 UI 原始碼 | 刪除最新配對後只剩 user，服務拒絕繼續刪 | 未執行正式瀏覽器 UI 重播 |
| H4：快速切換競態導致錯誤回跳 | Confirmed，服務重現 | A 慢、B 快，最後被選中的是 A | 不等同已證明 CPU 卡頓 |
| H5：長對話的全量讀取與渲染造成卡頓 | Plausible | 長對話耗時顯著高於短對話，主執行緒 trace 有對應長任務 | Chrome Performance、React Profiler |
| H6：背景同步放大開啟歷史時的負擔 | Plausible | 同步進行中的操作較同步完成後慢 | 相同資料的對照實驗 |
| H7：FastAPI 是歷史切換的直接等待點 | 此讀取路徑不支持 | 一般切換應出現必要 FastAPI 請求 | 現行路徑沒有；不代表整個後端沒有其他效能問題 |

## Experiments

所有輸入為合成資料，Supabase 以可控替身回傳，使用真實 repository/syncService 與 fake-indexeddb。聊天服務實驗以 store/database 替身隔離時序。

| 實驗 | 假說 | 若成立 | 若不成立 | 結果 |
|---|---|---|---|---|
| E1：只讓 user DELETE 回傳 error | H1 | 同步後只剩 user，錯誤 logger 未被呼叫 | 刪除失敗可見或資料不復活 | 重現 |
| E2：讀取快照後暫停，完成刪除再釋放 | H2 | 雲端空、本機重新出現兩則 | 舊快照被過濾 | 重現，下一次空雲端同步也未修復 |
| E3：模擬另一裝置把雲端刪空 | 同步刪除缺口 | 本機兩則仍在 | 本機同步清除 | 重現 |
| E4：user、user、assistant，刪最後一輪 | H3 | 孤立 user 留下，繼續刪除被拒絕 | 孤立 user 可清理 | 重現 |
| E5：A 讀取阻塞，B 完成後放行 A | H4 | 最後選中 A | 最後仍為 B | 重現 |

實驗來源：`tests/frontend/services/deletion.research.test.ts` 與 `tests/frontend/services/chat/index.test.ts`。
新增實驗是目前缺陷的 characterization，測試通過表示缺陷可重現，不代表修好了。正式修復時應改為期望恢復行為的 regression assertions。

重跑命令：

```bash
npm test --prefix frontend -- tests/frontend/services/deletion.research.test.ts tests/frontend/services/chat/index.test.ts tests/frontend/services/syncService.test.ts tests/frontend/database/messageRepo.sync.test.ts tests/frontend/database/conversationRepo.sync.test.ts
npm run check:report:strict
```

## Findings

5 個檔案、45 個測試通過，其中新增 5 個故障實驗。首次執行有一個實驗斷言錯把 IndexedDB 主鍵回傳順序當作輸入順序；改為無序集合比較後通過，產品程式沒有改動。

`npm run check:report:strict` 的 ESLint 與 TypeScript 均通過；`git diff --check` 通過。未跑完整測試套件或正式瀏覽器效能實驗，沒有觀察到所執行檢查的無關失敗。

既有 repository 測試只驗證雲端刪除函式有被呼叫，syncService 刪除測試只驗證 query filter；沒有證明雲端刪除成功、同步後不復活，或錯誤可傳回 UI。既有聊天測試甚至明確允許本機持久化失敗後仍正常返回。

## Root Cause

單輪刪除的主要缺陷是本機刪除、雲端逐筆刪除、同步合併沒有共同的完成與衝突處理契約。缺少錯誤傳遞、原子批次刪除、持久化刪除紀錄與重試，使部分成功和過期快照都能造成殘留；assistant-only 的操作限制使殘留 user 無法自行清理。

這些機制在目前程式中已確認，但無法從隔離實驗斷言用戶那一次一定是 H1 或 H2。user、user、assistant 的既有歷史也會留下孤立 user，不需要雲端失敗才能觸發。

歷史切換已確認競態缺陷。實際卡頓的耗時比例仍未確認；目前最值得量測的是前端全量讀取、渲染和啟動背景同步，不宜先歸咎模型或 FastAPI。

## Solution Options

1. 刪除一致性修復（優先，中風險）：在現有 repository/syncService 邊界內保存按 user/conversation/message 限定的待刪紀錄；以單一受權限約束的批次刪除完成該輪；驗證錯誤與目標結果、保留可重試狀態；pull 與尚未完成的 push 都須尊重刪除紀錄，防止舊資料復活。影響 messageRepo、syncService、Dexie schema、chat service 與 UI 狀態。回歸測試應涵蓋離線、重開、部分失敗、舊快照、延遲 upsert、多裝置與跨帳戶隔離。不能只加 await 或只檢查 error 就宣稱解決全部問題。
2. 孤立 query 清理（低至中風險）：允許刪除最後一則未配對 user，串流期間禁止誤刪；以明確訊息 ID/輪次範圍限制刪除，不向前吞掉其他提問。影響 MessageList、chat service 與配對測試。完成後既有損壞歷史有可用的修復入口。
3. 歷史切換穩定化與效能量測（低至中風險）：以請求序號丟棄過期 load 結果，讓最新切換擁有 loading 狀態；加入讀取、排序、commit/paint 的分段耗時。根據測量再選增量同步、分頁或虛擬化。影響 chat service、messageRepo、ChatContainer、MessageList。先確保 E5 改為 B 勝出，再量測長短對話。

以上應互補分階段進行。安全日誌只記操作 ID、訊息數、耗時、成功/待重試/失敗、錯誤碼，不記 query、回答、token 或完整資料列。

## Recommended Next Step

先修 E1/E2 的刪除一致性與 E4 的孤立 query 入口，再修 E5。效能方面使用測試帳戶建立 20、200、1000 則合成訊息的對話，保持文字與圖表比例一致，各跑 5 次開啟和 A/B 切換。

操作時記錄 Chrome Performance 與 React Profiler，分別比較啟動同步進行中、同步完成後；固定網路與 CPU 條件。檢視 `chat_history_local_cache_loaded` / `chat_history_cloud_sync_finished`，但這兩個現有事件不能代表逐次切換耗時或保證同步成功。需要補上點選到下一個 paint、Dexie 讀取、React commit、長任務數量及訊息數，才能歸因。只保存合成資料的 trace。

若主要時間在 IndexedDB，優先查詢/分頁；若在 React/Markdown/layout，優先渲染範圍；若只在背景同步期間惡化，再處理同步批次與排程。驗收同時要求最後選擇正確、刪除重試後一致、重開與同步不復活，以及固定測試條件下的延遲改善。

本次研究完成後仍需產品修復與正式環境驗證；清除 Chrome 網站資料不會修復上述契約，也可能把雲端殘留重新下載。
