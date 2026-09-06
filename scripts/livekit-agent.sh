#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="$ROOT_DIR/livekit_agent"
ENV_FILE="${AREQA_ENV_FILE:-$ROOT_DIR/.env}"
SECRETS_FILE=""

cleanup() {
  if [[ -n "$SECRETS_FILE" && -f "$SECRETS_FILE" ]]; then
    : > "$SECRETS_FILE"
    rm "$SECRETS_FILE"
  fi
}
trap cleanup EXIT

usage() {
  cat <<'USAGE'
Usage: scripts/livekit-agent.sh <command>

Commands:
  deploy        Deploy the current livekit_agent version to LiveKit Agent Cloud.
  sync-secrets  Sync required LiveKit Agent Cloud secrets from .env.
  status        Show the configured LiveKit Cloud agent status.
  logs          Tail deploy logs for the configured LiveKit Cloud agent.

Environment:
  AREQA_ENV_FILE  Optional path to the .env file used by sync-secrets.
USAGE
}

require_lk() {
  if ! command -v lk >/dev/null 2>&1; then
    echo "LiveKit CLI is not installed. Run: curl -sSL https://get.livekit.io/cli | bash" >&2
    exit 1
  fi
}

require_agent_config() {
  if [[ ! -f "$AGENT_DIR/livekit.toml" ]]; then
    echo "Missing livekit_agent/livekit.toml. Run 'lk agent create' from livekit_agent first." >&2
    exit 1
  fi
}

sync_secrets() {
  require_lk
  require_agent_config
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing env file: $ENV_FILE" >&2
    exit 1
  fi

  SECRETS_FILE="$(mktemp)"
  chmod 600 "$SECRETS_FILE"
  awk '
    /^(OPENAI_API_KEY|ANAM_API_KEY|ANAM_AVATAR_ID|LIVEKIT_URL|LIVEKIT_API_KEY|LIVEKIT_API_SECRET)=/ {
      sub(/\r$/, "");
      print;
    }
  ' "$ENV_FILE" > "$SECRETS_FILE"

  local found_count
  found_count="$(wc -l < "$SECRETS_FILE" | tr -d ' ')"
  if [[ "$found_count" -lt 6 ]]; then
    echo "Expected 6 secrets in $ENV_FILE, found $found_count." >&2
    echo "Required: OPENAI_API_KEY, ANAM_API_KEY, ANAM_AVATAR_ID, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET" >&2
    exit 1
  fi

  (
    cd "$AGENT_DIR"
    lk agent update-secrets --secrets-file "$SECRETS_FILE" --overwrite
  )
}

main() {
  local command="${1:-}"
  case "$command" in
    deploy)
      require_lk
      require_agent_config
      (cd "$AGENT_DIR" && lk agent deploy)
      ;;
    sync-secrets)
      sync_secrets
      ;;
    status)
      require_lk
      require_agent_config
      (cd "$AGENT_DIR" && lk agent status)
      ;;
    logs)
      require_lk
      require_agent_config
      (cd "$AGENT_DIR" && lk agent logs)
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      echo "Unknown command: $command" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
