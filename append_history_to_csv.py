"""
append_history_to_csv.py

Reads the last N records from history.json and writes them to new_data.csv
in the same format as good_data.csv (id, note, <freq cols...>).

Usage:
    python3 append_history_to_csv.py            # last 3 records (default)
    python3 append_history_to_csv.py --n 5      # last 5 records
"""

import json
import csv
import argparse
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
HISTORY_FILE = Path("history.json")
OUTPUT_FILE  = Path("new_data.csv")
GOOD_DATA    = Path("good_data.csv")  # read to get the canonical freq column order

# ── Args ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--n", type=int, default=3, help="Number of latest records to export")
args = parser.parse_args()

# ── Load frequency column order from good_data.csv ───────────────────────────
with open(GOOD_DATA, newline="") as f:
    reader = csv.reader(f)
    header = next(reader)  # ['id', 'note', '20', '40', ...]

freq_cols = header[2:]  # ['20', '40', ..., '3200']
freq_set  = {float(c) for c in freq_cols}

# ── Load history ──────────────────────────────────────────────────────────────
with open(HISTORY_FILE) as f:
    history = json.load(f)

records = history[-args.n:]
print(f"Exporting {len(records)} record(s) from history.json → {OUTPUT_FILE}")

# ── Write new_data.csv ────────────────────────────────────────────────────────
with open(OUTPUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(header)

    for rec in records:
        # Build freq → mag lookup from fftPoints
        fft_map = {round(p["freq"]): p["mag"] for p in rec.get("fftPoints", [])}

        row = [rec["id"], rec.get("note", "")]
        for col in freq_cols:
            freq_hz = int(col)
            row.append(fft_map.get(freq_hz, ""))

        writer.writerow(row)
        print(f"  {rec['timestamp']}  note='{rec.get('note', '')}' ")

print(f"\nDone. Saved to {OUTPUT_FILE.resolve()}")
print("Review the file, then manually copy rows into good_data.csv if they look correct.")
