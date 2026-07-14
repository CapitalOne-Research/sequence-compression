import sys
from pathlib import Path

# Put the repo root on sys.path so `import c1...` works without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
