# PELICAN CLI MVP

這是 PELICAN 論文方法的可觀察最小實作，作為獨立的 AI 驅動學習引擎與認知診斷模擬沙盒。

### 工作流程 (Intake-to-Diagnosis Workflow)

1. **Onboarding (校準優先意圖收集)**: 引擎預設先問主題，再問學習方向（理解概念、程式實作、做小專案、準備考試/面試），最後問程度與先備經驗。未完成校準前不會進入診斷題。
2. **Domain Skill Runtime (領域教學 Skill)**: 系統先解析或載入結構化 `skill.yaml`，驗證 prerequisite map、calibration、single-concept diagnostics、remediation paths、assessment policy，再編譯成 session-local learning plan。
3. **Diagnosis & Tutoring (診斷與輔導)**: 系統使用 successor-first (後繼者優先) 進行協作式認知診斷，並依學生回應更新知識狀態，最後根據 EDF (Epistemic Development Framework) 狀態與學習記憶 (Learning Memory) 選擇教學策略。

它不會把使用者程度當成已知，也不會在未完成當前知識節點時隨意跳到無關問題。使用者說「太細了」會觸發 scope mismatch 重新校準；說「不知道」會 scaffold prerequisite，而不是跳到另一個隨機診斷題。引擎的資料狀態（含 EDF 與 Memory 計數）均不會與主系統產生耦合，為完全獨立的實驗場域。

### Supported Skill Categories

- STEM conceptual/procedural/programming: 目前內建 `deep_learning.yaml`，其餘 STEM 主題可透過 validated generated skill 或 fallback 流程延伸。
- Humanities/explanatory, business, and language learning: 已有 routing/category contract，完整 approved skill 資產仍是後續工作。
- Legal knowledge is education-only. MVP intake will state that it cannot provide personalized legal advice.

Skill lifecycle labels:

- `runtime_generated`: 模型即時產生但未人工審核。
- `validated_generated`: 通過 schema validator，可在 MVP 中執行。
- `approved`: 未來人工審核或多輪測試後的可重用資產。

## Quick Start

```bash
# 1. 啟動 AREQA 後端虛擬環境
source /workspaces/AREQA/backend/.venv/bin/activate

# 2. 安裝相依套件（若尚未安裝）並啟動伺服器
cd /workspaces/AREQA/misc/PELICAN_mvp
pip install -r requirements.txt
python -m pelican_mvp

# 3. 在瀏覽器開啟 http://127.0.0.1:8000
```

預設為完全離線、可重現的規則模式 (Deterministic Fallback)。若沒有 API key，已存在的 catalog skill 仍可編譯；缺 skill 的主題會走安全 fallback 或要求澄清。
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

LLM 模式會執行 Teacher -> Assistant -> Verifier 的診斷題驗證，也可以在缺 catalog skill 時生成結構化 DomainSkill。模型輸出必須先通過 validator，才會交給 compiler 產生 learning plan；隱藏 reasoning 和 raw model output 不會寫入 state 或 log。若 API key 缺失、模型失敗或驗證不通過，系統會安全退回已審核的規則題庫或 deterministic fallback。

## Test

```bash
python -m pytest
python -m pelican_mvp --help
```
