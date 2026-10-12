#!/usr/bin/env bash
#
# Installer for the `secret-intake-webform` Hermes skill
# -----------------------------------------------------
# Copies the skill (SKILL.md + scripts/) into $HERMES_HOME/skills/security/.
# No system packages are needed: the script uses the Python standard library only.
#
# Usage:
#   ./install.sh                 # install into $HERMES_HOME (default ~/.hermes)
#   ./install.sh --profile work  # install into ~/.hermes/profiles/work
#   ./install.sh --dir /path     # install into an explicit HERMES_HOME
#   ./install.sh --help
#
# The installer is idempotent: running it again just refreshes the files.

set -euo pipefail

SKILL_NAME="secret-intake-webform"
CATEGORY="security"

DO_PROFILE=""
DO_DIR=""

log()  { printf '\033[1;32m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warning]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --profile) DO_PROFILE="${2:-}"; [ -n "$DO_PROFILE" ] || die "--profile needs a name"; shift 2 ;;
    --dir)     DO_DIR="${2:-}";     [ -n "$DO_DIR" ]     || die "--dir needs a path"; shift 2 ;;
    --help|-h) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown argument: $1 (use --help)" ;;
  esac
done

if [ -n "$DO_DIR" ]; then
  HERMES_ROOT="$DO_DIR"
elif [ -n "$DO_PROFILE" ]; then
  HERMES_ROOT="${HERMES_HOME_BASE:-$HOME/.hermes}/profiles/$DO_PROFILE"
else
  HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
fi

[ -d "$HERMES_ROOT" ] || die "Hermes home not found: $HERMES_ROOT (install Hermes first, or pass --dir)"

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SRC_DIR/SKILL.md" ] || die "SKILL.md not found next to install.sh"
[ -f "$SRC_DIR/scripts/secret_form.py" ] || die "scripts/secret_form.py not found next to install.sh"

command -v python3 >/dev/null 2>&1 || die "python3 is required but not in PATH"

DEST_DIR="$HERMES_ROOT/skills/$CATEGORY/$SKILL_NAME"
mkdir -p "$DEST_DIR/scripts"
install -m 644 "$SRC_DIR/SKILL.md" "$DEST_DIR/SKILL.md"
install -m 755 "$SRC_DIR/scripts/secret_form.py" "$DEST_DIR/scripts/secret_form.py"
log "Skill installed in: $DEST_DIR"

if command -v hermes >/dev/null 2>&1; then
  if [ -n "$DO_PROFILE" ]; then
    HERMES_HOME="$HERMES_ROOT" hermes skills list 2>/dev/null | grep -q "$SKILL_NAME" \
      && log "Hermes already sees '$SKILL_NAME' in profile '$DO_PROFILE'." \
      || warn "Skill copied. Restart the session (or run 'hermes skills list') to confirm."
  else
    hermes skills list 2>/dev/null | grep -q "$SKILL_NAME" \
      && log "Hermes already sees '$SKILL_NAME'." \
      || warn "Skill copied. Restart the session (or run 'hermes skills list') to confirm."
  fi
else
  warn "'hermes' not found in PATH. Install Hermes Agent, then check with: hermes skills list"
fi

cat <<EOF

Next step — make the form reachable:

  1. Add an ingress rule to your Cloudflare Tunnel (~/.cloudflared/config.yml), BEFORE the
     catch-all line:

       - hostname: token.example.com
         service: http://127.0.0.1:8899

  2. Create the DNS route and restart the tunnel:

       cloudflared tunnel route dns <your-tunnel> token.example.com
       systemctl --user restart cloudflared.service

  3. Protect that hostname with a Cloudflare Access application whose policy lists the
     emails allowed to open the form.

  4. Start a form when you need a secret (see SKILL.md):

       python3 $DEST_DIR/scripts/secret_form.py \\
         --dest ~/.hermes/.env.new --campo "API key" --host token.example.com

Read SKILL.md for the full procedure, the security model and the pitfalls.

EOF
