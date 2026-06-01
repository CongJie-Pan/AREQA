#!/bin/bash
set -e

echo "🌸 Initializing XiaoHong QA System Environment..."

# 0. Initialize Git LFS
echo "📦 Initializing Git LFS..."
git lfs install --skip-smudge
git lfs pull
git lfs install --force

# 1. Install Gemini CLI and Drift if missing
if ! command -v gemini &> /dev/null || ! command -v drift &> /dev/null; then
    echo "🚀 Installing Gemini CLI and Drift..."
    npm install -g @google/gemini-cli driftdetect driftdetect-mcp
else
    echo "✅ Gemini CLI and Drift are already installed."
fi

# 2. Setup Backend Virtual Environment
echo "🐍 Setting up Backend Python environment..."
BACKEND_DIR="/workspaces/XiaoHong_RedChamber_QA_System/backend"
VENV_PATH="$BACKEND_DIR/.venv"

# Check if venv is missing or broken (e.g., missing asyncio)
if [ ! -d "$VENV_PATH" ] || ! "$VENV_PATH/bin/python" -c "import asyncio" &> /dev/null; then
    echo "🔄 Recreating backend virtual environment..."
    rm -rf "$VENV_PATH"
    # Use python3.11 explicitly if available for stability
    if command -v python3.11 &> /dev/null; then
        python3.11 -m venv "$VENV_PATH"
    else
        python3 -m venv "$VENV_PATH"
    fi
    echo "📦 Installing backend dependencies..."
    "$VENV_PATH/bin/pip" install --upgrade pip
    "$VENV_PATH/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
else
    echo "✅ Backend virtual environment is healthy."
fi

# 3. Setup Frontend Environment (Optional but recommended)
echo "⚛️ Checking frontend dependencies..."
FRONTEND_DIR="/workspaces/XiaoHong_RedChamber_QA_System/frontend"
if [ -d "$FRONTEND_DIR" ] && [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd "$FRONTEND_DIR" && npm install && cd -
fi

# 4. Add Welcome Message to .bashrc if not already present
if ! grep -q "🤖 Drift AI Brain" ~/.bashrc; then
    echo "📝 Adding welcome message to .bashrc..."
    printf '\necho -e "\\033[1;36m======================================\\033[0m" \necho -e "\\033[1;32m🤖 Drift AI Brain & Gemini CLI are Ready!\\033[0m" \necho -e "\\033[1;33m👉 Run \\033[1;37mdrift init -y\\033[1;33m  (to initialize the AI codebase memory)\\033[0m" \necho -e "\\033[1;33m👉 Run \\033[1;37mdrift scan\\033[1;33m     (to manually sync code changes to the brain)\\033[0m" \necho -e "\\033[1;33m👉 Run \\033[1;37mgemini\\033[1;33m         (to start the AI conversation)\\033[0m" \necho -e "\\033[1;36m======================================\\033[0m\"\n' >> ~/.bashrc
fi

echo "✨ Initialization complete!"
