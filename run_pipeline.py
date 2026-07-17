from __future__ import annotations

import json

from src.ingestion import run_ingestion


def main() -> None:
    outputs = run_ingestion()
    print("\nMineralTwin-KG ingestion completed.\n")
    for name, path in outputs.__dict__.items():
        print(f"{name:24s} -> {path}")

    with outputs.quality_report.open("r", encoding="utf-8") as file:
        report = json.load(file)

    print("\nData-quality summary:")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
