# PELICAN CLI MVP

這是 PELICAN 論文方法的可觀察最小實作，作為獨立的 AI 驅動學習引擎與認知診斷模擬沙盒。

### 工作流程 (Intake-to-Diagnosis Workflow)

1. **Onboarding (意圖收集)**: 引擎啟動後預設進入此階段，等待學習者輸入想學習的主題（例如：「我想了解二元搜尋法」或「SQL Left Join 一直搞混」）。
2. **Dynamic Planning (動態學習地圖)**: 根據學習者的目標，系統會自動生成或回退 (Fallback) 到預設的學習診斷樹 (Learning Plan)。
3. **Diagnosis & Tutoring (診斷與輔導)**: 系統使用 successor-first (後繼者優先) 的方式進行協作式認知診斷，並依學生回應更新知識狀態，最後根據 EDF (Epistemic Development Framework) 狀態與學習記憶 (Learning Memory) 選擇教學策略。

它不會把使用者程度當成已知，也不會在未完成當前知識節點時隨意跳到無關問題。引擎的資料狀態（含 EDF 與 Memory 計數）均不會與主系統產生耦合，為完全獨立的實驗場域。

## Quick Start

```bash
cd misc/PELICAN_mvp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pelican_mvp
```

預設為完全離線、可重現的規則模式 (Deterministic Fallback)。
學習狀態存放於 `data/demo_student.json`，可使用 `reset` 清除以重新啟動 `onboarding` 流程。

### 開發與測試相容性
- **Fixture Curriculum Compatibility**: 為相容先前的回歸測試，直接在 API 傳入 `curriculum_id` (例如 `cnn` 或 `chinese_history`) 即可直接繞過 Onboarding 進入固定課綱診斷。
- **邊界聲明**: 本模組為非正式生產環境之模擬層。所有的 EDF (Epistemic Development Framework) 與 GUM (Generative User Model) 推論皆僅在 `misc/PELICAN_mvp` 內運行，絕對不會影響 `backend/` 主系統的運作。

## CLI Commands

- `tree`: 顯示知識狀態樹。
- `state`: 顯示完整持久化狀態。
- `history`: 顯示每回合的分類與策略。
- `mode rule` / `mode llm`: 切換模式。
- `show answer`: 顯示當前步驟答案，但不會把學生標為已掌握。
- `reset`: 重設目前學習者。
- `quit`: 保存並離開。

## Optional LLM Mode

設定以下環境變數後，以 `mode llm` 切換：

```bash
export OPENROUTER_API_KEY=your_key
export PELICAN_LLM_MODEL=qwen/qwen-2.5-7b-instruct
python -m pelican_mvp --mode llm
```

LLM 模式會執行 Teacher -> Assistant -> Verifier 的診斷題驗證。若 API key 缺失、模型失敗或驗證不通過，系統會安全退回已審核的規則題庫。

## Test

```bash
python -m pytest
python -m pelican_mvp --help
```
