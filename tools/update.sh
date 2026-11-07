#!/usr/bin/env bash
#
# Re-read the live Garry's Mod install, rebuild the site, and publish it --
# but only when something actually changed.
#
# Driven by the systemd user timer in tools/dbz-site.timer (every ten
# minutes). Safe to run by hand at any time.
#
# Unattended by design: no ssh-agent, no keyring, no interactive git. The
# deploy key is named explicitly because a timer unit inherits neither.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG="$ROOT/var/update.log"
mkdir -p "$ROOT/var"

# Keep the log to the last ~2000 lines rather than letting a ten-minute job
# grow it without bound.
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 4000 ]; then
	tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

exec >> "$LOG" 2>&1
echo "=== $(date -Is) ==="

export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/id_ed25519 -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

# git identity is unset globally on this machine, so state it per-invocation
# rather than writing to the user's global config.
GIT=(git -c user.name="Buddyboy2007" -c user.email="buddyboo2007@gmail.com")

GMOD="$HOME/.local/share/Steam/steamapps/common/GarrysMod/garrysmod"
if [ ! -d "$GMOD/lua/autorun" ]; then
	echo "skip: Garry's Mod not found at $GMOD"
	exit 0
fi

python3 tools/extract.py
python3 tools/stamp.py
python3 tools/build.py

# stamp.py has already held the timestamp still if the roster is unchanged,
# so a dirty tree here means a real change -- in the roster, or in the
# generator itself.
if [ -z "$("${GIT[@]}" status --porcelain)" ]; then
	echo "no change"
	exit 0
fi

"${GIT[@]}" add -A
"${GIT[@]}" commit -q -m "Site update $(date '+%Y-%m-%d %H:%M:%S')"
"${GIT[@]}" push -q origin HEAD
echo "published $("${GIT[@]}" rev-parse --short HEAD)"
