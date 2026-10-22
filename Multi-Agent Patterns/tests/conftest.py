"""Every test runs offline and at full speed, and writes its run logs, checkpoints and price feed to a temp folder,
not your own output/. Set before lab is imported; .env never overrides these, and the run.py subprocesses
the lab server starts inherit them."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["LAB_LLM"] = "offline"
os.environ["LAB_DELAY"] = "0"
os.environ["LAB_OUTPUT"] = tempfile.mkdtemp(prefix="multi-agent-patterns-tests-")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
