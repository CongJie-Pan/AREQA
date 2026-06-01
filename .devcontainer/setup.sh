#!/usr/bin/env bash
set -euo pipefail

echo "Initializing AREQA System Environment..."

WORKSPACE_DIR="${CODESPACE_VSCODE_FOLDER:-$(pwd)}"
BACKEND_DIR="${WORKSPACE_DIR}/backend"
FRONTEND_DIR="${WORKSPACE_DIR}/frontend"
VENV_PATH="${BACKEND_DIR}/.venv"

echo "📦 Initializing Git LFS..."
git lfs install --skip-smudge
git lfs pull || echo "⚠️ git lfs pull skipped or failed"

echo "🚀 Installing Antigravity CLI..."
if ! command -v agy >/dev/null 2>&1; then
  curl -fsSL https://antigravity.google/cli/install.sh | bash
else
  echo "✅ Antigravity CLI is already installed."
fi

echo "🚀 Installing Drift..."
if ! command -v drift >/dev/null 2>&1; then
  npm install -g driftdetect driftdetect-mcp
else
  echo "✅ Drift is already installed."
fi

echo "🔎 Checking versions..."
node -v
npm -v
python3.11 -V || python3 -V
agy --version || true
drift --version || true

echo "🐍 Setting up Backend Python environment..."
if [ ! -d "$VENV_PATH" ] || ! "$VENV_PATH/bin/python" -c "import asyncio" >/dev/null 2>&1; then
  echo "🔄 Recreating backend virtual environment..."
  rm -rf "$VENV_PATH"
  if command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv "$VENV_PATH"
  else
    python3 -m venv "$VENV_PATH"
  fi

  echo "📦 Installing backend dependencies..."
  "$VENV_PATH/bin/pip" install --upgrade pip setuptools wheel

  if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    "$VENV_PATH/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
  fi
else
  echo "✅ Backend virtual environment is healthy."
fi

echo "⚛️ Checking frontend dependencies..."
if [ -d "$FRONTEND_DIR" ]; then
  cd "$FRONTEND_DIR"
  if [ ! -d "node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    if [ -f package-lock.json ]; then
      npm ci
    else
      npm install
    fi
  fi
  cd "$WORKSPACE_DIR"
fi

if ! grep -q "Antigravity CLI is Ready" ~/.bashrc 2>/dev/null; then
  cat >> ~/.bashrc <<'EOF'

# Auto-manage Python virtual environment for AREQA
VENV_DIR="/workspaces/AREQA/backend/.venv"
REQUIREMENTS_FILE="/workspaces/AREQA/backend/requirements.txt"

if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo -e "\033[1;33m🔍 Python virtual environment (.venv) not found. Initializing setup...\033[0m"
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip setuptools wheel
    if [ -f "$REQUIREMENTS_FILE" ]; then
        echo -e "\033[1;32m📦 Installing requirements...\033[0m"
        pip install -r "$REQUIREMENTS_FILE"
    fi
    echo -e "\033[1;32m✅ Backend virtual environment is ready and activated!\033[0m"
fi

echo -e "\033[1;36m======================================\033[0m"
echo -e "\033[1;32m🤖 Drift AI Brain & Antigravity CLI are Ready!\033[0m"
echo -e "\033[1;33m👉 Run \033[1;37magy\033[0m"
echo -e "\033[1;33m👉 Run \033[1;37mdrift init -y\033[0m"
echo -e "\033[1;33m👉 Run \033[1;37mdrift scan\033[0m"
echo -e "\033[1;36m======================================\033[0m"
EOF
fi

echo "✨ Initialization complete!"