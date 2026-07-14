#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_FILE="$ROOT_DIR/deploy/systemd/ontology-platform.service"
UNIT_NAME="ontology-platform.service"

log() { printf '[install-user-service] %s\n' "$*"; }
fail() { printf '[install-user-service] ERROR: %s\n' "$*" >&2; exit 1; }

command -v systemctl >/dev/null 2>&1 || fail "systemctl is required"
[[ -f "$UNIT_FILE" ]] || fail "Missing unit file: $UNIT_FILE"

if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)" != "yes" ]]; then
  log "WARNING: user lingering is disabled; run 'sudo loginctl enable-linger $USER' for boot startup before login"
fi

log "Linking $UNIT_FILE into the user systemd manager"
systemctl --user link --force "$UNIT_FILE"
systemctl --user daemon-reload

log "Enabling and starting $UNIT_NAME"
systemctl --user enable --now "$UNIT_NAME"

log "Installed successfully"
systemctl --user --no-pager --full status "$UNIT_NAME"
