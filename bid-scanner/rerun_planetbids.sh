#!/usr/bin/env bash
# Keep retrying the PlanetBids portals that got blocked, until they all come
# back clean (or we've tried MAX_ROUNDS times).
#
#   ./rerun_planetbids.sh            # full scan, then resume-loop the blocked ones
#   ./rerun_planetbids.sh resume     # skip the full scan, go straight to resume-loop
#
# Each round opens Chrome and waits for you to solve the CAPTCHA and press Enter
# — it is NOT fully unattended. Between rounds it sleeps COOLDOWN_MIN minutes to
# let any rate-limit / IP block cool off.

set -u
cd "$(dirname "$0")"

MAX_ROUNDS=4
COOLDOWN_MIN=15

if [[ "${1:-}" != "resume" ]]; then
  echo "=== Round 0: full PlanetBids scan ==="
  python main.py --source planetbids
  code=$?
  if [[ $code -eq 0 ]]; then
    echo "All portals clean on the first pass. Done."
    exit 0
  fi
fi

for ((r = 1; r <= MAX_ROUNDS; r++)); do
  echo
  echo "=== Resume round $r/$MAX_ROUNDS (cooldown ${COOLDOWN_MIN}m first) ==="
  sleep "$((COOLDOWN_MIN * 60))"
  python main.py --source planetbids --resume
  code=$?
  if [[ $code -eq 0 ]]; then
    echo "All PlanetBids portals now clean. Done."
    exit 0
  fi
  echo "Still incomplete (exit $code)."
done

echo
echo "Gave up after $MAX_ROUNDS resume rounds. Check output/planetbids_state.json"
echo "and try again later — the block may be IP-level and need a few hours."
exit 1
