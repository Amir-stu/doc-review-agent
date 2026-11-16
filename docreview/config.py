"""Tunable defaults. Values marked with an env var can be overridden without code changes."""

import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STEPS_DIR = PROJECT_ROOT / "steps"
RUNS_DIR = Path(os.environ.get("DOCREVIEW_RUNS_DIR", PROJECT_ROOT / "runs"))

SUPPORTED_SUFFIXES = (".pptx", ".docx", ".xlsx")

# Subagents (headless `claude -p`).
LANGUAGE_MODEL = os.environ.get("DOCREVIEW_LANGUAGE_MODEL", "sonnet")
CONSISTENCY_MODEL = os.environ.get("DOCREVIEW_CONSISTENCY_MODEL", "sonnet")
AGENT_BUDGET_USD = 0.5
AGENT_TIMEOUT_SECONDS = 300
MAX_PARALLEL_AGENTS = int(os.environ.get("DOCREVIEW_MAX_PARALLEL", "4"))
AGENT_ATTEMPTS = 2
# Agents run outside the user's home so personal CLAUDE.md files are not loaded.
SANDBOX_DIR = Path(
    os.environ.get(
        "DOCREVIEW_SANDBOX",
        Path(os.environ.get("PUBLIC", tempfile.gettempdir())) / "docreview-sandbox",
    )
)
# Upper bound on text sent to the cross-document consistency agent.
CONSISTENCY_MAX_CHARS = 60_000

# Correction loop (step 06a).
MAX_CORRECTION_ROUNDS = 2

# PowerPoint overflow estimate (step 03b). See checks/file_specific.py.
EMU_PER_POINT = 12_700
AVERAGE_CHAR_WIDTH_EM = 0.5
LINE_HEIGHT_FACTOR = 1.2
DEFAULT_FONT_SIZE_PT = 18.0
TEXTBOX_INSET_PT = 7.2
OVERFLOW_TOLERANCE = 1.05

# Word: a fully bold Normal paragraph shorter than this looks like a manual heading.
MANUAL_HEADING_MAX_CHARS = 80

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
