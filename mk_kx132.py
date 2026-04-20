import time
import csv
import ctypes
import threading
import multiprocessing
from pathlib import Path
from datetime import datetime
import numpy as np

try:
    import plotly.graph_objects as go
except ImportError as exc:
    raise ImportError("plotly is required. Install with: pip install plotly") from exc

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

# =========================
# SPI setup (C library via ctypes)
# =========================
_lib_path = Path(__file__).parent / "libspi_fifo.so"
if not _lib_path.exists():
    raise FileNotFoundError(f"Compile first: cd {_lib_path.parent} && make")
_spi = ctypes.CDLL(str(_lib_path))

# C function signatures
_spi.spi_open.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint8]
_spi.spi_open.restype = ctypes.c_int
_spi.spi_close.argtypes = []
_spi.spi_close.restype = None
_spi.spi_write_reg.argtypes = [ctypes.c_uint8, ctypes.c_uint8]
_spi.spi_write_reg.restype = ctypes.c_int
_spi.spi_read_reg.argtypes = [ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
_spi.spi_read_reg.restype = ctypes.c_int
_spi.spi_fifo_read_samples.argtypes = [ctypes.c_uint16, ctypes.POINTER(ctypes.c_uint8)]
_spi.spi_fifo_read_samples.restype = ctypes.c_int

SPI_DEVICE = b"/dev/spidev0.0"
SPI_SPEED = 10000000
SPI_MODE = 3  # CPOL=1, CPHA=1
if _spi.spi_open(SPI_DEVICE, SPI_SPEED, SPI_MODE) < 0:
    raise RuntimeError("Failed to open SPI device")
# =========================
# KX132 registers
# =========================
WHO_AM_I = 0x13
INS2 = 0x17
CNTL1 = 0x1B
ODCNTL = 0x21
INC1 = 0x22
INC4 = 0x25
XOUT_L = 0x08
BUF_CNTL1 = 0x5E  # watermark threshold (in samples)
BUF_CNTL2 = 0x5F  # FIFO control: enable, resolution, mode
BUF_STATUS_1 = 0x60  # sample count low byte
BUF_STATUS_2 = 0x61  # sample count high bits + watermark flag
BUF_CLEAR = 0x62  # write to clear FIFO
BUF_READ = 0x63  # FIFO read register
# =========================
# Config
# =========================
FS = 6400              # sampling rate
N = 3840               # buffer size (0.6s at 6400 Hz)
CHUNK_SIZE = 40        # XYZ samples per read (FIFO max=86 in 16-bit mode)
FFT_AVG_COUNT = 5      # moving average count for FFT magnitude
# HP_CUTOFF_HZ = 10.0    # high-pass cutoff for magnitude signal (disabled)
KX132_G_PER_LSB = 0.000244  # +/-8g mode scale factor
RELAY_PIN = 27
RELAY_ON_S = 0.05
RELAY_OFF_S = 1.95
HPF_CUTOFF_HZ = 10.0      # high-pass filter cutoff (Hz) — used in export and feature extraction
MEASURE_DURATION_S = 20   # how long to collect data per run (seconds)
# =========================
# SPI helpers
# =========================
def write_reg(reg, value):
    _spi.spi_write_reg(reg, value)

def read_reg(reg, length=1):
    buf = (ctypes.c_uint8 * length)()
    _spi.spi_read_reg(reg, buf, length)
    return list(buf)

def fifo_burst_read(n_samples):
    """Read n_samples from FIFO via C ioctl (per-sample CS toggle)."""
    buf = (ctypes.c_uint8 * (n_samples * 6))()
    ret = _spi.spi_fifo_read_samples(n_samples, buf)
    if ret < 0:
        return np.array([], dtype=np.uint8)
    return np.frombuffer(buf, dtype=np.uint8).copy()
# =========================
# Init sensor
# =========================
def init_kx132():
    # Standby mode for configuration
    write_reg(CNTL1, 0x00)
    time.sleep(0.05)
 
    # ODR = 6400 Hz (OSA=0x0D)
    write_reg(ODCNTL, 0x0D)
 
    # FIFO: set watermark threshold (uint8, max 255)
    write_reg(BUF_CNTL1, min(CHUNK_SIZE, 255))
    # FIFO: enable, 16-bit resolution, stream mode (BUF_M=01)
    # bit 7: BUFE=1 (enable), bit 6: BRES=1 (16-bit), bit 1:0: BUF_M=01 (stream)
    write_reg(BUF_CNTL2, 0xC1)
 
    # Clear FIFO
    write_reg(BUF_CLEAR, 0x00)
 
    # Enable sensor: PC1 + high-res + 8g + DRDYE
    gsel_8g = 0x10
    pc1 = 0x80
    res = 0x40
    drdye = 0x20
    write_reg(CNTL1, pc1 | res | gsel_8g | drdye)
    time.sleep(0.05)
 
# =========================
# Read FIFO sample count
# =========================
def get_fifo_sample_count():
    lo = read_reg(BUF_STATUS_1)[0]
    status2 = read_reg(BUF_STATUS_2)[0]
    if status2 & 0x80:
        print("FIFO OVERFLOW! resetting...")
        write_reg(BUF_CLEAR, 0x00)
    hi = status2 & 0x07  # bits 2:0
    raw_count = (hi << 8) | lo
    # SMP_LEV counts bytes in FIFO; divide by 6 for XYZ sample sets (16-bit mode)
    return raw_count // 6
 
# =========================
# Collect samples (FIFO polling)
# =========================
def collect_data(num_samples):
    # Poll FIFO until at least num_samples are available (2s timeout)
    t0 = time.perf_counter()
    while True:
        n_available = get_fifo_sample_count()
        if n_available >= num_samples:
            break
        if time.perf_counter() - t0 > 2.0:
            print("Warning: polling timeout")
            return FS, np.array([])
        time.sleep(0.0001)  # brief sleep to avoid busy-wait
 
    n_to_read = min(CHUNK_SIZE, n_available)
    collect_data._call_count = getattr(collect_data, '_call_count', 0) + 1
    if collect_data._call_count % 100 == 0:
        print(f"available={n_available}, reading={n_to_read}")
 
    if n_to_read == 0:
        return FS, np.array([])
 
    # Burst read via C ioctl — single CS, no kernel splitting
    t_spi = time.perf_counter()
    raw = fifo_burst_read(n_to_read)
    dt_spi = time.perf_counter() - t_spi
    if collect_data._call_count % 100 == 0:
        print(f"spi_took={dt_spi*1000:.1f}ms, bytes={len(raw)}, reading={n_to_read}")

    if len(raw) == 0:
        return FS, np.array([])

    # Vectorized decode: reshape to (n_to_read, 6), extract Z only
    raw = raw.reshape(n_to_read, 6)
    z_raw = (raw[:, 5].astype(np.int16) << 8) | raw[:, 4]
 
    return FS, z_raw * KX132_G_PER_LSB
 
 
CSV_WRITE_THRESHOLD = 1000
csv_buffer = []

def append_csv_rows(csv_writer, sample_start_idx, z_data):
    indices = np.arange(sample_start_idx, sample_start_idx + len(z_data))
    rows = np.column_stack((indices, z_data))
    csv_buffer.extend(rows.tolist())
    if len(csv_buffer) >= CSV_WRITE_THRESHOLD:
        csv_writer.writerows(csv_buffer)
        csv_buffer.clear()
 
 
def export_magnitude_plotly_html(csv_path, sampling_rate_hz=FS, output_html_path=None):
    from plotly.subplots import make_subplots
    from scipy.signal import butter, sosfilt, find_peaks
    import re
 
    csv_file_path = Path(csv_path)
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
 
    data = np.genfromtxt(csv_file_path, delimiter=",", names=True)
    if data.size == 0:
        raise ValueError("CSV file is empty or missing data rows")
 
    # Ensure array-like behavior for a single-row CSV.
    data = np.atleast_1d(data)
 
    z_g = np.asarray(data["z_g"], dtype=np.float64)
 
    if sampling_rate_hz <= 0:
        raise ValueError("sampling_rate_hz must be > 0")
    fs = float(sampling_rate_hz)
    time_s = np.arange(len(z_g), dtype=np.float64) / fs
 
    # ── High-pass filter ──
    sos = butter(4, HPF_CUTOFF_HZ, btype='high', fs=fs, output='sos')
    z_hp = sosfilt(sos, z_g)
 
    # ── Peak detection (amplitude > 1.5g) ──
    PEAK_THRESH = 0.6
    WIN_SEC = 0.05
    win_samples = int(WIN_SEC * fs)
 
    above = np.abs(z_hp) > PEAK_THRESH
    # Find rising edges: transitions from below to above threshold
    edges = np.diff(above.astype(np.int8))
    peak_starts = np.where(edges == 1)[0] + 1
 
    # Ignore peaks in the first 2 seconds (sensor settling)
    skip_samples = int(2.0 * fs)
    peak_starts = peak_starts[peak_starts >= skip_samples]
 
    # Merge peaks that are within 1 window of each other
    if len(peak_starts) > 1:
        merged = [peak_starts[0]]
        for ps in peak_starts[1:]:
            if ps - merged[-1] >= win_samples:
                merged.append(ps)
        peak_starts = np.array(merged)
 
    # Filter out peaks where window would exceed data length
    peak_starts = peak_starts[peak_starts + win_samples <= len(z_hp)]
    print(f"  Found {len(peak_starts)} peak windows (threshold={PEAK_THRESH}g, window={WIN_SEC}s)")
 
    # ── Windowed FFT/PSD averaging ──
    fft_freq_win = np.fft.rfftfreq(win_samples, d=1.0 / fs)
    avg_fft_mag = np.zeros(len(fft_freq_win))
    avg_psd = np.zeros(len(fft_freq_win))
 
    if len(peak_starts) > 0:
        hann = np.hanning(win_samples)
        hann_sum = np.sum(hann)       # for FFT magnitude correction
        hann_ss = np.sum(hann ** 2)   # for PSD correction
        for ps in peak_starts:
            window = z_hp[ps:ps + win_samples] * hann
            fv = np.fft.rfft(window)
            avg_fft_mag += 2.0 * np.abs(fv) / hann_sum
            p = np.abs(fv) ** 2 / (hann_ss * fs)
            p[1:-1] *= 2
            avg_psd += p
        avg_fft_mag /= len(peak_starts)
        avg_psd /= len(peak_starts)
    else:
        # Fallback: use entire signal if no peaks found
        n_full = len(z_hp)
        hann = np.hanning(n_full)
        fft_freq_win = np.fft.rfftfreq(n_full, d=1.0 / fs)
        fv = np.fft.rfft(z_hp * hann)
        avg_fft_mag = 2.0 * np.abs(fv) / np.sum(hann)
        p = np.abs(fv) ** 2 / (np.sum(hann ** 2) * fs)
        p[1:-1] *= 2
        avg_psd = p

    avg_psd_db = 10 * np.log10(np.maximum(avg_psd, 1e-20))
 
    # Trim sub-20Hz bins
    freq_mask = fft_freq_win >= HPF_CUTOFF_HZ
    fft_freq_plot = fft_freq_win[freq_mask]
    fft_mag_plot = avg_fft_mag[freq_mask]
    psd_db_plot = avg_psd_db[freq_mask]
 
    # ── Build plotly figure ──
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=(
            f"Z-Axis Over Time ({HPF_CUTOFF_HZ:.0f}Hz HPF, {len(peak_starts)} peaks detected)",
            f"FFT Magnitude (avg of {len(peak_starts)} × {WIN_SEC}s windows)",
            f"PSD (avg of {len(peak_starts)} × {WIN_SEC}s windows)",
        ),
        vertical_spacing=0.08,
    )
 
    # Time domain (HPF'd)
    fig.add_trace(
        go.Scatter(x=time_s, y=z_hp, mode="lines", name="Z (HPF)", line=dict(color="steelblue")),
        row=1, col=1,
    )
 
    # Mark peak windows as shaded rectangles
    for i, ps in enumerate(peak_starts):
        t_start = ps / fs
        t_end = (ps + win_samples) / fs
        fig.add_vrect(
            x0=t_start, x1=t_end,
            fillcolor="red", opacity=0.15, line_width=0,
            row=1, col=1,
        )
        # Mark peak start with a vertical line
        fig.add_vline(
            x=t_start, line_dash="dash", line_color="red", line_width=1,
            row=1, col=1,
        )
 
    # FFT magnitude (averaged)
    fig.add_trace(
        go.Scatter(x=fft_freq_plot, y=fft_mag_plot, mode="lines", name="FFT |Z| (avg)"),
        row=2, col=1,
    )
 
    # PSD (averaged)
    fig.add_trace(
        go.Scatter(x=fft_freq_plot, y=psd_db_plot, mode="lines", name="PSD (avg)"),
        row=3, col=1,
    )
 
    # ── PSD peak detection (prominence ≥ 20 dB) ──
    PSD_PEAK_PROMINENCE = 15.0
    PSD_PEAK_WIN_HZ = 150.0  # half-width of highlight window around each peak
    psd_peak_indices, psd_peak_props = find_peaks(
        psd_db_plot, prominence=PSD_PEAK_PROMINENCE,
    )
    if len(psd_peak_indices) > 0:
        psd_peak_freqs = fft_freq_plot[psd_peak_indices]
        psd_peak_vals = psd_db_plot[psd_peak_indices]
        print(f"  PSD peaks (>{PSD_PEAK_PROMINENCE}dB prominence): "
              + ", ".join(f"{f:.1f}Hz ({v:.1f}dB/Hz)" for f, v in zip(psd_peak_freqs, psd_peak_vals)))
        # Mark each peak with a shaded window and annotation
        for idx, pi in enumerate(psd_peak_indices):
            f_center = fft_freq_plot[pi]
            f_lo = max(fft_freq_plot[0], f_center - PSD_PEAK_WIN_HZ)
            f_hi = min(fft_freq_plot[-1], f_center + PSD_PEAK_WIN_HZ)
            fig.add_vrect(
                x0=f_lo, x1=f_hi,
                fillcolor="orange", opacity=0.15, line_width=0,
                row=3, col=1,
            )
            fig.add_vline(
                x=f_center, line_dash="dash", line_color="red", line_width=1,
                row=3, col=1,
            )
        # Scatter markers on the peaks
        fig.add_trace(
            go.Scatter(
                x=psd_peak_freqs, y=psd_peak_vals,
                mode="markers+text",
                marker=dict(color="red", size=8, symbol="diamond"),
                text=[f"{f:.0f}Hz" for f in psd_peak_freqs],
                textposition="top center",
                name=f"PSD peaks (>{PSD_PEAK_PROMINENCE}dB)",
            ),
            row=3, col=1,
        )
    else:
        print(f"  No PSD peaks found with prominence > {PSD_PEAK_PROMINENCE} dB")

    fig.update_xaxes(title_text="Time (s)", row=1, col=1)
    fig.update_yaxes(title_text="Acceleration (g)", row=1, col=1)
    fig.update_xaxes(title_text="Frequency (Hz)", row=2, col=1)
    fig.update_yaxes(title_text="Magnitude (g)", row=2, col=1)
    fig.update_xaxes(title_text="Frequency (Hz)", row=3, col=1)
    fig.update_yaxes(title_text="PSD (dB/Hz)", row=3, col=1)
 
    fig.update_layout(
        height=900,
        template="plotly_white",
        showlegend=True,
    )
 
    if output_html_path is None:
        short_name = re.sub(r'^kx132_\d{4}', '', csv_file_path.stem).lstrip("_")
        output_html_path = csv_file_path.with_name(short_name + ".html")
 
    output_html_path = Path(output_html_path)
    fig.write_html(str(output_html_path), include_plotlyjs="cdn")
    return str(output_html_path)


# =========================
# Feature extraction
# =========================
def compute_features(csv_path, sampling_rate_hz=FS):
    from scipy.signal import butter, sosfilt

    csv_file_path = Path(csv_path)
    data = np.genfromtxt(csv_file_path, delimiter=",", names=True)
    data = np.atleast_1d(data)
    z_g = np.asarray(data["z_g"], dtype=np.float64)

    fs = float(sampling_rate_hz)

    # ── High-pass filter ──
    sos = butter(4, HPF_CUTOFF_HZ, btype='high', fs=fs, output='sos')
    z_hp = sosfilt(sos, z_g)

    # ── Peak window detection (0.05 s per window) ──
    PEAK_THRESH = 0.6
    WIN_SEC = 0.05
    win_samples = int(WIN_SEC * fs)
    skip_samples = int(2.0 * fs)

    above = np.abs(z_hp) > PEAK_THRESH
    edges = np.diff(above.astype(np.int8))
    peak_starts = np.where(edges == 1)[0] + 1
    peak_starts = peak_starts[peak_starts >= skip_samples]
    if len(peak_starts) > 1:
        merged = [peak_starts[0]]
        for ps in peak_starts[1:]:
            if ps - merged[-1] >= win_samples:
                merged.append(ps)
        peak_starts = np.array(merged)
    peak_starts = peak_starts[peak_starts + win_samples <= len(z_hp)]

    # ── Collect windowed segments (used for both PSD and RMS) ──
    if len(peak_starts) > 0:
        windows = [z_hp[ps:ps + win_samples] for ps in peak_starts]
    else:
        # Fallback: treat entire signal as one window
        windows = [z_hp]

    # ── Feature 5: RMS of Acceleration (averaged over windows) ──
    rms = float(np.mean([np.sqrt(np.mean(w ** 2)) for w in windows]))

    # ── Averaged PSD over peak windows ──
    if len(peak_starts) > 0:
        fft_freq = np.fft.rfftfreq(win_samples, d=1.0 / fs)
        avg_psd = np.zeros(len(fft_freq))
        avg_fft_mag = np.zeros(len(fft_freq))
        hann = np.hanning(win_samples)
        hann_sum = np.sum(hann)
        hann_ss = np.sum(hann ** 2)
        for w in windows:
            fv = np.fft.rfft(w * hann)
            avg_fft_mag += 2.0 * np.abs(fv) / hann_sum
            p = np.abs(fv) ** 2 / (hann_ss * fs)
            p[1:-1] *= 2
            avg_psd += p
        avg_fft_mag /= len(windows)
        avg_psd /= len(windows)
    else:
        n_full = len(z_hp)
        hann = np.hanning(n_full)
        fft_freq = np.fft.rfftfreq(n_full, d=1.0 / fs)
        fv = np.fft.rfft(z_hp * hann)
        avg_fft_mag = 2.0 * np.abs(fv) / np.sum(hann)
        avg_psd = np.abs(fv) ** 2 / (np.sum(hann ** 2) * fs)
        avg_psd[1:-1] *= 2

    # Restrict all spectral features to frequencies above the HPF cutoff
    freq_mask = fft_freq >= HPF_CUTOFF_HZ
    psd_masked = avg_psd[freq_mask]
    freq_masked = fft_freq[freq_mask]
    fft_mag_masked = avg_fft_mag[freq_mask]

    # ── Feature 1: Primary Resonance Frequency (peak of PSD above HPF cutoff) ──
    primary_freq = float(freq_masked[np.argmax(psd_masked)])

    # ── Feature: Spectral Centroid (PSD-weighted mean frequency) ──
    psd_sum = np.sum(psd_masked)
    if psd_sum > 0:
        spectral_centroid = float(np.sum(freq_masked * psd_masked) / psd_sum)
    else:
        spectral_centroid = 0.0

    print("\n=== EXTRACTED FEATURES ===")
    print(f"  Feature 1 — Primary Resonance Frequency : {primary_freq:.1f} Hz")
    print(f"  Feature 4 — Spectral Centroid           : {spectral_centroid:.1f} Hz")
    print(f"  Feature 5 — RMS of Acceleration         : {rms:.4f} g")
    print("===========================\n")

    # Write results to features.json so server.py can serve them to the frontend
    import json
    now = datetime.now()
    features = {
        "primaryFreq":      round(primary_freq, 1),
        "rmsAcceleration":  round(rms, 4),
        "spectralCentroid": round(spectral_centroid, 1),
        "timestamp":        now.isoformat(),
    }
    features_path = Path(__file__).parent / "features.json"
    features_path.write_text(json.dumps(features, indent=2))

    # Write FFT chart data for the frontend
    MAX_CHART_POINTS = 400
    freqs_list = freq_masked.tolist()
    mag_list = fft_mag_masked.tolist()
    if len(freqs_list) > MAX_CHART_POINTS:
        step = max(1, len(freqs_list) // MAX_CHART_POINTS)
        freqs_list = freqs_list[::step]
        mag_list = mag_list[::step]
    fft_points = [{"freq": round(float(f), 1), "mag": round(float(m), 6)}
                  for f, m in zip(freqs_list, mag_list)]
    fft_data_path = Path(__file__).parent / "fft_data.json"
    fft_data_path.write_text(json.dumps({"points": fft_points}))

    # Append to history.json for the frontend history table
    history_path = Path(__file__).parent / "history.json"
    pending_note_path = Path(__file__).parent / "pending_note.json"
    try:
        note = json.loads(pending_note_path.read_text()).get("note", "") if pending_note_path.exists() else ""
        pending_note_path.unlink(missing_ok=True)   # consume it
    except (json.JSONDecodeError, OSError):
        note = ""
    record = {
        "id":               f"m{now.strftime('%Y%m%d%H%M%S')}",
        "timestamp":        features["timestamp"],
        "date":             now.strftime("%b %-d"),
        "primaryFreq":      features["primaryFreq"],
        "spectralCentroid": features["spectralCentroid"],
        "rmsAcceleration":  features["rmsAcceleration"],
        "note":             note,
    }
    try:
        history = json.loads(history_path.read_text()) if history_path.exists() else []
    except (json.JSONDecodeError, OSError):
        history = []
    history.append(record)
    history_path.write_text(json.dumps(history, indent=2))
 

# =========================
# Live plot process
# =========================
def plot_process_func(plot_queue, fs, n_display):
    import os
    os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.qpa.*=false'
    import matplotlib
    # Try TkAgg first; fall back to Agg (non-interactive) on headless systems
    try:
        matplotlib.use('TkAgg')
        import matplotlib.pyplot as plt
        plt.ion()
        fig, ax = plt.subplots(1, 1)
    except (ImportError, Exception):
        print("Warning: No display available, live plot disabled")
        # Drain queue so main process doesn't block
        while True:
            try:
                item = plot_queue.get(timeout=2.0)
                if item is None:
                    return
            except Exception:
                continue
        return
    import numpy as np
    t = np.arange(n_display) / fs
    z_buf = np.zeros(n_display, dtype=np.float64)
    line_z, = ax.plot(t, z_buf, label="Z")
    ax.set_ylim(-2, 3)
    ax.set_title("Time Domain (live)")
    ax.set_ylabel("Acceleration (g)")
    ax.set_xlabel("Time (s)")
    ax.legend(loc="upper right")
    plt.tight_layout()
    plt.show(block=False)

    while True:
        try:
            chunk = plot_queue.get(timeout=2.0)
        except Exception:
            continue
        if chunk is None:  # poison pill
            break
        n = len(chunk)
        z_buf = np.roll(z_buf, -n)
        z_buf[-n:] = chunk
        line_z.set_ydata(z_buf)
        fig.canvas.draw_idle()
        plt.pause(0.001)
        # drain extra items to stay responsive
        while not plot_queue.empty():
            item = plot_queue.get_nowait()
            if item is None:
                plt.close('all')
                return
            n2 = len(item)
            z_buf = np.roll(z_buf, -n2)
            z_buf[-n2:] = item
        line_z.set_ydata(z_buf)
        fig.canvas.draw_idle()
        plt.pause(0.001)
    plt.close('all')
 
script_start = datetime.now()
csv_filename = script_start.strftime("kx132_%Y%m%d_%H%M%S.csv")
csv_file = open(csv_filename, "w", newline="")
csv_writer = csv.writer(csv_file)
csv_writer.writerow(["sample", "z_g"])
sample_counter = 0
diag_counter = 0
plotly_export_enabled = True
plotly_export_path = Path(csv_filename).with_name(script_start.strftime("%m%d_%H%M%S.html"))
print(f"Logging CSV: {csv_filename}")

# Start live plot in separate process
plot_queue = multiprocessing.Queue(maxsize=50)
plot_proc = multiprocessing.Process(target=plot_process_func, args=(plot_queue, FS, N), daemon=True)
plot_proc.start()

# Pre-import scipy so it's cached before Ctrl+C triggers export
try:
    from scipy.signal import butter, sosfilt, find_peaks  # noqa: F401
except ImportError:
    pass
 
relay_stop_event = threading.Event()

def relay_thread_func():
    state_on = False
    last_toggle = time.perf_counter()
    GPIO.output(RELAY_PIN, GPIO.LOW)
    while not relay_stop_event.is_set():
        now = time.perf_counter()
        period = RELAY_ON_S if state_on else RELAY_OFF_S
        if now - last_toggle >= period:
            state_on = not state_on
            GPIO.output(RELAY_PIN, GPIO.HIGH if state_on else GPIO.LOW)
            last_toggle = now
        relay_stop_event.wait(timeout=0.001)
    GPIO.output(RELAY_PIN, GPIO.LOW)

if GPIO_AVAILABLE:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RELAY_PIN, GPIO.OUT)
    GPIO.output(RELAY_PIN, GPIO.LOW)
    print(GPIO.gpio_function(27))
    relay_thread = threading.Thread(target=relay_thread_func, daemon=True)
    relay_thread.start()
else:
    print("Warning: RPi.GPIO not available, relay control disabled")
try:
    init_kx132()
    write_reg(BUF_CLEAR, 0x00)
    print("WHO:", hex(read_reg(WHO_AM_I)[0]))
    print("INS2 init:", read_reg(INS2))
    print("RAW:", read_reg(XOUT_L, 6))
 
    cntl1_val = read_reg(CNTL1)[0]
    print(f"CNTL1 = {bin(cntl1_val)}")
    print(f"CNTL1 = {hex(cntl1_val)}")

    # ── FIFO read diagnostic ──────────────────────────
    time.sleep(0.2)  # let FIFO fill at 6400 Hz → ~1280 samples
    print("\n=== FIFO DIAGNOSTIC ===")
    print("BUF_CNTL2 readback:", hex(read_reg(BUF_CNTL2)[0]))
    fifo_cnt = get_fifo_sample_count()
    print("FIFO sample count:", fifo_cnt)

    # Read ADP_CNTL registers (0x64-0x69) for comparison
    adp = read_reg(0x64, 6)
    print("ADP_CNTL(1-6) @ 0x64-0x69:", adp)

    # Test A: read 6 bytes from BUF_READ in one 7-byte SPI transaction
    test_a = read_reg(BUF_READ, 6)
    print("A) BUF_READ  6 bytes (1 txn):", test_a)
    if test_a[1:6] == adp[0:5]:
        print("   >>> AUTO-INCREMENT CONFIRMED! bytes [1:6] match ADP_CNTL regs")

    # Test B: read 1 byte from BUF_READ × 12 (twelve 2-byte SPI transactions = 2 samples)
    test_b = [read_reg(BUF_READ, 1)[0] for _ in range(12)]
    print("B) BUF_READ  1 byte × 12:    ", test_b)
    # Decode as two samples
    def _to_i16(hi, lo):
        return np.array([(hi << 8) | lo], dtype=np.uint16).view(np.int16)[0]
    for s in range(2):
        off = s * 6
        xv = _to_i16(test_b[off+1], test_b[off+0])
        yv = _to_i16(test_b[off+3], test_b[off+2])
        zv = _to_i16(test_b[off+5], test_b[off+4])
        print(f"   Sample {s}: X={xv} ({xv*KX132_G_PER_LSB:.3f}g) "
              f"Y={yv} ({yv*KX132_G_PER_LSB:.3f}g) "
              f"Z={zv} ({zv*KX132_G_PER_LSB:.3f}g)")

    # Test C: read 6 bytes from XOUT_L in one 7-byte SPI transaction (always works)
    test_c = read_reg(XOUT_L, 6)
    print("C) XOUT_L    6 bytes (1 txn):", test_c)
    xc = _to_i16(test_c[1], test_c[0])
    yc = _to_i16(test_c[3], test_c[2])
    zc = _to_i16(test_c[5], test_c[4])
    print(f"   XOUT decode: X={xc} ({xc*KX132_G_PER_LSB:.3f}g) "
          f"Y={yc} ({yc*KX132_G_PER_LSB:.3f}g) "
          f"Z={zc} ({zc*KX132_G_PER_LSB:.3f}g)")

    # Test D: per-sample C function, 1 sample (7-byte txn)
    test_d = fifo_burst_read(1)
    print("D) C per-sample 1 sample:    ", list(test_d[:6]))
    print("=== END DIAGNOSTIC ===\n")
    # ──────────────────────────────────────────────────

    measure_end = time.perf_counter() + MEASURE_DURATION_S
    print(f"Collecting data for {MEASURE_DURATION_S}s...")
    while time.perf_counter() < measure_end:
        actual_fs, z_chunk = collect_data(CHUNK_SIZE)
 
        n_got = len(z_chunk)
        if n_got == 0:
            continue
 
        append_csv_rows(csv_writer, sample_counter, z_chunk)
        sample_counter += n_got

        # Send to plot process (non-blocking, drop if queue full)
        try:
            plot_queue.put_nowait(z_chunk)
        except Exception:
            pass  # drop frame if plot can't keep up

        diag_counter += 1
 
        if diag_counter % 300 == 0:
            csv_file.flush()
 
        if diag_counter % 100 == 0:
            print(f"Actual sampling rate: {actual_fs:.1f} Hz")

    print(f"\nDone — {sample_counter} samples collected.")

except KeyboardInterrupt:
    print("\nStopping early (KeyboardInterrupt)...")
finally:
    # Flush CSV
    if csv_buffer:
        csv_writer.writerows(csv_buffer)
        csv_buffer.clear()
    csv_file.flush()
    # Export plotly HTML
    if plotly_export_enabled:
        try:
            export_magnitude_plotly_html(
                csv_path=csv_filename,
                sampling_rate_hz=FS,
                output_html_path=plotly_export_path,
            )
            print(f"Plotly HTML exported: {plotly_export_path}")
        except Exception as exc:
            print(f"Warning: HTML export failed: {exc}")
    # Extract features and push to Flask API
    try:
        compute_features(csv_path=csv_filename, sampling_rate_hz=FS)
    except Exception as exc:
        print(f"Warning: Feature extraction failed: {exc}")
    # Hardware cleanup
    relay_stop_event.set()
    if GPIO_AVAILABLE:
        if 'relay_thread' in dir():
            relay_thread.join(timeout=1)
        GPIO.output(RELAY_PIN, GPIO.LOW)
        GPIO.cleanup()
    csv_file.close()
    _spi.spi_close()
    # Stop plot process
    try:
        plot_queue.put_nowait(None)
        plot_proc.join(timeout=3)
    except Exception:
        pass
    if plot_proc.is_alive():
        plot_proc.terminate()