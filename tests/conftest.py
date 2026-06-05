import sys
from pathlib import Path

# Ensure imports like `from data.mock_data ...` work during pytest collection.
# Project layout expects packages under `src/`.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
