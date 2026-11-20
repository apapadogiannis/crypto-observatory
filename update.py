"""Downloads the latest data into data/:  python3 update.py [DATA_DIR]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observatory.update import main  # noqa: E402

main(sys.argv)
