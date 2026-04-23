"""
backup.py — Export all data to JSON + CSV files in the /backups directory.

Usage:
  python backup.py                  # exports to backups/<today>/
  python backup.py --output ./my-backup
"""

import argparse
import csv
import json
import logging
import os
import sqlite3
from datetime import date
from pathlib import Path

from config import DATABASE_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

TABLES = ["predictions", "stock_results", "accuracy_scores", "portfolio_values"]


def export_all(output_dir: str):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    summary = {}

    for table in TABLES:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
            data = [dict(r) for r in rows]
            summary[table] = len(data)

            # JSON
            json_path = out / f"{table}.json"
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2)

            # CSV
            if data:
                csv_path = out / f"{table}.csv"
                with open(csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)

            logger.info("✓ %-22s → %d rows", table, len(data))

        except Exception as exc:
            logger.error("✗ %s: %s", table, exc)

    conn.close()

    # Write manifest
    manifest = {
        "exported_at": date.today().isoformat(),
        "database":    DATABASE_PATH,
        "tables":      summary,
    }
    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Backup complete → %s", out.resolve())
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export AI Stock Analyst data")
    parser.add_argument(
        "--output",
        default=f"backups/{date.today().isoformat()}",
        help="Output directory (default: backups/<today>)",
    )
    args = parser.parse_args()
    export_all(args.output)
