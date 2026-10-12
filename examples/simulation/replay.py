import sys
from pathlib import Path
sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "_replay"))
from investigator.replay import verify
verify(root)
