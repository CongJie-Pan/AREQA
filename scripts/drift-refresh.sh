#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DRIFTIGNORE_FILE="${ROOT_DIR}/.driftignore"
REPORT_DIR="${ROOT_DIR}/docs/drift_report"
REPORT_FILE="${REPORT_DIR}/drift-refresh-$(date -u +%Y%m%dT%H%M%SZ).md"
SCAN_PATHS=(backend frontend tests)

mkdir -p "$REPORT_DIR"

export CI=true
export NO_COLOR=1
export FORCE_COLOR=0
export TERM=dumb

sanitize_report_stream() {
  perl -CS -pe '
    s/\e\][^\a]*(?:\a|\e\\)//g;
    s/\e\[[0-?]*[ -\/]*[@-~]//g;
    s/\r/\n/g;
    s/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]//g;
  '
}

finish_report() {
  local status="$1"

  echo
  if [ "$status" -eq 0 ]; then
    echo "Drift refresh completed successfully."
  else
    echo "Drift refresh failed with exit code ${status}."
  fi
  echo "Report written to: ${REPORT_FILE}"

  ln -sfn "$(basename "$REPORT_FILE")" "${REPORT_DIR}/latest.md"
}

trap 'finish_report $?' EXIT

exec > >(sanitize_report_stream | tee "$REPORT_FILE") 2>&1

echo "# Drift Refresh Report"
echo
echo "- Started at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "- Working directory: ${ROOT_DIR}"
echo "- Scan paths: ${SCAN_PATHS[*]}"
echo

if ! command -v drift >/dev/null 2>&1; then
  echo "drift command not found. Run .devcontainer/setup.sh first."
  exit 1
fi

ensure_driftignore_entry() {
  local pattern="$1"

  if [ ! -f "$DRIFTIGNORE_FILE" ]; then
    printf "# Drift ignore patterns\n" > "$DRIFTIGNORE_FILE"
  fi

  if ! grep -qxF "$pattern" "$DRIFTIGNORE_FILE"; then
    printf "\n%s\n" "$pattern" >> "$DRIFTIGNORE_FILE"
  fi
}

run_step() {
  local title="$1"
  shift

  echo
  echo "==> ${title}"
  "$@"
}

run_step "Ensure Drift ignore scope" ensure_driftignore_entry ".git/"
ensure_driftignore_entry "misc/"
ensure_driftignore_entry "temp/"

run_step "Rescan main project scope" drift scan "${SCAN_PATHS[@]}" --force

run_step "Build call graph" drift callgraph build
run_step "Build test topology" drift test-topology build
run_step "Build coupling graph" drift coupling build
run_step "Build error handling analysis" drift error-handling build

run_step "Audit Drift patterns" drift audit
run_step "Auto-approve eligible patterns" drift approve --auto --yes
run_step "Show detailed Drift status" drift status --detailed

echo
echo "Drift refresh complete."
