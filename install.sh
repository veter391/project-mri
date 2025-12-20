#!/usr/bin/env bash
# project-mri one-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/project-mri/project-mri/main/install.sh | bash
# Usage: curl -fsSL ... | bash -s -- --user

set -euo pipefail

# ---------- colors ----------
if [ -t 1 ]; then
    RED=$'\033[0;31m'; GRN=$'\033[0;32m'; YLW=$'\033[1;33m'; BLU=$'\033[0;34m'; NC=$'\033[0m'
else
    RED=""; GRN=""; YLW=""; BLU=""; NC=""
fi
say()  { printf "${BLU}[mri]${NC} %s\n" "$*"; }
ok()   { printf "${GRN}[ok]${NC} %s\n" "$*"; }
warn() { printf "${YLW}[warn]${NC} %s\n" "$*"; }
die()  { printf "${RED}[err]${NC} %s\n" "$*" >&2; exit 1; }

# ---------- arg parsing ----------
PYTHON=""
USER_INSTALL=0
SYSTEM_INSTALL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --python) PYTHON="$2"; shift 2 ;;
        --user)   USER_INSTALL=1; shift ;;
        --system) SYSTEM_INSTALL=1; shift ;;
        --help|-h)
            cat <<EOF
project-mri installer

Usage:
  $0 [options]

Options:
  --python PATH     Use this Python interpreter (default: python3)
  --user            Install into user site (~/.local)
  --system          Install system-wide (requires sudo)
  -h, --help        Show this help

Examples:
  # One-liner:
  curl -fsSL https://raw.githubusercontent.com/project-mri/project-mri/main/install.sh | bash

  # User install (no sudo):
  curl -fsSL ... | bash -s -- --user

  # Custom Python:
  curl -fsSL ... | bash -s -- --python /opt/python3.12/bin/python3
EOF
            exit 0
            ;;
        *) die "Unknown option: $1 (use --help)" ;;
    esac
done

# ---------- detect Python ----------
detect_python() {
    if [ -n "$PYTHON" ]; then
        echo "$PYTHON"; return
    fi
    for cand in python3.12 python3.11 python3.10 python3 python; do
        if command -v "$cand" >/dev/null 2>&1; then
            local ver
            ver=$("$cand" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            # Require 3.10+
            case "$ver" in
                3.1[0-9]|3.[2-9][0-9]) echo "$cand"; return ;;
            esac
        fi
    done
    echo ""
}

PYTHON=$(detect_python)
if [ -z "$PYTHON" ]; then
    die "Python 3.10+ not found. Install it first, or pass --python PATH."
fi

ok "Using Python: $PYTHON ($($PYTHON --version 2>&1))"

# ---------- detect git ----------
if ! command -v git >/dev/null 2>&1; then
    warn "git not found — repository cloning won't work, but scans of local paths will."
fi

# ---------- install via pip ----------
PIP_ARGS=()
if [ "$USER_INSTALL" -eq 1 ]; then
    PIP_ARGS+=(--user)
    ok "Installing into user site (~/.local)"
elif [ "$SYSTEM_INSTALL" -eq 1 ]; then
    if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
        die "System install requires root or sudo"
    fi
    ok "Installing system-wide"
fi

say "Installing project-mri via pip..."
$PYTHON -m pip install "${PIP_ARGS[@]}" --upgrade project-mri

# ---------- verify ----------
if ! command -v mri >/dev/null 2>&1; then
    warn "mri not in PATH. You may need to add ~/.local/bin to your PATH:"
    warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    warn "(add this to your ~/.bashrc or ~/.zshrc to make it permanent)"
fi

ok "project-mri installed successfully"
echo
say "Next steps:"
say "  1. Run 'mri init' to create the admin user and config."
say "  2. Run 'mri serve' to start the API + dashboard."
say "  3. Open http://localhost:7331/dashboard/ in your browser."
echo
say "Docs:  https://github.com/project-mri/project-mri/blob/main/README.md"
say "Help:  mri --help"
