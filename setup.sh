#!/data/data/com.termux/files/usr/bin/bash
# EMEKA installer (rootless) — Author: Anonymous-beta (Chinedu)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "  ███████╗███╗   ███╗███████╗██╗  ██╗ █████╗ "
echo "  ██╔════╝████╗ ████║██╔════╝██║ ██╔╝██╔══██╗"
echo "  █████╗  ██╔████╔██║█████╗  █████╔╝ ███████║"
echo "  ██╔══╝  ██║╚██╔╝██║██╔══╝  ██╔═██╗ ██╔══██║"
echo "  ███████╗██║ ╚═╝ ██║███████╗██║  ██╗██║  ██║"
echo "  ╚══════╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝"
echo "  Rootless Termux MCP Server — Anonymous-beta (Chinedu)"; echo

echo "[*] pkg update/upgrade…"
pkg update -y && pkg upgrade -y || true

echo "[*] Installing system deps…"
pkg install -y python git clang make cmake pkg-config openssl binutils \
  ripgrep jq curl wget termux-api nodejs-lts

echo "[*] Installing Python deps…"
pip install --upgrade pip
pip install -r "$HERE/requirements.txt"

chmod +x "$HERE/emeka.py" "$HERE/emeka_server.py" "$HERE/uninstall.sh"

echo "[*] Verifying stack…"
python - <<'PY'
import importlib
for mod in ("textual", "rich", "mcp"):
    importlib.import_module(mod)
print("[+] All Python dependencies import cleanly.")
PY
python -c "import sys; sys.path.insert(0,'$HERE'); import emeka_core; emeka_core.ensure_workspace(); print('[+] Workspace jail OK:', emeka_core.WORKSPACE)"

echo
echo "[+] EMEKA installed."
echo "    TUI:            python $HERE/emeka.py"
echo "    MCP server:     python $HERE/emeka_server.py"
echo "    Optional: install the Termux:API app from F-Droid for Android tools."
