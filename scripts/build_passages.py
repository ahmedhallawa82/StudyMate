"""Step 1: extract the lecture slides into data/AI/passages.csv.

Run from the project folder:  python scripts/build_passages.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.passages import build_passages

if __name__ == "__main__":
    print("Building passages from lecture PDFs ...")
    df = build_passages()
    print(df.groupby("topic").size().to_string())
