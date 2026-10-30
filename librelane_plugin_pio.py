"""Register the opt-in audited PIO flow; src/config.json selects the active flow."""
from pathlib import Path
import sys

_timing_tools = str(Path(__file__).resolve().parent/'tools/timing')
sys.path.insert(0, _timing_tools)
from production_flow import PIOClosure  # noqa: E402,F401
sys.path.remove(_timing_tools)
