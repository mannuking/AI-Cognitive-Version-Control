#!/usr/bin/env bash
# =============================================================================
# CVC (Cognitive Version Control) — Installer for macOS, Linux & WSL
# Usage:  curl -fsSL https://jaimeena.com/cvc/install.sh | bash
# =============================================================================
set -euo pipefail

PACKAGE="tm-ai[all]"
TOOL_NAME="cvc"
DISPLAY_NAME="CVC — AI Cognitive Version Control"
UV_INSTALL_URL="https://astral.sh/uv/install.sh"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

print_step()  { echo -e "${CYAN}${BOLD}==>${RESET} $1"; }
print_ok()    { echo -e "${GREEN}${BOLD} ✓${RESET}  $1"; }
print_error() { echo -e "${RED}${BOLD} ✗  ERROR:${RESET} $1" >&2; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  ╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}  ║   ${CYAN}${DISPLAY_NAME}${RESET}${BOLD}  ║${RESET}"
echo -e "${BOLD}  ╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1: Check / install uv ────────────────────────────────────────────────
print_step "Checking for uv package manager..."

if command -v uv &>/dev/null; then
    UV_VERSION=$(uv --version 2>&1 | head -1)
    print_ok "uv already installed: ${UV_VERSION}"
else
    print_step "uv not found — installing uv (this will also manage Python for you)..."
    curl -fsSL "$UV_INSTALL_URL" | sh

    # Reload PATH so we can find uv immediately
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

    if ! command -v uv &>/dev/null; then
        print_error "uv installation failed. Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
    print_ok "uv installed successfully"
fi

# ── Step 2: Install / upgrade CVC ─────────────────────────────────────────────
print_step "Installing ${DISPLAY_NAME} from PyPI..."

if uv tool list 2>/dev/null | grep -q "^tm-ai"; then
    print_step "Existing uv-managed installation found — upgrading..."
    uv tool upgrade tm-ai
    print_ok "CVC upgraded to latest version"
else
    uv tool install "$PACKAGE" --python 3.11
    print_ok "CVC installed successfully"
fi

# Ensure uv's tool bin directory is on PATH
uv tool update-shell 2>/dev/null || true

# ── Step 3: Verify ────────────────────────────────────────────────────────────
print_step "Verifying installation..."

# Try to find cvc — may require a new shell if PATH not yet updated
if command -v "$TOOL_NAME" &>/dev/null; then
    CVC_VERSION=$("$TOOL_NAME" --version 2>&1 | head -1 || echo "(installed)")
    print_ok "${TOOL_NAME} is ready: ${CVC_VERSION}"
else
    # uv tools are put in ~/.local/bin — add it for this session
    export PATH="$HOME/.local/bin:$PATH"
    if command -v "$TOOL_NAME" &>/dev/null; then
        print_ok "${TOOL_NAME} installed. PATH updated for this session."
    else
        echo ""
        echo -e "  ${CYAN}Note:${RESET} Please restart your shell or run:"
        echo -e "    ${BOLD}source ~/.bashrc${RESET}  (bash)"
        echo -e "    ${BOLD}source ~/.zshrc${RESET}   (zsh)"
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  Installation complete!${RESET}"
echo ""
echo -e "  ${BOLD}Quick start:${RESET}"
echo -e "    ${CYAN}cvc --help${RESET}              Show all commands"
echo -e "    ${CYAN}cvc init${RESET}                Initialize CVC in your project"
echo -e "    ${CYAN}cvc launch claude${RESET}        Launch Claude Code with time-machine"
echo ""
echo -e "  ${BOLD}Docs:${RESET}  https://jaimeena.com/cvc"
echo -e "  ${BOLD}Repo:${RESET}  https://github.com/mannuking/AI-Cognitive-Version-Control"
echo ""
