"""Regenerate the demo events' posters and banners.

Run:  python tools/make_posters.py
Real event artwork from organizers replaces these later.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.posters import write_art  # noqa: E402

APP = ROOT / "app"


def main():
    for e in json.loads((APP / "data" / "events.json").read_text(encoding="utf-8")):
        write_art(e, APP / "static")
        print("wrote", e["slug"])


if __name__ == "__main__":
    main()
