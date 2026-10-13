"""Download the matched native755 graph candidate without selecting old data."""
import argparse
import json
from pathlib import Path

from download_single import install


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = Path(__file__).resolve().parents[1] / "native755_data.json"
    install(args.output_dir, json.loads(manifest.read_text()))


if __name__ == "__main__":
    main()
