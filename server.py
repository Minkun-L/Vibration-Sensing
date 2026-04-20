"""
server.py — Lightweight always-on Flask server for the Pi.

Runs continuously (launch at boot or manually):
    python3 server.py

Endpoints
---------
GET  /features   — Return latest measurement features from features.json
POST /trigger    — Launch mk_kx132.py as a subprocess (one at a time)
GET  /status     — Report idle/running state and whether data is available
"""

import json
import logging
import subprocess
import threading
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

# ── Paths ──────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
FEATURES_FILE    = _HERE / "features.json"
HISTORY_FILE     = _HERE / "history.json"
PENDING_NOTE_FILE = _HERE / "pending_note.json"
FFT_DATA_FILE    = _HERE / "fft_data.json"
MK_SCRIPT        = _HERE / "mk_kx132.py"
FLASK_PORT    = 5000

# ── State ──────────────────────────────────────────────────────────────────
_proc_lock   = threading.Lock()
_active_proc = None          # subprocess.Popen handle while mk_kx132.py runs

# ── Flask app ──────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)   # allow requests from browser on a different origin


@app.route("/features")
def api_features():
    """Return the most recent feature set written by mk_kx132.py."""
    if not FEATURES_FILE.exists():
        return jsonify({"error": "No measurement data yet"}), 404
    try:
        data = json.loads(FEATURES_FILE.read_text())
        return jsonify(data)
    except (json.JSONDecodeError, OSError) as exc:
        return jsonify({"error": f"Could not read features file: {exc}"}), 500


@app.route("/trigger", methods=["POST"])
def api_trigger():
    """Start a measurement run.  Returns 409 if one is already running."""
    global _active_proc
    # Save optional note so mk_kx132.py can attach it to the history record
    data = request.get_json(silent=True) or {}
    note = str(data.get("note", "")).strip()
    PENDING_NOTE_FILE.write_text(json.dumps({"note": note}))
    # Delete stale output files so hasMeasurement stays False until the new run finishes
    FEATURES_FILE.unlink(missing_ok=True)
    FFT_DATA_FILE.unlink(missing_ok=True)
    with _proc_lock:
        # Check if a previous process is still alive
        if _active_proc is not None and _active_proc.poll() is None:
            return jsonify({"status": "already_running"}), 409
        # Launch mk_kx132.py as a new subprocess
        _active_proc = subprocess.Popen(
            ["python3", str(MK_SCRIPT)],
            cwd=str(_HERE),
        )
    return jsonify({"status": "triggered"})


@app.route("/history")
def api_history():
    """Return the full measurement history written by mk_kx132.py."""
    if not HISTORY_FILE.exists():
        return jsonify([])
    try:
        return jsonify(json.loads(HISTORY_FILE.read_text()))
    except (json.JSONDecodeError, OSError) as exc:
        return jsonify({"error": f"Could not read history file: {exc}"}), 500


@app.route("/fft")
def api_fft():
    """Return the latest FFT chart data written by mk_kx132.py."""
    if not FFT_DATA_FILE.exists():
        return jsonify({"error": "No FFT data yet"}), 404
    try:
        return jsonify(json.loads(FFT_DATA_FILE.read_text()))
    except (json.JSONDecodeError, OSError) as exc:
        return jsonify({"error": f"Could not read FFT file: {exc}"}), 500


@app.route("/status")
def api_status():
    """Return whether a measurement is in progress and if data is available."""
    with _proc_lock:
        running = _active_proc is not None and _active_proc.poll() is None
    return jsonify({
        "ready":          True,
        "running":        running,
        "hasMeasurement": FEATURES_FILE.exists(),
    })


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)   # suppress per-request logs
    print(f"Server starting on port {FLASK_PORT} …")
    app.run(host="0.0.0.0", port=FLASK_PORT, use_reloader=False)
