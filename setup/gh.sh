#!/bin/bash
#
# Run `gh` authenticated as the FCU GitHub token (GITHUB_TOKEN in ~/fcu/.env).
# The token is never printed. Use this for ALL GitHub operations (PRs, merges,
# API calls) — do not rely on `gh auth login` state or the macOS keychain.
#
#   bash ~/fcu-cron/setup/gh.sh pr create --title ... --body ...
#
set -euo pipefail
ENV_FILE="${FCU_ENV_FILE:-$HOME/fcu/.env}"
tok=$(sed -nE "s/^GITHUB_TOKEN=[[:space:]]*[\"']?([^\"'[:space:]#]+).*/\1/p" "$ENV_FILE" | head -1)
[ -n "$tok" ] || { echo "GITHUB_TOKEN not found in $ENV_FILE" >&2; exit 1; }
GH_TOKEN="$tok" exec gh "$@"
