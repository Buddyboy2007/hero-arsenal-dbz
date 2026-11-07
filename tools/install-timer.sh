#!/usr/bin/env bash
# Install the ten-minute publisher as a systemd *user* timer.
# User scope on purpose: the job reads a Steam install in $HOME and pushes
# with a key in $HOME/.ssh, neither of which a system unit should touch.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.config/systemd/user"
mkdir -p "$DEST"

install -m 0644 "$HERE/dbz-site.service" "$DEST/dbz-site.service"
install -m 0644 "$HERE/dbz-site.timer"   "$DEST/dbz-site.timer"

systemctl --user daemon-reload
systemctl --user enable --now dbz-site.timer

echo
systemctl --user list-timers dbz-site.timer --no-pager
echo
echo "Log:  tail -f $(dirname "$HERE")/var/update.log"
echo "Stop: systemctl --user disable --now dbz-site.timer"
echo
echo "The timer runs while you are logged in. To keep it running after you"
echo "log out as well, enable lingering for your account:"
echo "    loginctl enable-linger $USER"
