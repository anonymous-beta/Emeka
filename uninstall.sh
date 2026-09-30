#!/data/data/com.termux/files/usr/bin/bash
echo "[*] Removing EMEKA (workspace and ~/.emeka kept — delete manually if wanted)."
pip uninstall -y textual rich mcp || true
echo "[+] Done."
