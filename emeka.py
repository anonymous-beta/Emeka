#!/data/data/com.termux/files/usr/bin/python
"""
EMEKA TUI — configure AI API, generate client configs, run/observe server.
Keys: s=start/stop  g=generate client config  l=tail log  c=clear  q=quit
Author: Anonymous-beta (Chinedu)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from emeka_core import CONFIG_FILE, LOG_FILE, PROVIDERS, load_config, save_config

SERVER_SCRIPT = Path(__file__).resolve().parent / "emeka_server.py"

BANNER = (
    "[bold cyan]"
    " ███████╗███╗   ███╗███████╗██╗  ██╗ █████╗ \n"
    " ██╔════╝████╗ ████║██╔════╝██║ ██╔╝██╔══██╗\n"
    " █████╗  ██╔████╔██║█████╗  █████╔╝ ███████║\n"
    " ██╔══╝  ██║╚██╔╝██║██╔══╝  ██╔═██╗ ██╔══██║\n"
    " ███████╗██║ ╚═╝ ██║███████╗██║  ██╗██║  ██║\n"
    " ╚══════╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝\n"
    "[/bold cyan][dim] Rootless Termux MCP Server · by Anonymous-beta (Chinedu) [/dim]"
)

CLIENT_TARGETS = {
    "claude":  "~/.claude/claude_desktop_config.json",   # reference path
    "cursor":  "~/.cursor/mcp.json",
    "cline":   "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
}


def build_mcp_config(python_bin: str, server_path: str) -> dict:
    return {"mcpServers": {"emeka": {"command": python_bin, "args": [server_path]}}}


class EmekaApp(App):
    CSS = """
    Screen { background: $surface; }
    #banner { height: 9; padding: 0 1; }
    #status { height: 3; padding: 0 1; border: round $accent; }
    #form { height: auto; padding: 0 1; }
    Input { margin-bottom: 1; }
    #log { border: round $accent; height: 1fr; }
    """
    TITLE = "EMEKA"
    SUB_TITLE = "Termux MCP Server — Anonymous-beta (Chinedu)"
    BINDINGS = [
        ("s", "toggle_server", "Start/Stop Server"),
        ("g", "generate_config", "Generate Client Config"),
        ("l", "tail_log", "Tail emeka.log"),
        ("c", "clear_log", "Clear Log"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cfg = load_config()
        self.server_proc: subprocess.Popen | None = None
        self._tail_running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(BANNER, id="banner")
        with Vertical(id="form"):
            yield Input(id="provider", placeholder="Provider (openai/anthropic/groq/openrouter/together/ollama/custom)",
                        value=self.cfg["provider"])
            yield Input(id="api_key", placeholder="API key (stored chmod 600)", value=self.cfg["api_key"], password=True)
            yield Input(id="base_url", placeholder="Base URL", value=self.cfg["base_url"])
            yield Input(id="model", placeholder="Model", value=self.cfg["model"])
        yield Static("[yellow]● SERVER STOPPED[/yellow] — [b]s[/b] start · [b]g[/b] gen client config · [b]l[/b] tail log", id="status")
        yield RichLog(highlight=True, markup=True, id="log")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("[bold cyan]EMEKA ready.[/bold cyan] Set your AI API fields and press Enter to save.")
        log.write(f"[dim]Server: {SERVER_SCRIPT}[/dim]")
        log.write("[dim]Workspace jail: ~/emeka_workspace[/dim]")

    # ------------------------------------------------------------ helpers
    def _collect_form(self) -> None:
        for wid in ("provider", "api_key", "base_url", "model"):
            self.cfg[wid] = self.query_one(f"#{wid}", Input).value.strip()
        preset = PROVIDERS.get(self.cfg["provider"])
        if preset:
            self.cfg["base_url"] = self.cfg["base_url"] or preset["base_url"]
            self.cfg["model"] = self.cfg["model"] or preset["model"]
        save_config(self.cfg)

    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    # ------------------------------------------------------------ events
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "provider":
            preset = PROVIDERS.get(event.value.strip())
            if preset:
                self.query_one("#base_url", Input).value = preset["base_url"]
                self.query_one("#model", Input).value = preset["model"]

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._collect_form()
        self._log("[green]Config saved → ~/.emeka/config.json (600)[/green]")

    # ------------------------------------------------------------ actions
    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_tail_log(self) -> None:
        if self._tail_running:
            self._tail_running = False
            self._log("[dim]Log tail stopped.[/dim]")
            return
        self._tail_running = True
        self._pump_file_log()

    def _pump_file_log(self) -> None:
        if not self._tail_running:
            return
        if LOG_FILE.exists():
            try:
                lines = LOG_FILE.read_text().splitlines()[-8:]
                for ln in lines:
                    self._log(f"[dim]{ln}[/dim]")
            except OSError:
                pass
        self.set_timer(2.0, self._pump_file_log)

    def action_generate_config(self) -> None:
        self._collect_form()
        cfgjson = build_mcp_config(sys.executable, str(SERVER_SCRIPT))
        out = Path.home() / ".emeka" / "mcp_client_config.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cfgjson, indent=2))
        self._log("[green]Client config written → ~/.emeka/mcp_client_config.json[/green]")
        self._log(json.dumps(cfgjson, indent=2))
        self._log("[dim]Paste into your AI client's MCP settings "
                  "(Cursor: ~/.cursor/mcp.json · Cline: cline_mcp_settings.json · "
                  "Claude Desktop: claude_desktop_config.json).[/dim]")

    def action_toggle_server(self) -> None:
        status = self.query_one("#status", Static)
        if self.server_proc and self.server_proc.poll() is None:
            self.server_proc.terminate()
            try:
                self.server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_proc.kill()
            self.server_proc = None
            status.update("[yellow]● SERVER STOPPED[/yellow]")
            self._log("[yellow]Server stopped.[/yellow]")
            return
        self._collect_form()
        if not SERVER_SCRIPT.exists():
            self._log(f"[red]Missing {SERVER_SCRIPT}[/red]")
            return
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.server_proc = subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        status.update("[green]● SERVER RUNNING (stdio MCP)[/green] — s to stop")
        self._log("[green]Server started on stdio. Connect an MCP client to use it.[/green]")
        self._pump_server_logs()

    def _pump_server_logs(self) -> None:
        proc = self.server_proc
        if not proc:
            return
        if proc.stdout:
            line = proc.stdout.readline()
            if line:
                self._log(line.rstrip())
        if proc.poll() is None:
            self.set_timer(0.4, self._pump_server_logs)
        else:
            self.query_one("#status", Static).update("[red]● SERVER EXITED[/red] — s to restart")
            self._log("[red]Server process exited — check output above.[/red]")

    def action_quit(self) -> None:
        self._tail_running = False
        if self.server_proc and self.server_proc.poll() is None:
            self.server_proc.terminate()
        self.exit()


if __name__ == "__main__":
    EmekaApp().run()
