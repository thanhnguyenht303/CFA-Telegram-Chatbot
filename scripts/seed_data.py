from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cfa_vocab_bot.__main__ import _seed

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(Path("data") / "seed_vocab.json")
    _seed(path)

