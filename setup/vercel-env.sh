#!/bin/bash
#
# Manage env vars on the fcu-bid-dashboard Vercel project using VERCEL_TOKEN
# from ~/fcu/.env. Values are never printed.
#
#   bash ~/fcu-cron/setup/vercel-env.sh ls
#   bash ~/fcu-cron/setup/vercel-env.sh set KEY VALUE [targets] [type]
#   bash ~/fcu-cron/setup/vercel-env.sh set KEY - [targets] [type]   # value from stdin (secrets)
#   bash ~/fcu-cron/setup/vercel-env.sh rm KEY
#
#   targets: comma-separated, default "production,preview"
#   type:    encrypted (default) | sensitive | plain
#
# Changes apply on the NEXT deploy (merge to main triggers one).
#
set -euo pipefail
ENV_FILE="${FCU_ENV_FILE:-$HOME/fcu/.env}"
export VERCEL_TOKEN=$(sed -nE "s/^VERCEL_TOKEN=[[:space:]]*[\"']?([^\"'[:space:]#]+).*/\1/p" "$ENV_FILE" | head -1)
[ -n "$VERCEL_TOKEN" ] || { echo "VERCEL_TOKEN not found in $ENV_FILE" >&2; exit 1; }
[ "${1:-}" = set ] && [ "${3:-}" = "-" ] && export VAL_STDIN="$(cat)"

exec python3 -I - "$@" <<'PY'
import json, os, sys, urllib.request

API = "https://api.vercel.com/v9/projects/fcu-bid-dashboard/env"
HDR = {"Authorization": f"Bearer {os.environ['VERCEL_TOKEN']}", "Content-Type": "application/json"}

def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, headers=HDR,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Vercel {e.code}: {e.read().decode()[:300]}")

args = sys.argv[1:]
cmd = args[0] if args else "ls"
envs = call("GET", API)["envs"]

if cmd == "ls":
    for e in envs:
        print(f"{e['key']:24} {','.join(e['target']):24} {e['type']}")
elif cmd == "set" and len(args) >= 3:
    key, val = args[1], os.environ.get("VAL_STDIN") if args[2] == "-" else args[2]
    targets = (args[3] if len(args) > 3 else "production,preview").split(",")
    typ = args[4] if len(args) > 4 else "encrypted"
    if not val:
        sys.exit("empty value")
    body = {"key": key, "value": val, "target": targets, "type": typ}
    existing = [e for e in envs if e["key"] == key]
    if len(existing) > 1:
        sys.exit(f"{key} has {len(existing)} entries — rm it first, then set")
    if existing:  # Vercel's upsert flag doesn't overwrite — edit in place
        call("PATCH", f"{API}/{existing[0]['id']}", body)
    else:
        call("POST", API, body)
    print(f"{'updated' if existing else 'created'} {key} ({','.join(targets)}, {typ})")
elif cmd == "rm" and len(args) == 2:
    ids = [e["id"] for e in envs if e["key"] == args[1]]
    if not ids:
        sys.exit(f"{args[1]} not found")
    for i in ids:
        call("DELETE", f"{API}/{i}")
    print(f"removed {args[1]} ({len(ids)} entr{'y' if len(ids) == 1 else 'ies'})")
else:
    sys.exit("usage: vercel-env.sh ls | set KEY VALUE|- [targets] [type] | rm KEY")
PY
