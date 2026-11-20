"""Builds the page and the data file from the stored data:  python3 -I build.py [DATA_DIR] [OUT_DIR]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observatory.build import main  # noqa: E402

main(sys.argv)
