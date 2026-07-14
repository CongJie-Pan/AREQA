# PELICAN CLI MVP

這是 PELICAN 論文方法的可觀察最小實作，使用論文中的集合與不等式題：

```text
A = {x ∈ R | |x - 1| ≤ 2}
B = {x ∈ Z | √x ≤ 4}
Find A ∩ B
```

它先用 successor-first 進行協作式認知診斷，再依學生回應更新知識狀態，最後以快/慢思考選擇教學策略。它不會把使用者程度當成已知，也不會在未完成當前知識節點時隨意跳到無關問題。

## Quick Start

```bash
cd misc/PELICAN_mvp
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pelican_mvp
```

預設為完全離線、可重現的規則模式。學習狀態存放於 `data/demo_student.json`，可使用 `reset` 清除。

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
