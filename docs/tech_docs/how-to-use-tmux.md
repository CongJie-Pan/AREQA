## Codespace 的完整 Tmux 流程

以下是從安裝、使用到刪除的正規完整流程，專為在背景跑長時間任務所設計。

### 1. 安裝 Tmux
在 Codespace 的終端機（通常是 Ubuntu/Debian 基礎）中執行以下指令進行安裝 ： [pengfeixc](https://pengfeixc.com/blogs/developer-handbook/tmux.html)
```bash
sudo apt-get update
sudo apt-get install -y tmux
```

### 2. 建立並進入會話
為您的 AI 任務建立一個專屬名稱的會話（例如命名為 `ai_task`），這樣比較好管理 ： [blog.csdn](https://blog.csdn.net/m0_67165162/article/details/149124187)
```bash
tmux new -s ai_task
```
執行此指令後，畫面底部會出現一條綠色的狀態列，代表您已經在 Tmux 的環境內了 。這時您就可以啟動 Codex 並下達需要長時間執行的指令。 [blog.jks](https://blog.jks.coffee/5-min-hands-on-linux-tmux-multiplexer-tutorial/)

### 3. 分離會話（Detach）
當 Codex 開始工作後，若您想離開終端機去忙別的事或關機，請不要直接按 `Ctrl+C`。您需要將這個會話丟到背景執行 ： [blog.csdn](https://blog.csdn.net/m0_67165162/article/details/149124187)
1. 先按下 **`Ctrl + b`**。
2. 放開雙手。
3. 單獨按下 **`d`**。
此時終端機會顯示 `[detached (from session ai_task)]`，代表任務已在背景繼續運作，您現在可以安全地關閉 VSCode 或將電腦關機了 。 [blog.csdn](https://blog.csdn.net/m0_67165162/article/details/149124187)

### 4. 重新連接會話（Attach）
當您重開機回到 Codespace 時，若要查看 AI 的進度，請先列出目前所有在背景跑的會話 ： [blog.jks](https://blog.jks.coffee/5-min-hands-on-linux-tmux-multiplexer-tutorial/)
```bash
tmux ls
```
確認 `ai_task` 還在後，執行以下指令接回原本的畫面 ： [blog.csdn](https://blog.csdn.net/m0_67165162/article/details/149124187)
```bash
tmux attach -t ai_task
```

### 5. 結束與刪除會話
當 AI 任務完成，或者您想強制終止任務時，有兩種作法可以完全刪除這個會話：
- **在會話內部刪除：** 當您處於 Tmux 畫面內時，直接輸入 `exit` 或按下 `Ctrl+d` 即可關閉並刪除當前會話 。 [blog.jks](https://blog.jks.coffee/5-min-hands-on-linux-tmux-multiplexer-tutorial/)
- **在會話外部刪除：** 如果您已經 detach 出來，不想進去畫面就直接刪除，可以執行 ： [blog.csdn](https://blog.csdn.net/m0_67165162/article/details/149124187)
```bash
tmux kill-session -t ai_task
```
若想一次刪除所有背景的 Tmux 會話（當環境變得很亂時），可以使用：
```bash
tmux kill-server
```

您有需要在 Codex 完成任務後，透過 Gmail MCP 觸發什麼特定的通知格式嗎？例如包含錯誤日誌或是測試報告？