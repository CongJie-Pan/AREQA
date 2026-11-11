# 首次載入輸入列、sidebar 按鈕與手機金色捲軸調查

日期：2026-11-11。基準 commit：`a40a54b`。本次僅研究，未修改產品程式碼。

## Research Question

為何首頁首次載入時輸入列和 sidebar 按鈕會改變外觀／位置，且手機輸入區疑似短暫出現金色捲軸？

預期：空白首頁在 JavaScript 載入前後維持一致的輸入列幾何、手機導覽位置與使用者主題，空白 textarea 不需要捲軸。

## Observations

使用者回報手機 Safari、Chrome 都會出現。實驗使用本機 Next.js 16.0.7 開發伺服器，Playwright Chromium、WebKit 的乾淨瀏覽器環境；非實體手機。攔住 Next.js JavaScript 請求，擷取伺服器首屏，放行後以 requestAnimationFrame 記錄計算樣式與元素座標。刻意延後 JavaScript 是為隔離階段，時間值不能解讀成正式環境載入效能。

共完成 8 個頁面情境：Chromium 手機／桌面 × 明／暗色 4 組、手機繁中 1 組、320px 手機英文／繁中 2 組、WebKit 390px 手機暗色 1 組。另完成兩個引擎的人工 1px overflow 實驗。

| 量測項目 | JavaScript 載入前 | 載入穩定後 | 結果 |
|---|---|---|---|
| 390px 手機輸入列高度 | 56px | 50px | Chromium、WebKit 一致 |
| 手機輸入列圓角 | 20px | 999px | Chromium、WebKit 一致 |
| 手機輸入列內距 | 10px 14px 8px | 7px 10px | Chromium、WebKit 一致 |
| textarea 字級／行高 | 16px／24px | 15px／22px | Chromium、WebKit 一致 |
| 390px 手機 sidebar 按鈕 x | 228px | 16px | Chromium、WebKit 一致 |
| 1280px 桌面輸入列高度 | 60px | 52px | Chromium 明暗色一致 |
| 已儲存白色主題的輸入列底色 | rgb(36, 36, 36) | rgb(255, 255, 255) | Chromium 手機、桌面一致 |
| 空白 textarea 穩定高度／內容高度 | 22px／22px | 無 overflow | 兩個引擎一致 |

390px 手機輸入列 y 由約 398.7px 變成 444.6px，桌面由 425.9px 變成 483.7px。這個位移同時受空白頁內容／標誌布局影響，不應全歸因於輸入列本身。

## Evidence Map

| 證據 | 來源 | 意義 | 信心 |
|---|---|---|---|
| 首屏與最終圓角、內距、字級不同 | `frontend/src/app/globals.css:596`、`:1094`；`frontend/src/components/ChatInput/styles.ts:14`、`:149` | 全域首屏備援樣式與 antd-style 最終樣式已分歧 | Confirmed |
| 未放行 JavaScript 時即看到舊外形，放行後才改變 | `measurements.json`、probe 首屏／最終截圖 | 此批最終元件樣式並未在首屏生效 | Confirmed |
| SSR 視為桌面，`isOpen=true` | `frontend/src/components/ChatContainer/useSidebarState.ts:11`、`:24` | 首屏輸出 `data-sidebar-open=true` | Confirmed |
| 手機 CSS 仍以 `data-sidebar-open` 定位 | `frontend/src/app/globals.css:216`、`:220`；`frontend/src/components/ChatContainer/index.tsx:694` | 按鈕首屏放在抽屜邊緣，後來才移回左側 | Confirmed |
| 主題屬性只在 effect 寫入 | `frontend/src/contexts/UserPreferencesContext.tsx:1122`；`frontend/src/app/layout.tsx` | 白色主題首次繪製仍採用深色預設值 | Confirmed |
| 儲存繁中時出現 hydration text mismatch | `mobile-zh`、`mobile-narrow-zh` 的 pageerror | SSR 英文與 client 儲存語言不一致，React 重新產生子樹 | Confirmed |
| textarea 為 `overflow-y:auto`，捲軸顏色為 rgb(216,162,92) | `frontend/src/app/globals.css:1119`、`:1134`、`:1146`；兩引擎計算樣式 | 原生捲軸會套用全站金色 | Confirmed |
| 自動高度僅在 value effect 更新 | `frontend/src/components/ChatInput/index.tsx:469` | 字型／樣式／寬度改變不是高度量測的直接依賴 | Plausible contributing factor |

## Hypotheses

| 假設 | 預測與實驗 | 結果 |
|---|---|---|
| H1：首屏 CSS 與最終元件 CSS 不一致造成輸入列變形 | 攔住 JavaScript 時維持備援外形，放行後改成最終外形 | Confirmed；兩個引擎皆符合 |
| H2：手機導覽首屏使用桌面可見狀態定位 | 手機首屏 x=抽屜寬度−52px，hydration 後 x=16px | Confirmed；390px 為 228→16，320px 為 220→16 |
| H3：主題與語言的瀏覽器偏好只在 client 可用，造成額外切換 | 白色偏好先深後淺；繁中偏好與 SSR 英文衝突 | Confirmed；繁中 2 次皆記錄到 hydration 例外 |
| H4：短暫 textarea overflow 觸發金色捲軸 | 自然載入期間出現 scrollHeight > clientHeight，並在實際畫面出現線條 | 未確認；自然空白載入樣本未捕捉到 overflow 或金色線 |
| H5：僅某一瀏覽器引擎問題 | 另一引擎不會發生同一布局切換 | 對布局切換已 Falsified；Chromium、WebKit 一致 |

## Experiments

1. **JavaScript 階段隔離**：先取得首屏截圖與計算樣式，放行腳本後採樣 2.2 秒。確認 H1、H2，並觀察白色主題切換。
2. **語言變因**：相同路由與暗色主題，改用 `zh-TW`。390px 與 320px 都收到 `Hydration failed because the server rendered text didn't match the client`。英文對照未記錄到此 pageerror；沒有將未收集的 console 訊息宣稱為不存在。
3. **引擎變因**：WebKit 390×844 重現相同首屏／最終幾何。WebKit 首屏截圖原先等待字型逾時；以 `PW_TEST_SCREENSHOT_NO_FONTS_READY=1` 略過截圖的字型等待後完成，不代表字型載入時間已被量測。
4. **人工 1px overflow**：只在瀏覽器記憶體中，將穩定 textarea 從 22px 改成 21px，並解除 min-height；兩引擎皆量到內容 22px、可用高度 21px，`overflow-y:auto`、金色 scrollbar-color。改 `overflow-y:hidden` 後計算樣式確實改變。**這是觸發條件實驗，不是自然載入時金色線條的重現；截圖亦未提供可辨識的金色 thumb 證據。**
5. **既有測試**：執行 `mobileViewportStyles.test.ts`、`sidebarState.test.tsx`、`lightThemeSurfaces.test.ts`，共 16 項通過。這些測試檢查字串、hook 狀態及主題 token，沒有比較 SSR 首屏與 hydration 後的瀏覽器幾何，因此未攔下本次問題。

完整採樣與錯誤在 [measurements.json](./measurements.json)。首屏／最終截圖存於未提交的 `.audit/initial-render-research/`。

重跑主要實驗：

```bash
# Terminal 1, repository root
npm --prefix frontend run dev -- --port 3005

# Terminal 2, repository root
PW_TEST_SCREENSHOT_NO_FONTS_READY=1 node docs/experiments/2026-11-11-initial-render/probe.cjs

# Focused existing tests
cd frontend
npm test -- ../tests/frontend/components/ChatContainer/mobileViewportStyles.test.ts ../tests/frontend/components/ChatContainer/sidebarState.test.tsx ../tests/frontend/components/lightThemeSurfaces.test.ts
```

probe 預設重跑明暗主題與 WebKit 共 5 組；繁中／窄螢幕情境可透過匯出的 `run(browserType, label, viewport, theme, language)` 重跑。人工 overflow 是獨立的瀏覽器內樣式實驗，數據保留於 measurements.json。

## Findings And Root Cause

已確認三個可疊加的機制：

1. `globals.css` 保留舊版輸入列布局，`ChatInput/styles.ts` 使用新版膠囊布局。相同元素在不同載入階段採用不同規格。空白內容區亦有 `18vh` 與 `clamp(64px, 14vh, 168px)` 的差異，會額外改變位置。
2. sidebar 圖示已用媒體查詢搭配獨立的 mobile/desktop flags，但浮動容器位置仍依賴混合後的 `sidebarOpen`。伺服器快照固定回傳非手機，因此手機初始位置錯誤；client 知道 viewport 後才更正。
3. 主題與語言在 server 和 client 的首次值不同，且主題 DOM 屬性等到 effect 才寫入。白色主題因此出現深色首屏；儲存繁中則另造成 hydration 重建。React 要求首次 client 輸出與 server HTML 一致，否則可能重新產生子樹，見 [hydrateRoot 官方說明](https://react.dev/reference/react-dom/client/hydrateRoot)。

金色來自全域 scrollbar 設定可以確認，但使用者所見線條是否確為 textarea 捲軸、自然載入時為何溢位，仍需實體手機首屏錄影／逐幀 trace 確認。人工少 1px 實驗只能證明可能機制，不能證明原始根因。全域 `scrollbar-color` 本身會影響捲動區域，見 [MDN scrollbar-color](https://developer.mozilla.org/en-US/docs/Web/CSS/scrollbar-color)。

未修改或驗證正式環境 build；開發環境的 HMR、字型／資源時間可能放大觀察窗口。未將本機時間推廣為正式環境閃動時長，也未認定這些變化全部都會「改回」；本次確認的是首屏與穩定畫面不一致。

## Solution Options

| 方案 | 變更邊界 | 預期效果與風險 | 必要回歸驗證 |
|---|---|---|---|
| A：統一首屏與最終布局來源，補正手機定位 | `globals.css`、`ChatInput/styles.ts`、`ChatContainer/styles.ts`、`ChatContainer/index.tsx` | 最小修正應優先使用一份關鍵布局 CSS；手機位置依獨立 mobile flag。低至中風險，需涵蓋附件與展開狀態 | 腳本延遲下輸入列尺寸／按鈕 x 不變；320/390px 與桌面，抽屜開關、桌面收合 |
| B：使偏好初始化與 SSR 相容 | `UserPreferencesContext.tsx`、`app/layout.tsx`，可能包含服務端可讀的偏好持久化邊界 | 首屏主題要在繪製前決定；React 首次語言／主題快照必須一致。中風險，不能只加 suppressHydrationWarning | light/dark/system、繁中／簡中／英文、storage 拒絕、系統主題變更；無 hydration mismatch |
| C：限定 textarea 的 overflow 與重測時機 | `ChatInput/index.tsx`、相應 CSS | 在內容未達高度上限時避免內部捲軸；達到 200px 時保留可捲動；重測涵蓋字型／寬度／輸入。需先取得自然載入溢位證據，避免掩蓋問題 | 空白／單行無捲軸，多行及達上限仍可捲動，旋轉螢幕、字型變更、鍵盤、IME |

## Recommended Next Step

先實作 A，並用本次 probe 做修正前後比較；B 為獨立但相關的偏好初始化修正。C 先在實體 Safari／Chrome 擷取首次出現線條時的 textarea 尺寸、scrollHeight、clientHeight、scrollTop、字型與 viewport，確認後再決定 overflow 策略。不要直接把全站捲軸隱藏，或以 hydration 警告抑制代替資料一致性修正。
