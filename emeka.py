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

from emeka_core import (CONFIG_FILE, LOG_FILE, PROVIDERS, SERVER_DIR if False else None)  # noqa
