# 🌸 XiaoHong Ancient Chinese QA System (小紅古典文學問答系統)

XiaoHong is a specialized Question-Answering system for Classical Chinese Literature (with a focus on *Dream of the Red Chamber*) and general Sinology. It implements a **Retrieval-Augmented Double Instruction Tuning (RADIT)** architecture to bridge the gap between vernacular questions and classical Chinese knowledge.

## 🏗️ Architecture Overview

The system is split into three main layers:

1.  **Frontend (Next.js):** A modern chat interface supporting streaming responses, thinking process visualization (CoT), and interactive citation cards.
2.  **Backend (FastAPI):** A microservice that orchestrates the RAG pipeline and manages LLM inference via Hugging Face Endpoints.
3.  **Core RAG Service (Python):** A hybrid retrieval engine combining:
    *   **Dense Search:** FAISS index with `Qwen3-Embedding-0.6B`.
    *   **Sparse Search:** `rank-bm25` optimized for classical Chinese (custom $k_1$ and $b$ parameters).
    *   **Fusion:** Reciprocal Rank Fusion (RRF) and Cross-Encoder Reranking.
    *   **Gatekeeper:** A two-layer intelligent routing system using `Qwen3.5-0.8B` (via DeepInfra) for Out-of-Domain (OOD) detection and Rerank score thresholding for fallback refusal.
    *   **Safeguards:** Prompt injection sanitization and "Refusal to Answer" for hallucination prevention.

## 🚀 Key Technologies

*   **LLM:** `XiaoHong-v1` (Fine-tuned `Qwen3-8B` via QLoRA 4-bit).
*   **Frontend:** Next.js 15+, React 19, Ant Design, Zustand (State), Dexie (IndexedDB), Framer Motion.
*   **Backend:** FastAPI, Pydantic, OpenAI SDK (Async).
*   **Search/Data:** FAISS, rank-bm25, Jieba (Tokenization), Transformers.

## 📂 Directory Structure

```text
XiaoHong_RedChamber_QA_System/
├── backend/               # FastAPI Server (main.py, requirements.txt)
├── frontend/              # Next.js Application (src/, package.json)
│   ├── src/app/           # Next.js App Router (API routes & Pages)
│   ├── src/services/      # API communication & stream parsing
│   ├── src/store/         # Zustand stores (Chat, Conversation)
│   └── src/database/      # Dexie schema & repositories
├── src/main/python/       # Core Logic
│   └── services/          # RAG pipeline, BM25 Search, Prompt templates
├── docs/                  # Detailed documentation & Training details
├── data/rag/              # (Manual setup required) FAISS/BM25 indices
└── .env.example           # Unified environment template
```

## 🛠️ Building and Running

### 1. Environment Setup
Create a `.env` file in the **root directory** by copying `.env.example`.
```bash
cp .env.example .env
```
Key variables: `HF_TOKEN`, `HF_ENDPOINT_URL`, `OPENROUTER_API_KEY`.

### 2. Backend
Requires Python 3.9+.
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend
Requires Node.js v18+.
```bash
cd frontend
npm install
npm run dev
```

## 📜 Development Conventions

*   **Language:** Always use **Traditional Chinese (繁體中文)** for user-facing chat interactions.
*   **Thinking Mode:** Responses often include a `<think>` section for Chain-of-Thought (CoT). The frontend uses a dedicated `ThinkingPanel` to render this.
*   **RAG Flow:** 
    1. Query Expansion (HyDE via OpenRouter)
    2. Hybrid Search (Dense + Sparse)
    3. RRF Fusion + Reranking
    4. Prompt Augmentation (XML-like `<context>` tags)
*   **State Management:** Use Zustand for transient UI state and Dexie (IndexedDB) for persistent local conversation history.
*   **API Protocol:** The backend uses Server-Sent Events (SSE) via FastAPI's `StreamingResponse`.

## 🧪 Testing

*   **Frontend:** Uses `Vitest` for unit and smoke tests.
    ```bash
    cd frontend
    npm run test
    ```
*   **Backend:** Manual validation via the FastAPI Swagger UI at `/docs`.

## ⚠️ Important Notes

*   **Database Files:** Large index files (FAISS/BM25) are not included in the repo. They must be manually placed in `data/rag/` before RAG mode will function locally.
*   **Unified Config:** The frontend has a `predev` script that automatically copies the root `.env` to `frontend/.env.local`.

## Coding Guidelines

You are a talented professional engineer like in Google, and follow of the principle of streamlined. Please adhere to the following guidelines:

## 🚨 CRITICAL RULES - READ FIRST

> **⚠️ RULE ADHERENCE SYSTEM ACTIVE ⚠️**  
> **Claude Code must explicitly acknowledge these rules at task start**  
> **These rules override all other instructions and must ALWAYS be followed:**

### 🔄 RULE ACKNOWLEDGMENT REQUIRED
> **Before starting ANY task, Claude Code must respond with:**  
> "✅ CRITICAL RULES ACKNOWLEDGED - I will follow all prohibitions and requirements listed in CLAUDE.md"

### ❌ ABSOLUTE PROHIBITIONS
- **NEVER** create new files in root directory → use proper module structure
- **NEVER** write output files directly to root directory → use designated output folders
- **NEVER** create documentation files (.md) unless explicitly requested by user
- **NEVER** use `find`, `grep`, `cat`, `head`, `tail`, `ls` commands → use Read, LS, Grep, Glob tools instead
- **NEVER** create duplicate files (manager_v2.py, enhanced_xyz.py, utils_new.js) → ALWAYS extend existing files
- **NEVER** create multiple implementations of same concept → single source of truth
- **NEVER** copy-paste code blocks → extract into shared utilities/functions
- **NEVER** hardcode values that should be configurable → use config files/environment variables
- **NEVER** use naming like enhanced_, improved_, new_, v2_ → extend original files instead
- **NEVER** assume missing context → ask questions if uncertain
- **NEVER** hallucinate libraries or functions → only use known, verified packages
- **NEVER** delete or overwrite existing code unless explicitly instructed

### 📝 MANDATORY REQUIREMENTS
- **COMMIT** after every completed task/phase - no exceptions
- **USE TASK AGENTS** for all long-running operations (>30 seconds) - Bash commands stop when context switches
- **TODOWRITE** for complex tasks (3+ steps) → parallel agents → git checkpoints → test validation
- **READ FILES FIRST** before editing - Edit/Write tools will fail if you didn't read the file first
- **DEBT PREVENTION** - Before creating new files, check for existing similar functionality to extend  
- **SINGLE SOURCE OF TRUTH** - One authoritative implementation per feature/concept
- **TEST FIRST DEVELOPMENT** - Write tests before implementation to ensure interface consistency
- **FILE SIZE LIMIT** - Never create files longer than 500 lines of code → refactor by splitting into modules

## 🏗️ CODING GUIDELINES & STANDARDS

### 🗨️ Communication & Language Standards
- All code—including comments, variable names, function names, logs, and documentation—must be written in English
- Provide detailed comments for each code block, explaining the purpose and logic of every function, class, and significant code section
- Include thorough explanations of why specific approaches were chosen
- All error logging, debugging information, and technical documentation should be in English
- Ensure code is well-structured, follows best practices, and includes comprehensive error handling with clear English error messages

### 🔄 Project Awareness & Context Management
- Always read `PLANNING.md` at the start of a new conversation to understand the project's architecture, goals, style, and constraints
- Check `TASK.md` before starting a new task. If the task isn't listed, add it with a brief description and today's date
- Use consistent naming conventions, file structure, and architecture patterns as described in `PLANNING.md`

### 🧱 Code Structure & Modularity Principles
- Never create a file longer than 500 lines of code. If a file approaches this limit, refactor by splitting it into modules or helper files
- Organize code into clearly separated modules, grouped by feature or responsibility
- Use clear, consistent imports (prefer relative imports within packages)

### 📎 Language-Specific Style & Conventions
- **Python Projects**: Follow PEP8, use type hints, format with `black`
- **JavaScript/TypeScript**: Follow ESLint standards, use TypeScript when possible
- **Java**: Follow Oracle coding conventions, use Maven/Gradle structure
- Use `pydantic` for data validation in Python projects
- Use `FastAPI` for APIs and `SQLAlchemy` or `SQLModel` for ORM if applicable
- Write docstrings for every function using the Google style:
  ```
  def example():
      """
      Brief summary.

      Args:
          param1 (type): Description.

      Returns:
          type: Description.
      """
  ```

## 🧪 COMPREHENSIVE TESTING FRAMEWORK

### 🎯 Test-Driven Development (TDD) Workflow
- **Write tests first, implement later** - Follow TDD principles to ensure interface design consistency
- Define expected behavior through tests before writing implementation code
- Use tests as living documentation of system requirements and expected behavior
- **Ensure alignment between tests and implementation** - Tests must use the same calling patterns as the actual implementation
- If tests expect `object.attribute.method()`, implementation must provide that exact interface
- If implementation uses static methods `Class.method()`, tests should mirror this pattern

### 📊 Test Coverage & Quality Requirements
- **Always create unit tests for new features** (functions, classes, routes, etc)
- **Update existing tests when logic changes** - After any logic modification, verify and update related tests
- Tests should live in a `/tests` folder mirroring the main application structure
- Each feature must include at least:
  - **1 test for expected use case** - Normal, successful operation
  - **1 edge case test** - Boundary conditions, unusual but valid inputs
  - **1 failure case test** - Invalid inputs, error conditions, exception handling

### 🎭 Mock and Test Design Best Practices
- **Use module-level variables for aligned test mock paths** - Ensure mocks target the correct import paths
- **Access and call objects meaningfully** - Don't just import to confirm existence; actually invoke methods to match mock design
- **Trigger actual mock behavior** - Use real calls/await statements to activate mock responses
- **Design for testability** - Structure code to allow easy mocking and testing
- **Cross-platform consistency** - Don't rely on OS-specific path interpretation
- Ensure tests behave identically across different operating systems

### 🛡️ Error Handling & Performance Testing
- **Comprehensive Error Testing** - Test error propagation across module boundaries
- Verify graceful handling of file system errors
- Test configuration error scenarios (missing API keys, invalid settings)
- Ensure error messages are clear and actionable
- **Performance Testing** - Test batch processing performance with realistic data sizes
- Verify memory usage stability during extended operations
- Test proper cleanup of resources (files, connections, etc.)

### 📚 Test Documentation & Maintenance Standards
- Use clear, descriptive test method names
- Include docstrings explaining test purpose and expected behavior
- Document any special setup or teardown requirements
- Maintain test documentation alongside code changes
- Regular review of test relevance and effectiveness
- Remove or update obsolete tests
- Monitor test flakiness and address unstable tests promptly

### ✅ Quality Assurance Checklist
Before considering any feature complete:
- [ ] All new functionality has corresponding tests
- [ ] Tests cover normal, edge, and failure cases
- [ ] Test-implementation architectural consistency verified
- [ ] Cross-platform compatibility confirmed
- [ ] Error handling thoroughly tested
- [ ] Performance impact assessed
- [ ] Documentation updated accordingly
- [ ] Code review completed with focus on test quality

## 🏗️ PROJECT STRUCTURE TEMPLATES

### 📁 Simple Project Structure
```
project-root/
├── CLAUDE.md              # Essential rules for Claude Code
├── README.md              # Project documentation
├── .gitignore             # Git ignore patterns
├── src/                   # Source code (NEVER put files in root)
│   ├── main.py            # Main script/entry point
│   └── utils.py           # Utility functions
├── tests/                 # Test files
│   └── test_main.py       # Basic tests
├── docs/                  # Documentation
└── output/                # Generated output files
```

### 📁 Standard Project Structure
```
project-root/
├── CLAUDE.md              # Essential rules for Claude Code
├── README.md              # Project documentation
├── LICENSE                # Project license
├── .gitignore             # Git ignore patterns
├── src/                   # Source code (NEVER put files in root)
│   ├── main/              # Main application code
│   │   ├── [language]/    # Language-specific code
│   │   │   ├── core/      # Core business logic
│   │   │   ├── utils/     # Utility functions/classes
│   │   │   ├── models/    # Data models/entities
│   │   │   ├── services/  # Service layer
│   │   │   └── api/       # API endpoints/interfaces
│   │   └── resources/     # Non-code resources
│   │       ├── config/    # Configuration files
│   │       └── assets/    # Static assets
│   └── test/              # Test code
│       ├── unit/          # Unit tests
│       └── integration/   # Integration tests
├── docs/                  # Documentation
├── tools/                 # Development tools and scripts
├── examples/              # Usage examples
└── output/                # Generated output files
```

### 📁 AI/ML Project Structure
```
project-root/
├── CLAUDE.md              # Essential rules for Claude Code
├── README.md              # Project documentation
├── LICENSE                # Project license
├── .gitignore             # Git ignore patterns
├── src/                   # Source code (NEVER put files in root)
│   ├── main/              # Main application code
│   │   ├── python/        # Python-specific code
│   │   │   ├── core/      # Core ML algorithms
│   │   │   ├── utils/     # Data processing utilities
│   │   │   ├── models/    # Model definitions/architectures
│   │   │   ├── services/  # ML services and pipelines
│   │   │   ├── api/       # ML API endpoints/interfaces
│   │   │   ├── training/  # Training scripts and pipelines
│   │   │   ├── inference/ # Inference and prediction code
│   │   │   └── evaluation/# Model evaluation and metrics
│   │   └── resources/     # Non-code resources
│   │       ├── config/    # Configuration files
│   │       ├── data/      # Sample/seed data
│   │       └── assets/    # Static assets
│   └── test/              # Test code
│       ├── unit/          # Unit tests
│       ├── integration/   # Integration tests
│       └── fixtures/      # Test data/fixtures
├── data/                  # AI/ML Dataset management
│   ├── raw/               # Original, unprocessed datasets
│   ├── processed/         # Cleaned and transformed data
│   ├── external/          # External data sources
│   └── temp/              # Temporary data processing files
├── notebooks/             # Jupyter notebooks and analysis
│   ├── exploratory/       # Data exploration notebooks
│   ├── experiments/       # ML experiments and prototyping
│   └── reports/           # Analysis reports and visualizations
├── models/                # ML Models and artifacts
│   ├── trained/           # Trained model files
│   ├── checkpoints/       # Model checkpoints
│   └── metadata/          # Model metadata and configs
├── experiments/           # ML Experiment tracking
│   ├── configs/           # Experiment configurations
│   ├── results/           # Experiment results and metrics
│   └── logs/              # Training logs and metrics
├── docs/                  # Documentation
├── tools/                 # Development tools and scripts
├── examples/              # Usage examples
└── output/                # Generated output files
```

## ✅ TASK COMPLETION & DOCUMENTATION STANDARDS

### 📝 Task Management Requirements
- Mark completed tasks in `TASK.md` immediately after finishing them
- Add new sub-tasks or TODOs discovered during development to `TASK.md` under a "Discovered During Work" section

### 📚 Documentation & Explainability Standards
- Update `README.md` when new features are added, dependencies change, or setup steps are modified
- Comment non-obvious code and ensure everything is understandable to a mid-level developer
- When writing complex logic, add an inline `# Reason:` comment explaining the why, not just the what

## 🚨 TECHNICAL DEBT PREVENTION SYSTEM

### 🔍 MANDATORY PRE-TASK COMPLIANCE CHECK
> **STOP: Before starting any task, Claude Code must explicitly verify ALL points:**

**Step 1: Rule Acknowledgment**
- [ ] ✅ I acknowledge all critical rules in CLAUDE.md and will follow them

**Step 2: Task Analysis**  
- [ ] Will this create files in root? → If YES, use proper module structure instead
- [ ] Will this take >30 seconds? → If YES, use Task agents not Bash
- [ ] Is this 3+ steps? → If YES, use TodoWrite breakdown first
- [ ] Am I about to use grep/find/cat? → If YES, use proper tools instead

**Step 3: Technical Debt Prevention (MANDATORY SEARCH FIRST)**
- [ ] **SEARCH FIRST**: Use Grep pattern="<functionality>.*<keyword>" to find existing implementations
- [ ] **CHECK EXISTING**: Read any found files to understand current functionality
- [ ] Does similar functionality already exist? → If YES, extend existing code
- [ ] Am I creating a duplicate class/manager? → If YES, consolidate instead
- [ ] Will this create multiple sources of truth? → If YES, redesign approach
- [ ] Have I searched for existing implementations? → Use Grep/Glob tools first
- [ ] Can I extend existing code instead of creating new? → Prefer extension over creation
- [ ] Am I about to copy-paste code? → Extract to shared utility instead

**Step 4: Session Management**
- [ ] Is this a long/complex task? → If YES, plan context checkpoints
- [ ] Have I been working >1 hour? → If YES, consider /compact or session break

> **⚠️ DO NOT PROCEED until all checkboxes are explicitly verified**

### 🧹 Debt Prevention Workflow Pattern
**Before Creating ANY New File:**
1. **🔍 Search First** - Use Grep/Glob to find existing implementations
2. **📋 Analyze Existing** - Read and understand current patterns
3. **🤔 Decision Tree**: Can extend existing? → DO IT | Must create new? → Document why
4. **✅ Follow Patterns** - Use established project patterns
5. **📈 Validate** - Ensure no duplication or technical debt

**Wrong Approach (Creates Technical Debt):**
```
# Creating new file without searching first
Write(file_path="new_feature.py", content="...")
```

**Correct Approach (Prevents Technical Debt):**
```
# 1. SEARCH FIRST
Grep(pattern="feature.*implementation", include="*.py")
# 2. READ EXISTING FILES  
Read(file_path="existing_feature.py")
# 3. EXTEND EXISTING FUNCTIONALITY
Edit(file_path="existing_feature.py", old_string="...", new_string="...")
```

**⚠️ Prevention is better than consolidation - build clean from the start.**  
**🎯 Focus on single source of truth and extending existing functionality.**  
**📈 Each task should maintain clean architecture and prevent technical debt.**  
**🧪 Remember: Tests first, implementation second - this ensures better design.**

> **⚠️ DO NOT PROCEED until all checkboxes are explicitly verified**/
