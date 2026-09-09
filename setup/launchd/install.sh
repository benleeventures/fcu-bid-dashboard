#!/bin/bash
#
# FCU scheduled jobs — installer.
#
# The launchd jobs (scraper, parser, digest, jobwalk, expirer, supervisor) run
# out of a DEDICATED git worktree at ~/fcu-cron kept on a DETACHED HEAD at
# origin/main — no human ever works in it, and it does not hold the `main`
# branch (so the primary checkout can). Each job does
#   git -C ~/fcu-cron pull --quiet --ff-only origin main
# before running, so the schedule always executes freshly-merged code without
# depending on whatever branch someone left the primary checkout on.
#
# Run this after changing any setup/launchd/*.plist. Safe to re-run.
#
#   bash setup/launchd/install.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # primary checkout
CRON_TREE="$HOME/fcu-cron"
LA="$HOME/Library/LaunchAgents"
JOBS=(scraper parser digest jobwalk expirer supervisor)
RUNTIME_FILES=(bid-scanner/.env bid-scanner/cookies.json bid-scanner/cookies_opengov.json)

echo "primary checkout : $REPO"
echo "cron worktree    : $CRON_TREE"

# 1. Create the dedicated worktree if it isn't there yet. Detached HEAD, so it
#    never claims the `main` branch — the primary checkout keeps that.
git -C "$REPO" fetch --quiet origin main
if [ ! -e "$CRON_TREE/.git" ]; then
  echo "creating cron worktree (detached at origin/main)…"
  git -C "$REPO" worktree add --detach "$CRON_TREE" origin/main
fi
git -C "$CRON_TREE" checkout --quiet --detach origin/main
git -C "$CRON_TREE" pull --quiet --ff-only origin main
echo "cron worktree at $(git -C "$CRON_TREE" rev-parse --short HEAD) (detached)"

# 2. Copy over the git-ignored runtime files (secrets / cookies) that a fresh
#    worktree doesn't get. Only copies what's missing — never clobbers.
mkdir -p "$CRON_TREE/bid-scanner/logs" "$CRON_TREE/bid-scanner/output"
for rel in "${RUNTIME_FILES[@]}"; do
  if [ ! -f "$CRON_TREE/$rel" ] && [ -f "$REPO/$rel" ]; then
    cp "$REPO/$rel" "$CRON_TREE/$rel"
    echo "copied $rel"
  fi
done
[ -f "$CRON_TREE/bid-scanner/.env" ] || { echo "ERROR: $CRON_TREE/bid-scanner/.env missing — copy it in by hand"; exit 1; }

# 3. Install + reload each launchd job from the versioned template.
for job in "${JOBS[@]}"; do
  src="$REPO/setup/launchd/com.fcu.$job.plist"
  dst="$LA/com.fcu.$job.plist"
  cp "$src" "$dst"
  launchctl unload "$dst" 2>/dev/null || true
  launchctl load "$dst"
  echo "loaded com.fcu.$job"
done

echo
echo "done. verify:  launchctl list | grep com.fcu"
echo "log rotation (needs sudo, one time):"
echo "  sudo cp $REPO/setup/newsyslog/com.fcu.bid-scanner.conf /etc/newsyslog.d/"
