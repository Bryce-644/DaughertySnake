import pathlib
import sys

# Make main.py importable from tests/ regardless of how pytest is invoked.
sys.path.insert(0, str(pathlib.Path(__file__).parent))
