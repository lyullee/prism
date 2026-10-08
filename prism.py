"""Repository-local PRISM launcher for standard and optional LH2 analysis."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'lh2-tno/src'))
from tno_host import main

if __name__ == '__main__':
    raise SystemExit(main())
