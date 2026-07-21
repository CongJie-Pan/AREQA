# PELICAN Learning Engine MVP

## 1. 介紹

PELICAN MVP 是 AREQA 主系統外的一個學習引擎實驗場。它的目的不是做一般聊天問答，而是驗證一套更像「教學策略 engine」的流程：先理解學習者想學什麼、想用什麼角度學、目前背景在哪裡，再把主題轉成可診斷、可補架、可追蹤的知識狀態樹。

目前最穩定的展示主題是 `深度學習`。這個主題有 checked-in catalog skill：`domain_skills/deep_learning.yaml`，可以離線載入、驗證、編譯成 foundation-first 的學習路徑。系統會避免一開始就問 MLP 權重數量、SGD 細節這類過細題目，而是先做 goal/level onboarding，再從較低負荷的概念開始診斷。

目前系統已具備：

- Calibration-first onboarding：先收集 topic、goal/intent、level/background。
- Semantic Intake Classifier：在 LLM 模式下判斷 onboarding 回答是否是 topic revision、一般回答或其他語意訊號；狀態轉移仍由 engine 控制。
- DomainSkill runtime：先找 catalog skill，再找 `data/generated_skills/validated` cache，再做 runtime skill generation/repair，最後才 fallback。
- Skill validation：未通過 schema、graph、remediation、diagnostic safety 檢查的 skill 不會進入診斷。
- Generic domain fallback：已知 domain 但 runtime skill 失敗時，會使用 generic STEM/humanities/business/language skill，而不是直接使用隨機 LLM plan。
- EDF/GUM 模擬層：保留教學策略狀態、direct user evidence、working context count。
- 前端即時狀態顯示：會顯示目前 phase、EDF policy、activity badges 與翻牌動畫。
- Markdown 匯出：可從 UI 匯出目前對話、session metadata、knowledge tree、recent activity。
- 安全 structured logs：terminal 會顯示 safe metadata，例如 skill source、semantic intent、confidence、API health、reason code；不記錄 raw prompt、raw model output 或 API key。

目前仍需注意的限制：

- `domain_skills/` 目前只有 `deep_learning.yaml` 是正式 catalog skill。
- 中國歷史/思想史等主題目前主要依賴 runtime skill generation 或 fallback；若 OpenRouter/Gemini route 失敗，仍會掉回 generic humanities 或 legacy two-node fallback。
- Semantic Intake Classifier 已能處理明確 topic revision，但目前仍可能把 topic refinement/background answer 判成 revision，造成 onboarding 反覆重問 goal/level。
- Domain routing 對中國思想史仍不完整，例如 `諸子百家`、`思想史`、`春秋`、`戰國` 等 alias 尚需補齊，否則可能被判成 `unknown_domain`。
- Runtime-generated skill 成功後會存在 `data/generated_skills/validated/`，不會自動寫入 `domain_skills/`；人工審核後才適合 promote 成 catalog skill。

## 2. 開啟方式

從 repo root 執行：

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python -m pelican_mvp
```

瀏覽器開啟：

```text
http://127.0.0.1:8000
```

`python -m pelican_mvp` 啟動時會嘗試清掉仍占用同一 host/port 的舊 PELICAN MVP server process。如果不想自動清理，可以使用：

```bash
python -m pelican_mvp --no-cleanup-stale-server
```

常用檢查：

```bash
python -m pelican_mvp --help
python -m pytest -q
```

預設可離線執行。離線時仍可使用 checked-in catalog skill 與 deterministic fallback。若要啟用 OpenRouter-compatible LLM：

```bash
export OPENROUTER_API_KEY=your_key
export PELICAN_STEM_MODEL=openai/gpt-5.5
export PELICAN_HUMANITIES_MODEL=~google/gemini-pro-latest
export PELICAN_BUSINESS_MODEL=~google/gemini-pro-latest
export PELICAN_LANGUAGE_MODEL=~google/gemini-pro-latest
export PELICAN_TUTOR_MODEL=google/gemini-3.1-flash-lite
python -m pelican_mvp
```

相關 model route 行為：

- `PELICAN_TUTOR_MODEL`：onboarding question、tutoring 等 learner-facing turns。
- `PELICAN_SKILL_MODEL`：所有 domain skill generation 的全域 override。
- `PELICAN_STEM_MODEL` / `PELICAN_HUMANITIES_MODEL` / `PELICAN_BUSINESS_MODEL` / `PELICAN_LANGUAGE_MODEL`：各 domain 的 skill generation route。
- `PELICAN_LLM_MODEL`：舊版相容用的全域 override。

Runtime artifacts：

```text
data/generated_skills/validated/   # 已通過 validator 的 runtime-generated skill cache
data/generated_skills/failed/      # 失敗 metadata；只保存 safe reason/status/hash
```

## 3. Mermaid 系統架構圖

```mermaid
flowchart TD
    User["Learner / Browser UI"] --> UI["Static UI\nchat, tree, badges, export"]
    UI --> API["FastAPI server.py\n/api/start /respond /reset /mode /export"]
    API --> Engine["PelicanEngine\ncalibration-first state machine"]

    Engine --> Store["StateStore\nlocal JSON session persistence"]
    Store --> State["SessionState\nphase, intake, plan, transcript,\nEDF snapshot, direct evidence"]

    Engine --> Intake["Onboarding\n topic -> semantic classification -> goal -> level"]
    Intake --> Semantic["Semantic Intake Classifier\nLLM structured JSON + rule fallback"]
    Semantic --> Engine

    Engine --> Planner["LearningPlanner"]
    Planner --> Generator["DomainSkillGenerator"]

    Generator --> Catalog["domain_skills/*.yaml\nreviewed catalog skills"]
    Generator --> Cache["data/generated_skills/validated\nvalidated runtime cache"]
    Generator --> Health["LLM route health check\nsafe api_status/api_error logs"]
    Health --> RuntimeLLM["LlmAdapter\nruntime DomainSkill generation + repair"]
    RuntimeLLM --> Artifacts["data/generated_skills/failed\nsafe failed artifacts"]
    Generator --> Generic["generic_skill.py\nknown-domain fallback skills"]

    Catalog --> Validator["SkillValidator\nschema, graph, remediation,\nanswer-leak checks"]
    Cache --> Validator
    RuntimeLLM --> Validator
    Generic --> Validator

    Validator --> Compiler["SkillCompiler\nDomainSkill + Intake -> LearningPlanSnapshot"]
    Compiler --> Plan["Session-local knowledge tree\nnodes, diagnostics, task steps"]

    Plan --> Engine
    Engine --> Diagnosis["diagnosis.py\nsuccessor-first + remediation signals"]
    Diagnosis --> EDF["EdfSimulator\nlearner_state + strategy"]
    Diagnosis --> Memory["LearningMemorySimulator\ndirect evidence boundary"]
    EDF --> Tutor["tutoring.py\nstrategy selection"]
    Memory --> Tutor
    Tutor --> Engine
    Engine --> API

    subgraph Boundary["AREQA production boundary"]
        Backend["backend/ reference only"]
        Frontend["frontend/ untouched"]
    end
    Boundary -. no runtime import .- Engine
```

## 4. Mermaid 用戶流程圖

```mermaid
flowchart TD
    Start["使用者開啟 MVP"] --> AskTopic["AI: 你想學什麼？"]
    AskTopic --> UserTopic["User: 深度學習 / 中國歷史 / 其他主題"]

    UserTopic --> Resolve["Resolve domain category"]
    Resolve --> AskGoal["AI: 詢問學習目的或切入角度"]
    AskGoal --> UserGoal["User: 目標、方向、或更正主題"]

    UserGoal --> SemanticGoal{"Semantic Intake Classifier"}
    SemanticGoal -- topic_revision --> ReviseTopic["更新 topic\n重跑 domain resolve\n回到 goal question"]
    ReviseTopic --> AskGoal
    SemanticGoal -- normal_answer --> InferIntent["Infer learning intent"]
    InferIntent --> AskLevel["AI: 詢問背景、程度、經驗"]

    AskLevel --> UserLevel["User: 背景、程度、或再次更正主題"]
    UserLevel --> SemanticLevel{"Semantic Intake Classifier"}
    SemanticLevel -- topic_revision --> ReviseTopic
    SemanticLevel -- normal_answer --> CompileStart["Compile learning plan"]

    CompileStart --> SkillRoute{"Skill source selection"}
    SkillRoute -- catalog hit --> CatalogSkill["Load domain_skills/deep_learning.yaml"]
    SkillRoute -- runtime cache hit --> RuntimeCache["Load data/generated_skills/validated"]
    SkillRoute -- LLM available --> Health["Check model route health"]
    Health -- healthy --> RuntimeGen["Generate/repair DomainSkill"]
    Health -- failed --> GenericFallback["Known-domain generic fallback"]
    RuntimeGen -- validated --> SaveCache["Save validated runtime skill"]
    RuntimeGen -- failed --> FailedArtifact["Save failed artifact"]
    FailedArtifact --> GenericFallback
    SkillRoute -- unknown domain --> LegacyFallback["Legacy two-node fallback"]

    CatalogSkill --> Compile["Compile knowledge tree"]
    RuntimeCache --> Compile
    SaveCache --> Compile
    GenericFallback --> Compile
    LegacyFallback --> Compile

    Compile --> Diagnostic["Present first diagnostic"]
    Diagnostic --> Answer{"Learner response"}
    Answer -- correct --> Mastered["Update direct mastered evidence"]
    Answer -- unknown --> Scaffold["Scaffold prerequisite/current concept"]
    Answer -- too_detailed/too_hard --> Recalibrate["Remediate level/scope"]
    Answer -- too_easy --> Accelerate["Accelerate to next concept"]

    Mastered --> EDF["Update EDF/GUM metadata"]
    Scaffold --> EDF
    Recalibrate --> EDF
    Accelerate --> EDF
    EDF --> Continue["Continue diagnosis/tutoring"]
    Continue --> Export["Optional: export Markdown transcript"]
```

## 5. 檔案架構圖

```text
misc/PELICAN_mvp/
├── README.md
├── requirements.txt
├── data/
│   ├── generated_skills/
│   │   ├── validated/                  # runtime-generated skill cache
│   │   └── failed/                     # safe failure metadata
│   └── *.json                          # local learner session state
├── docs/
│   ├── 11211_PELICAN_Personalized_Edu.md
│   ├── 11211_PELICAN_Personalized_Edu.pdf
│   ├── PELICAN_Graph.jpg
│   ├── Qwen_Qwen3_235B_A22B_Instruct_2507_–_API_Quickstart_OpenRouter.md
│   ├── Gemini_3.1_Flash_Lite_-_API_Pricing_&_Providers_OpenRouter.md
│   ├── 2026_07_18_experiment/
│   │   └── PELICAN_Knowledge_Tracing_MVP.md
│   ├── implemenation_plan/
│   │   └── PELICAN_Domain_Skill_Runtime_plan.md
│   └── worklog/
│       └── 2026_07_20/
│           ├── 2026_07_20.md
│           ├── 2026_07_21.md
│           ├── conversation.md
│           └── terminal.md
├── domain_skills/
│   └── deep_learning.yaml              # current reviewed catalog skill
├── pelican_mvp/
│   ├── __init__.py
│   ├── __main__.py                     # CLI entry, stale-server cleanup, safe formatter
│   ├── curriculum.py                   # reviewed fixture curricula
│   ├── diagnosis.py                    # successor-first diagnosis
│   ├── domain_catalog.py               # topic -> domain route
│   ├── domain_skill.py                 # executable skill contract
│   ├── edf_simulator.py                # EDF learner-state simulation
│   ├── engine.py                       # main onboarding/diagnosis/tutoring state machine
│   ├── generic_skill.py                # known-domain fallback skills
│   ├── learning_memory.py              # bounded direct-evidence memory simulator
│   ├── llm.py                          # OpenRouter-compatible LLM adapter
│   ├── models.py                       # serializable state/domain models
│   ├── observability.py                # safe structured logging allow-list
│   ├── planner.py                      # profile-aware plan creation
│   ├── server.py                       # FastAPI API + Markdown export
│   ├── skill_artifacts.py              # validated/failed runtime skill artifacts
│   ├── skill_compiler.py               # DomainSkill -> LearningPlanSnapshot
│   ├── skill_generator.py              # catalog/cache/runtime/generic skill pipeline
│   ├── skill_loader.py                 # catalog skill loader
│   ├── skill_validator.py              # skill safety/shape validator
│   ├── state_store.py                  # local JSON persistence
│   └── tutoring.py                     # tutoring strategy templates
├── static/
│   ├── app.js                          # chat UI, status badges, export action
│   ├── index.html
│   └── styles.css
└── tests/
    ├── test_chinese_history.py
    ├── test_curriculum.py
    ├── test_diagnosis.py
    ├── test_domain_skill.py
    ├── test_e2e.py
    ├── test_edf_simulator.py
    ├── test_engine.py
    ├── test_learning_memory.py
    ├── test_llm.py
    ├── test_main.py
    ├── test_models.py
    ├── test_pedagogical_flow.py
    ├── test_planner.py
    ├── test_server.py
    ├── test_skill_compiler.py
    ├── test_skill_generator.py
    ├── test_skill_loader.py
    ├── test_skill_validator.py
    ├── test_state_store.py
    └── test_tutoring.py
```
