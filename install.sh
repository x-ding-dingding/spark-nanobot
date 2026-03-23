#!/usr/bin/env bash
# install.sh — One-step nanobot setup
#
# What this script does:
#   1. Checks Python version (≥ 3.11 required)
#   2. Installs nanobot via pip
#   3. Copies config.example.json → config.json (if not already present)
#   4. Copies workspace/*.md.example → workspace/*.md (if not already present)
#   5. Prompts to initialize a work directory (optional)
#   6. Reminds you to fill in API keys

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors ────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${CYAN}ℹ  $*${RESET}"; }
success() { echo -e "${GREEN}✓  $*${RESET}"; }
warn()    { echo -e "${YELLOW}⚠  $*${RESET}"; }
error()   { echo -e "${RED}✗  $*${RESET}"; exit 1; }

# Try pip install against default index first, then multiple CN mirrors.
# Usage:
#   pip_install_with_fallback "<desc>" <pip args...>
pip_install_with_fallback() {
    local desc="$1"
    shift

    local -a mirrors=(
        "https://pypi.tuna.tsinghua.edu.cn/simple|pypi.tuna.tsinghua.edu.cn|TUNA"
        "https://pypi.mirrors.ustc.edu.cn/simple|pypi.mirrors.ustc.edu.cn|USTC"
        "https://mirrors.aliyun.com/pypi/simple|mirrors.aliyun.com|Aliyun"
    )

    info "Installing ${desc} from default index..."
    if "$PYTHON_BIN" -m pip install \
        --retries 5 \
        --timeout 60 \
        "$@" --quiet; then
        success "Installed ${desc} from default index"
        return 0
    fi

    warn "Default index failed. Trying domestic mirrors..."
    local m index host name
    for m in "${mirrors[@]}"; do
        IFS='|' read -r index host name <<< "$m"
        info "Trying ${name} mirror..."
        if "$PYTHON_BIN" -m pip install \
            --retries 5 \
            --timeout 60 \
            -i "$index" \
            --trusted-host "$host" \
            "$@" --quiet; then
            success "Installed ${desc} via ${name} mirror"
            return 0
        fi
    done

    error "Failed to install ${desc}. Please check network/proxy settings and retry."
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🤖  nanobot installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Step 1: Check Python version ──────────────────────────────────────────────

info "Checking Python version..."

PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        VERSION=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        MAJOR=$(echo "$VERSION" | cut -d. -f1)
        MINOR=$(echo "$VERSION" | cut -d. -f2)
        if [[ "$MAJOR" -ge 3 && "$MINOR" -ge 11 ]]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    error "Python 3.11 or higher is required. Please install it and re-run this script."
fi

success "Python $($PYTHON_BIN --version | awk '{print $2}') found"

# ── Step 2: Install nanobot ───────────────────────────────────────────────────

echo ""
info "Installing nanobot..."

if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    # Running from source — prefer editable mode so CLI points to this repo.
    if "$PYTHON_BIN" -m pip install -e "$SCRIPT_DIR" --retries 5 --timeout 60 --quiet; then
        # Some macOS setups may mark generated .pth files as hidden; unhide it
        # so Python loads editable path mapping reliably.
        PTH_FILE="$("$PYTHON_BIN" -c 'import site; from pathlib import Path; p=[]; [p.extend(Path(d).glob("*nanobot*.pth")) for d in site.getsitepackages() if Path(d).exists()]; print(p[0] if p else "")' 2>/dev/null || true)"
        if [[ -n "${PTH_FILE:-}" && -f "$PTH_FILE" ]]; then
            chflags nohidden "$PTH_FILE" 2>/dev/null || true
        fi
        success "Installed nanobot from source (editable mode)"
    else
        warn "Editable install failed. Retrying with non-editable install..."
        pip_install_with_fallback "nanobot from source (non-editable mode)" "$SCRIPT_DIR"
    fi
else
    # pip_install_with_fallback "nanobot from PyPI" "nanobot"
fi

# ── Step 3: Copy config template ─────────────────────────────────────────────

echo ""
info "Setting up config.json..."

CONFIG_FILE="$SCRIPT_DIR/config.json"
CONFIG_EXAMPLE="$SCRIPT_DIR/config.example.json"

if [[ -f "$CONFIG_FILE" ]]; then
    warn "config.json already exists — skipping (your existing config is untouched)"
else
    if [[ -f "$CONFIG_EXAMPLE" ]]; then
        cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
        success "Created config.json from config.example.json"
    else
        warn "config.example.json not found — skipping config setup"
    fi
fi

# ── Step 4: Copy workspace templates ─────────────────────────────────────────

echo ""
info "Setting up workspace files..."

WORKSPACE_DIR="$SCRIPT_DIR/workspace"
WORKSPACE_FILES=("SOUL.md" "USER.md" "AGENTS.md" "TOOLS.md" "HEARTBEAT.md")

for filename in "${WORKSPACE_FILES[@]}"; do
    target="$WORKSPACE_DIR/$filename"
    template="$WORKSPACE_DIR/$filename.example"
    if [[ -f "$target" ]]; then
        warn "$filename already exists — skipping"
    elif [[ -f "$template" ]]; then
        cp "$template" "$target"
        success "Created workspace/$filename"
    else
        warn "$filename.example not found — skipping"
    fi
done

# Copy memory/MEMORY.md from example if not present
MEMORY_TARGET="$WORKSPACE_DIR/memory/MEMORY.md"
MEMORY_TEMPLATE="$WORKSPACE_DIR/memory/MEMORY.md.example"
mkdir -p "$WORKSPACE_DIR/memory"
if [[ -f "$MEMORY_TARGET" ]]; then
    warn "memory/MEMORY.md already exists — skipping"
elif [[ -f "$MEMORY_TEMPLATE" ]]; then
    cp "$MEMORY_TEMPLATE" "$MEMORY_TARGET"
    success "Created workspace/memory/MEMORY.md"
else
    warn "memory/MEMORY.md.example not found — skipping"
fi

# ── Step 5: Initialize work directory ────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📁  Work Directory Setup (optional)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  A work directory stores your project notes, daily logs,"
echo "  and knowledge base. Skills like daily-dump and todo-coach"
echo "  use it automatically."
echo ""
read -r -p "  Set up a work directory now? [Y/n]: " SETUP_WORKDIR
SETUP_WORKDIR="${SETUP_WORKDIR:-Y}"

if [[ "$SETUP_WORKDIR" =~ ^[Yy]$ ]]; then
    DEFAULT_WORKDIR="$SCRIPT_DIR/workdir"
    echo ""
    echo "  Default location: $DEFAULT_WORKDIR"
    read -r -p "  Path (or Enter for default): " USER_WORKDIR_INPUT
    if [[ -z "$USER_WORKDIR_INPUT" ]]; then
        WORKDIR_PATH="$DEFAULT_WORKDIR"
    else
        WORKDIR_PATH="${USER_WORKDIR_INPUT/#\~/$HOME}"
    fi

    bash "$SCRIPT_DIR/init_workdir.sh" "$WORKDIR_PATH"
else
    echo ""
    info "Skipped. You can run ./init_workdir.sh at any time to set up a work directory."
    info "Then set tools.workDir in config.json to the path."
fi

# ── Step 6: Remind about API keys ────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🔑  Next Steps"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  1. Open config.json and fill in your API keys:"
echo "     - At minimum, add one LLM provider key (e.g. openrouter or anthropic)"
echo "     - Enable and configure any chat channels you want to use"
echo ""
echo "  2. Customize your workspace:"
echo "     - workspace/SOUL.md    — your assistant's personality"
echo "     - workspace/USER.md    — your profile and preferences"
echo "     - workspace/AGENTS.md  — behavioral guidelines"
echo ""
echo "  3. Start chatting:"
echo ""
echo "     ./nb gateway               # one-command launcher (local env)"
echo "     ./nb agent                 # interactive CLI (local env)"
echo ""
echo "     nanobot agent              # interactive CLI"
echo "     nanobot agent -m 'Hello!'  # single message"
echo "     nanobot gateway            # start all channels"
echo ""
echo "  📖  Full docs: https://github.com/x-ding-dingding/cyper_bot"
echo ""
success "Installation complete! Happy hacking 🚀"
echo ""


# source /Users/xiongmengjun/Desktop/program/spark-nanobot/.miniconda3/bin/activate /Users/xiongmengjun/Desktop/program/spark-nanobot/.py311
# python -c "import nanobot; print(nanobot.__file__)"
