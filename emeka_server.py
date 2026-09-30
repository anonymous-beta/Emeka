#!/data/data/com.termux/files/usr/bin/python
"""
EMEKA MCP Server — 14 rootless tools giving an MCP AI full Termux autonomy.
Stdio transport. Author: Anonymous-beta (Chinedu)
"""

import os
import shutil
import tarfile
import zipfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from emeka_core import (WORKSPACE, ensure_workspace, resolve_in_workspace,
                        run_process, check_command_safety, load_config,
                        log_event)

ensure_workspace()
cfg = load_config()

mcp = FastMCP(
    "EMEKA",
    instructions=(
        "EMEKA: rootless AI control of a Termux (Android) environment.\n"
        f"Everything operates inside the workspace jail: {WORKSPACE}\n"
        "Workflow: pkg_install for system deps -> git_clone the project ->\n"
        "build_project -> run. Use `shell` for anything the dedicated tools lack.\n"
        "Files: read_file / write_file / list_dir / search_files / tree.\n"
        "Android extras: termux_api (notifications, tts, battery, clipboard).\n"
        "Avoid destructive commands; never attempt root/su."
    ),
)


def _cap(r: dict) -> dict:
    lim = cfg.get("max_output_chars", 20000)
    if len(r.get("stdout", "")) > lim:
        r["stdout"] = r["stdout"][:lim]
        r["truncated"] = True
    return r


# ------------------------------------------------------------ 1. shell
@mcp.tool()
async def shell(command: str, timeout: int = 300) -> dict:
    """Run an arbitrary rootless bash command inside Termux.
    Examples: 'ls -la', 'python script.py', 'npm test', 'curl -s https://x.sh | bash'.
    Dangerous system-destroying patterns are blocked."""
    reason = check_command_safety(command)
    if reason:
        return {"ok": False, "stderr": reason}
    return _cap(run_process(["bash", "-lc", command],
                            timeout=min(max(timeout, 5), 1800)))


# ------------------------------------------------------------ 2-4. packages
@mcp.tool()
async def pkg_search(query: str) -> dict:
    """Search Termux packages: pkg_search('python')."""
    return _cap(run_process(["pkg", "search", query], timeout=120))


@mcp.tool()
async def pkg_install(packages: list[str]) -> dict:
    """Install Termux package(s), e.g. ["nodejs","clang","rust"]. Non-interactive."""
    if not packages:
        return {"ok": False, "stderr": "No packages given."}
    return _cap(run_process(["pkg", "install", "-y", *packages], timeout=1200))


@mcp.tool()
async def pkg_list_installed() -> dict:
    """List all installed Termux packages."""
    return _cap(run_process(["bash", "-lc", "dpkg -l | awk '/^ii/{print $2, $3}'"], timeout=120))


# ------------------------------------------------------------ 5. pip
@mcp.tool()
async def pip_install(packages: list[str]) -> dict:
    """pip install package(s), e.g. ["flask","rich"]. Use for Python deps."""
    if not packages:
        return {"ok": False, "stderr": "No packages given."}
    return _cap(run_process(["pip", "install", *packages], timeout=1200))


# ------------------------------------------------------------ 6. git
@mcp.tool()
async def git_clone(url: str, name: str = "", full_history: bool = False) -> dict:
    """git clone a repository into the workspace (shallow by default).
    Returns the local path under the workspace jail."""
    ensure_workspace()
    name = name or Path(url.rstrip("/")).name.replace(".git", "") or "repo"
    target, err = resolve_in_workspace(name)
    if err:
        return {"ok": False, "stderr": err}
    if target.exists() and any(target.iterdir()):
        return {"ok": True, "path": str(target), "note": "Already exists; not re-cloned."}
    cmd = ["git", "clone"] + ([] if full_history else ["--depth", "1"]) + [url, str(target)]
    r = _cap(run_process(cmd, timeout=1200))
    r["path"] = str(target)
    return r


@mcp.tool()
async def git_action(repo_path: str, action: str, args: str = "") -> dict:
    """Run a git subcommand in a workspace repo.
    action: pull|log|status|branch|checkout|commit|push|diff  args: extra flags."""
    repo, err = resolve_in_workspace(repo_path)
    if err:
        return {"ok": False, "stderr": err}
    if not (repo / ".git").exists():
        return {"ok": False, "stderr": f"Not a git repo: {repo}"}
    if action not in ("pull", "log", "status", "branch", "checkout",
                      "commit", "push", "diff", "add", "init"):
        return {"ok": False, "stderr": f"Disallowed git action: {action}"}
    extra = args.split() if args else []
    return _cap(run_process(["git", action, *extra], timeout=300, cwd=repo))


# ------------------------------------------------------------ 7. build
@mcp.tool()
async def build_project(path: str) -> dict:
    """Detect the build system of a workspace project and build it.
    Supports: requirements.txt, pyproject/setup.py, package.json, Makefile,
    CMake, Cargo, Go, gradlew. Runs steps in order; stops at first failure."""
    root, err = resolve_in_workspace(path)
    if err:
        return {"ok": False, "stderr": err}
    if not root.is_dir():
        return {"ok": False, "stderr": f"Not a directory: {root}"}

    steps: list[list[str]] = []
    has = lambda f: (root / f).exists()
    if has("requirements.txt"):
        steps.append(["pip", "install", "-r", "requirements.txt"])
    if has("pyproject.toml") or has("setup.py"):
        steps.append(["pip", "install", "-e", "."])
    if has("package.json"):
        steps.append(["npm", "install"])
    if has("Cargo.toml"):
        steps.append(["cargo", "build", "--release"])
    if has("go.mod"):
        steps.append(["go", "build", "./..."])
    if has("CMakeLists.txt"):
        steps.append(["bash", "-lc", "cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j$(nproc)"])
    if has("Makefile"):
        steps.append(["make"])
    if has("gradlew"):
        steps.append(["bash", "-lc", "chmod +x gradlew && ./gradlew build"])
    if not steps:
        return {"ok": False, "stderr": "No known build system detected.", "path": str(root)}

    results = []
    for step in steps:
        r = _cap(run_process(step, timeout=1800, cwd=root))
        results.append({"cmd": " ".join(step), **r})
        if not r["ok"]:
            return {"ok": False, "path": str(root), "failed_step": " ".join(step), "results": results}
    return {"ok": True, "path": str(root), "results": results}


# ------------------------------------------------------------ 8. run
@mcp.tool()
async def run_program(path: str, program: str = "", args: str = "",
                      timeout: int = 120) -> dict:
    """Run a program inside the workspace and capture output.
    Auto-detects python/node if `program` is empty:
    *.py -> python, package.json main -> node, binary -> execute directly."""
    root, err = resolve_in_workspace(path)
    if err:
        return {"ok": False, "stderr": err}
    target = root / program if program else root
    if not target.exists():
        return {"ok": False, "stderr": f"Not found: {target}"}

    extra = args.split() if args else []
    if target.is_file():
        if target.suffix == ".py":
            cmd = ["python", str(target), *extra]
        elif target.suffix == ".js":
            cmd = ["node", str(target), *extra]
        elif target.suffix in (".sh",):
            cmd = ["bash", str(target), *extra]
        else:
            cmd = [str(target), *extra]
    else:
        if (target / "package.json").exists():
            cmd = ["npm", "start", *extra]
        elif (target / "Makefile").exists():
            cmd = ["make", "run", *extra]
        else:
            return {"ok": False, "stderr": "Directory has no runnable entry (package.json/Makefile). "
                                           "Use `shell` with an explicit command."}
    return _cap(run_process(cmd, timeout=min(max(timeout, 5), 900), cwd=target if target.is_dir() else target.parent))


# ------------------------------------------------------------ 9-12. files
@mcp.tool()
async def read_file(path: str, offset: int = 0, max_lines: int = 2000) -> dict:
    """Read a text file (workspace-relative or absolute read-only). Paginate with offset."""
    f, err = resolve_in_workspace(path, allow_outside_read=True)
    if err:
        return {"ok": False, "stderr": err}
    try:
        if f.stat().st_size > 5_000_000:
            return {"ok": False, "stderr": "File too large (>5MB); read in chunks via offset on smaller slices."}
        lines = f.read_text(errors="replace").splitlines()
    except Exception as e:
        return {"ok": False, "stderr": str(e)}
    slice_ = lines[offset:offset + max_lines]
    return {"ok": True, "path": str(f), "content": "\n".join(slice_),
            "offset": offset, "lines_returned": len(slice_),
            "total_lines": len(lines), "more": offset + max_lines < len(lines)}


@mcp.tool()
async def write_file(path: str, content: str) -> dict:
    """Create/overwrite a text file inside the workspace. Parent dirs auto-created."""
    f, err = resolve_in_workspace(path)
    if err:
        return {"ok": False, "stderr": err}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
        log_event("file", f"wrote {f} ({len(content)} bytes)")
        return {"ok": True, "path": str(f), "bytes": len(content)}
    except Exception as e:
        return {"ok": False, "stderr": str(e)}


@mcp.tool()
async def list_dir(path: str = ".") -> dict:
    """List directory contents (workspace-relative or absolute read-only)."""
    d, err = resolve_in_workspace(path, allow_outside_read=True)
    if err:
        return {"ok": False, "stderr": err}
    if not d.is_dir():
        return {"ok": False, "stderr": f"Not a directory: {d}"}
    items = []
    for p in sorted(d.iterdir())[:1000]:
        try:
            items.append({"name": p.name, "type": "dir" if p.is_dir() else "file",
                          "size": p.stat().st_size if p.is_file() else None})
        except OSError:
            continue
    return {"ok": True, "path": str(d), "count": len(items), "items": items}


@mcp.tool()
async def tree(path: str = ".", depth: int = 3) -> dict:
    """Recursive directory tree of a workspace path (bounded depth, ignores .git/node_modules)."""
    root, err = resolve_in_workspace(path, allow_outside_read=True)
    if err:
        return {"ok": False, "stderr": err}
    skip = {".git", "node_modules", "__pycache__", ".venv", "build", "dist", "target"}
    lines: list[str] = [str(root)]

    def walk(d: Path, level: int) -> None:
        if level > min(depth, 6):
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name))
        except OSError:
            return
        for e in entries[:100]:
            if e.name in skip:
                continue
            lines.append(("  " * level) + ("├─ " + e.name) + ("/" if e.is_dir() else ""))
            if e.is_dir():
                walk(e, level + 1)

    if root.is_dir():
        walk(root, 1)
    return {"ok": True, "tree": "\n".join(lines[:2000])}


# ------------------------------------------------------------ 13. search
@mcp.tool()
async def search_files(path: str, query: str, is_regex: bool = False) -> dict:
    """ripgrep search of file contents under a workspace path."""
    d, err = resolve_in_workspace(path, allow_outside_read=True)
    if err:
        return {"ok": False, "stderr": err}
    if not shutil.which("rg"):
        return {"ok": False, "stderr": "ripgrep missing. Run: pkg install ripgrep"}
    cmd = ["rg", "-n", "--max-count", "40", "--"] if not is_regex else \
          ["rg", "-n", "--max-count", "40", "-e"]
    return _cap(run_process([*cmd, query, str(d)], timeout=120))


# ------------------------------------------------------------ 14. android
@mcp.tool()
async def termux_api(action: str, text: str = "", title: str = "EMEKA") -> dict:
    """Android integration via termux-api app (requires the Termux:API addon).
    actions: notify | tts | battery | clipboard_get | vibrate
    e.g. termux_api('notify', text='Build finished', title='EMEKA')."""
    if not shutil.which("termux-notification") and action != "battery":
        return {"ok": False, "stderr": "termux-api missing. pkg install termux-api + install the Termux:API app."}
    if action == "notify":
        return _cap(run_process(["termux-notification", "--title", title, "--content", text or "EMEKA event"], timeout=30))
    if action == "tts":
        return _cap(run_process(["termux-tts-speak", text], timeout=60))
    if action == "battery":
        return _cap(run_process(["termux-battery-status"], timeout=30))
    if action == "clipboard_get":
        return _cap(run_process(["termux-clipboard-get"], timeout=30))
    if action == "vibrate":
        return _cap(run_process(["termux-vibrate", "-d", "500"], timeout=30))
    return {"ok": False, "stderr": f"Unknown action: {action}"}


# ------------------------------------------------------------ bonus: backup
@mcp.tool()
async def backup_workspace(name: str = "") -> dict:
    """Tar.gz the whole workspace into ~/.emeka/backups/ and return the archive path."""
    ensure_workspace()
    bdir = Path(os.environ.get("HOME", "")) / ".emeka" / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    import time as _t
    archive = bdir / (name or f"emeka_backup_{_t.strftime('%Y%m%d_%H%M%S')}.tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(WORKSPACE, arcname="emeka_workspace")
    return {"ok": True, "archive": str(archive), "size": archive.stat().st_size}


if __name__ == "__main__":
    log_event("server", "EMEKA MCP server starting (stdio)")
    mcp.run()
