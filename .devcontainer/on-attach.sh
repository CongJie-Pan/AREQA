#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="${CODESPACE_VSCODE_FOLDER:-$(pwd)}"
cd "$WORKSPACE_DIR"

echo "🔎 Checking runtime tools..."
command -v agy >/dev/null 2>&1 && agy --version || echo "⚠️ agy not found"
command -v drift >/dev/null 2>&1 && drift --version || echo "⚠️ drift not found"

if [ ! -d ".drift" ] && command -v drift >/dev/null 2>&1; then
  echo "🔧 Initializing Drift..."
  drift init -y || echo "⚠️ drift init failed"
fi

echo "ℹ️ If this is your first time, run: agy"
echo "ℹ️ Antigravity CLI may ask you to trust this workspace and complete login in browser."
echo "ℹ️ Run 'drift scan' manually after login if needed."

echo "🚀 Starting Redis server..."
sudo service redis-server start >/dev/null 2>&1 || echo "⚠️ Failed to start Redis server"