#!/data/data/com.termux/files/usr/bin/python
"""
EMEKA Core — shared infrastructure.
Config store, workspace jail, hardened process runner, event log.
Author: Anonymous-beta (Chinedu)
"""

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

# ---------------------------------------------------------------- paths
TERMUX_PREFIX = Path("/data/data/com.termux/files/usr")
HOME = Path(os.environ.get("HOME", "/data/data/com.termux/files/home"))
CONFIG_DIR = HOME / ".emeka"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "emeka.log"
WORKSPACE = HOME / "emeka_workspace"

PROVIDERS = {
    "openai":     {"base_url": "https://api.openai.com/v1",        "model": "gpt-4o"},
    "anthropic":  {"base_url": "https://api.anthropic.com",        "model": "claude-sonnet-4-5"},
    "groq":       {"base_url": "https://api.groq.com/openai/v1",   "model": "llama-3.3-70b-versatile"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1",     "model": "anthropic/claude-sonnet-4.5"},
    "together":   {"base_url": "https://api.together.xyz/v1",      "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo"},
    "ollama":     {"base_url": "http://127.0.0.1:11434/v1",        "model": "llama3.2"},
    "custom":     {"base_url": "",                                 "model": ""},
}

DEFAULT_CONFIG = {
    "provider": "openai",
    "api_key": "",
    "base_url": PROVIDERS["openai"]["base_url"],
    "model": PROVIDERS["openai"]["model"],
    "max_output_chars": 20000,
    "default_timeout": 300,
}

# ---------------------------------------------------------------- config
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    os.chmod(CONFIG_FILE, 0o600)
    LOG_FILE.touch(mode=0o600, exist_ok=True)


def log_event(source: str, message: str) -> None:
    """Append a timestamped line to ~/.emeka/emeka.log (readable only by owner)."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a") as fh:
            fh.write(f"[{ts}] [{source}] {message}\n")
    except OSError:
        pass


# ---------------------------------------------------------------- workspace jail
def ensure_workspace() -> Path:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return WORKSPACE


def resolve_in_workspace(path: str, allow_outside_read: bool = False) -> tuple[Path | None, str | None]:
    """
    Resolve `path` against the workspace. Returns (resolved_path, error).
    Writes/builds/clones MUST stay inside the workspace. Reads may escape
    only if allow_outside_read=True (still never /data/data outside Termux user files).
    """
    if not path or not isinstance(path, str):
        return None, "Empty or invalid path."
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE / p
    p = p.resolve()
    inside = str(p).startswith(str(WORKSPACE) + os.sep) or p == WORKSPACE
    if not inside and not allow_outside_read:
        return None, f"Path escapes the EMEKA workspace jail: {p}\nWorkspace: {WORKSPACE}"
    if not inside and allow_outside_read:
        # block sensitive system dirs even for reads
        blocked = ("/data/data/com.termux.files/usr/etc", "/system", "/proc", "/sys", "/dev")
        if any(str(p).startswith(b) for b in blocked):
            return None, f"Access to protected path denied: {p}"
    return p, None


# ---------------------------------------------------------------- process runner
DANGEROUS_PATTERNS = (
    "rm -rf /", "rm -rf /*", "rm -fr /", "mkfs", ":(){", "fork bomb",
    "> /dev/block", "dd if=/dev/", "chmod -R 777 /", "reboot", "shutdown",
    "su -c", "/system/bin", "settings put", "pm disable", "flash_image",
)


def check_command_safety(command: str) -> str | None:
    """Return a rejection reason, or None if acceptable."""
    low = command.lower()
    for pat in DANGEROUS_PATTERNS:
        if pat.lower() in low:
            return f"Blocked dangerous pattern: {pat!r}"
    return None


def run_process(cmd: list[str], timeout: int = 300, cwd: Path | None = None,
                max_chars: int = 20000) -> dict:
    """
    Hardened subprocess runner. Never uses shell=True; always injects a
    non-interactive environment. Returns structured dict.
    """
    ensure_workspace()
    cwd = cwd or WORKSPACE
    env = {**os.environ,
           "TERM": "dumb", "DEBIAN_FRONTEND": "noninteractive",
           "NONINTERACTIVE": "1", "CI": "1",
           "PATH": f"{TERMUX_PREFIX}/bin:{os.environ.get('PATH', '')}",
           "HOME": str(HOME)}
    started = time.time()
    try:
        proc = subprocess.run(
            [str(c) for c in cmd],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(cwd), env=env, shell=False,
        )
        out = proc.stdout[:max_chars]
        err = proc.stderr[:max_chars // 2]
        result = {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": out,
            "stderr": err,
            "duration_sec": round(time.time() - started, 2),
            "cwd": str(cwd),
            "truncated": len(proc.stdout) > max_chars,
        }
    except subprocess.TimeoutExpired as e:
        result = {"ok": False, "returncode": -1,
                  "stdout": (e.stdout or "")[:max_chars] if isinstance(e.stdout, str) else "",
                  "stderr": f"TIMEOUT after {timeout}s",
                  "duration_sec": round(time.time() - started, 2),
                  "cwd": str(cwd), "truncated": False}
    except FileNotFoundError:
        result = {"ok": False, "returncode": 127, "stdout": "",
                  "stderr": f"Command not found: {shlex.join(cmd)}",
                  "duration_sec": 0, "cwd": str(cwd), "truncated": False}
    log_event("proc", f"rc={result.get('returncode')} dur={result['duration_sec']}s cmd={shlex.join(cmd)[:200]}")
    return result
