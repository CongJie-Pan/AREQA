# 在 AREQA 使用 pstack

在新的 Codex 工作階段提出開發需求。根目錄 `AGENTS.md` 會要求非簡單的功能、bug、重構與效能任務使用 pstack，並讀取 [AREQA 開發 playbook](../../.agents/playbooks/areqa-development.md)。一般問答、學術研究與純文件工作沿用原有流程。

## 確認本機安裝

在終端機執行：

```bash
codex plugin list --marketplace pstack-claude
```

確認 `pstack@pstack-claude` 顯示 `installed, enabled`。本次安裝版本為 `0.9.92`。如果外掛尚未安裝，執行：

```bash
codex plugin marketplace add michael-denyer/pstack-claude
codex plugin add pstack@pstack-claude
```

安裝後開啟新的 Codex 工作階段，請代理確認 `poteto-mode` 與 Codex 平台對照文件可讀。正在進行中的對話未必會重新載入技能清單。

外掛與模型設定安裝在目前使用者的 Codex home，預設為 `~/.codex`。這些檔案不在專案 commit 內。其他開發者需各自安裝外掛。

## 交付一個開發任務

可以直接描述問題，或明確指定入口：

```text
使用 pstack poteto-mode 修正以下問題。
重現步驟：［操作步驟］
目前結果：［實際結果］
預期結果：［可觀察的成功條件］
遵守 AREQA 的 AGENTS.md 與專案 playbook，完成驗證後提交。
```

例如：

```text
使用 poteto-mode 調查 Live Tutor 的 avatar 連線失敗後，語音也停止的問題。
先重現並追蹤 fallback，再做最小修正。
驗證 avatar 失敗時仍可使用語音，並顯示 logo。
```

這是需求範例，不代表本次已重現或修正該問題。

要求代理提供失敗與通過的證據。單元測試、整合測試與實際操作的證據要分開列出。涉及前端時仍須執行 `npm run check:report:strict`。

## 單獨使用技能

- 理解程式時，要求「用 pstack how 與 why 解釋這段流程，先不要修改」。
- 修正已知 bug 時，要求「用 pstack tdd，先讓回歸測試因這個 bug 失敗，再修正」。
- 審查改動時，要求「用 pstack interrogate 審查本次 diff，只報告問題」。
- 建立實際操作驗證時，要求「用 create-verification-skill 建立這個功能的專案驗證技能」。

使用自然語言指定名稱即可。技能是否能執行仍取決於目前工作階段提供的工具與權限。

## 檢查角色與路由設定

讀取 Codex home 的 `pstack-models.md`。目前所有角色設定為 `inherit-parent`，`default effort` 設為 `session`。角色設定也寫入同目錄的 `AGENTS.md`，供新工作階段載入。

這些設定讓角色沿用父工作階段的模型與推理設定。多人審查可能有獨立觀點，但相同模型不能宣稱是多模型審查。需要模型多樣性時，重新執行 `setup-pstack`，選擇當時工作階段確實可用的模型。

目前 `session hook: off`。AREQA 透過專案 `AGENTS.md` 路由，避免對其他專案注入全域開發流程。若要啟用全域 hook，使用 `setup-pstack` 開啟，再透過 Codex 的 `/hooks` 完成信任設定。不要手動偽造 hook 信任狀態。

## 驗證 playbook

於專案根目錄執行下列命令。本機安裝位置對應 `0.9.92`，更新後需依外掛清單的版本確認快取路徑：

```bash
node "${CODEX_HOME:-$HOME/.codex}/plugins/cache/pstack-claude/pstack/0.9.92/skills/poteto-mode/scripts/check-playbooks.mjs"
git diff --check
```

成功時，檢查器輸出 `Every project playbook matches this pstack's playbooks.`。更新 pstack 後重新檢查，尤其是未來新增會引用上游步驟的擴充 playbook 時。

開啟新工作階段，要求只讀確認流程：

```text
這是只讀的開發流程檢查。不要修改檔案、提交、開 PR 或派子代理。
確認 pstack 是否可用，讀取 poteto-mode、Codex 對照文件與 AREQA playbook。
假設要修正 avatar 失敗後語音停止的 bug，說明你會採用的流程、
模型設定、測試要求與提交界線，不要開始實作。
```

確認代理選擇專案 playbook，保留語音 fallback 約束，並區分測試通過與獨立審查。沒有獨立 reviewer 時，必要的獨立審查仍屬阻塞，不能用自查替代。

## 在外掛缺少時繼續工作

請代理明確報告 pstack 不可用，改用 `AGENTS.md` 的 Default Implementation Workflow。既有專案技能與品質檢查仍適用。恢復外掛後，重新開啟工作階段並執行上述只讀檢查。
