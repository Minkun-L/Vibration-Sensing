import sys
import time
import csv
import ctypes
import subprocess
import threading
import multiprocessing
from pathlib import Path
from datetime import datetime
import numpy as np

# When launched with --no-motor the motor impulse is skipped (background characterization mode)
_NO_MOTOR = '--no-motor' in sys.argv

try:
    import plotly.graph_objects as go
except ImportError as exc:
    raise ImportError("plotly is required. Install with: pip install plotly") from exc

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
HPF_CUTOFF_HZ = 10.0      # high-pass filter cutoff (Hz) — used in export and feature extraction
MEASURE_DURATION_S = 13   # how long to collect data per run (seconds)
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
        return 0  # return 0 so collect_data waits for fresh data after the clear
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
    z_g = z_raw * KX132_G_PER_LSB

    # Sanity clamp: KX132 is configured for ±8 g; anything beyond ±9 g is
    # a corrupt read (usually from a cs_change / auto-increment misfire or
    # loose SPI wiring causing a momentary open circuit).
    MAX_VALID_G = 9.0
    corrupt = np.abs(z_g) > MAX_VALID_G
    if corrupt.any():
        n_corrupt = int(corrupt.sum())
        raw_vals = z_raw[corrupt].tolist()
        # Diagnose the pattern: all-0xFF → MISO floating high (wire open)
        #                       all-0x00 → MISO floating low  (wire open)
        #                       specific values → register auto-increment
        raw_bytes_corrupt = raw[corrupt]
        all_ff = bool(np.all(raw_bytes_corrupt == 0xFF))
        all_00 = bool(np.all(raw_bytes_corrupt == 0x00))
        if all_ff or all_00:
            print(f"WARNING: {n_corrupt} corrupt sample(s) — MISO line appears OPEN CIRCUIT "
                  f"({'0xFF' if all_ff else '0x00'} pattern). CHECK WIRING.")
        else:
            # Verify WHO_AM_I to confirm SPI bus is still alive
            who = read_reg(WHO_AM_I)[0]
            if who != 0x3D:
                print(f"WARNING: {n_corrupt} corrupt sample(s) AND WHO_AM_I={hex(who)} "
                      f"(expected 0x3D) — SPI BUS FAULT. CHECK WIRING.")
            else:
                print(f"Warning: {n_corrupt} corrupt sample(s) clamped (|z| > {MAX_VALID_G}g) "
                      f"— raw Z bytes: {raw_vals[:4]}. SPI bus OK (WHO_AM_I=0x3D).")
        z_g[corrupt] = 0.0

    return FS, z_g
 
 
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
    WIN_SEC = 0.1
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
    from scipy.signal import butter, sosfilt, find_peaks

    csv_file_path = Path(csv_path)
    data = np.genfromtxt(csv_file_path, delimiter=",", names=True)
    data = np.atleast_1d(data)
    z_g = np.asarray(data["z_g"], dtype=np.float64)

    fs = float(sampling_rate_hz)

    # ── High-pass filter ──
    sos = butter(4, HPF_CUTOFF_HZ, btype='high', fs=fs, output='sos')
    z_hp = sosfilt(sos, z_g)

    # ── Peak window detection (0.05 s per window) ──
    # Skipped in no-motor (background noise) mode — use the full signal instead.
    PEAK_THRESH = 0.6
    WIN_SEC = 0.05
    win_samples = int(WIN_SEC * fs)
    skip_samples = int(2.0 * fs)

    if _NO_MOTOR:
        peak_starts = np.array([], dtype=np.intp)
    else:
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

    # ── Feature 1: Primary Resonance Frequency (peak of PSD above 100 Hz) ──
    PRIMARY_FREQ_MIN_HZ = 100.0
    pf_mask = freq_masked >= PRIMARY_FREQ_MIN_HZ
    if pf_mask.any():
        pf_idc = np.where(pf_mask)[0]
        best_local = int(np.argmax(psd_masked[pf_mask]))
        primary_freq = float(freq_masked[pf_idc[best_local]])
        _primary_peak_idx = int(pf_idc[best_local])
    else:
        primary_freq = float(freq_masked[np.argmax(psd_masked)])
        _primary_peak_idx = int(np.argmax(psd_masked))

    # ── Feature: Spectral Centroid (PSD-weighted mean frequency) ──
    psd_sum = np.sum(psd_masked)
    if psd_sum > 0:
        spectral_centroid = float(np.sum(freq_masked * psd_masked) / psd_sum)
    else:
        spectral_centroid = 0.0

    # ── Feature: Modal Frequency Ratio (f₂ / f₁) ──
    # Find the second distinct PSD peak, requiring at least max(50 Hz, 30% of f₁) separation
    freq_resolution = float(freq_masked[1] - freq_masked[0]) if len(freq_masked) > 1 else 1.0
    min_sep_bins = max(2, int(max(50.0, 0.3 * primary_freq) / freq_resolution))
    candidate_peaks, _ = find_peaks(psd_masked, distance=min_sep_bins)
    if len(candidate_peaks) >= 2:
        sorted_peaks = sorted(candidate_peaks, key=lambda i: psd_masked[i], reverse=True)
        second_freq = float(freq_masked[sorted_peaks[1]])
        freq_ratio = round(second_freq / primary_freq, 2) if primary_freq > 0 else None
    else:
        second_freq = None
        freq_ratio = None
    print(f"  Feature 6 — Modal Frequency Ratio (f₂/f₁): {freq_ratio} (f₂ = {second_freq} Hz)")
    # Find -3dB (half-power) crossing points around the primary frequency peak
    peak_idx = _primary_peak_idx
    half_power = psd_masked[peak_idx] / 2.0
    # Walk left from peak to find lower -3dB crossing
    left_idx = peak_idx
    while left_idx > 0 and psd_masked[left_idx] > half_power:
        left_idx -= 1
    # Interpolate for sub-bin accuracy
    if left_idx < peak_idx and psd_masked[left_idx + 1] != psd_masked[left_idx]:
        frac = (half_power - psd_masked[left_idx]) / (psd_masked[left_idx + 1] - psd_masked[left_idx])
        f_lower = float(freq_masked[left_idx] + frac * (freq_masked[left_idx + 1] - freq_masked[left_idx]))
    else:
        f_lower = float(freq_masked[left_idx])
    # Walk right from peak to find upper -3dB crossing
    right_idx = peak_idx
    while right_idx < len(psd_masked) - 1 and psd_masked[right_idx] > half_power:
        right_idx += 1
    if right_idx > peak_idx and psd_masked[right_idx] != psd_masked[right_idx - 1]:
        frac = (psd_masked[right_idx - 1] - half_power) / (psd_masked[right_idx - 1] - psd_masked[right_idx])
        f_upper = float(freq_masked[right_idx - 1] + frac * (freq_masked[right_idx] - freq_masked[right_idx - 1]))
    else:
        f_upper = float(freq_masked[right_idx])
    bandwidth = f_upper - f_lower
    if bandwidth > 0 and primary_freq > 0:
        q_factor      = primary_freq / bandwidth
        damping_ratio = 1.0 / (2.0 * q_factor)
        decay_time_ms = (q_factor / (np.pi * primary_freq)) * 1000.0  # ms
    else:
        q_factor      = 0.0
        damping_ratio = 0.0
        decay_time_ms = 0.0
    print(f"  Feature 2 — Q Factor                    : {q_factor:.1f}")
    print(f"  Feature 3 — Damping Ratio               : {damping_ratio:.4f}")
    print(f"  Feature 3 — Decay Time                  : {decay_time_ms:.1f} ms")
    print("===========================\n")

    print("\n=== EXTRACTED FEATURES ===")
    print(f"  Feature 1 — Primary Resonance Frequency : {primary_freq:.1f} Hz")
    print(f"  Feature 4 — Spectral Centroid           : {spectral_centroid:.1f} Hz")
    print(f"  Feature 5 — RMS of Acceleration         : {rms:.4f} g")

    # Write results to features.json so server.py can serve them to the frontend
    import json
    now = datetime.now()
    features = {
        "primaryFreq":      round(primary_freq, 1),
        "rmsAcceleration":  round(rms, 4),
        "spectralCentroid": round(spectral_centroid, 1),
        "freqRatio":        freq_ratio,
        "secondFreq":       round(second_freq, 1) if second_freq is not None else None,
        "qFactor":          round(q_factor, 1),
        "dampingRatio":     round(damping_ratio, 4),
        "decayTime":        round(decay_time_ms, 1),
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

    # Build sampled time-series data for the frontend
    MAX_TIME_POINTS = 5000
    ts_step = max(1, len(z_hp) // MAX_TIME_POINTS)
    ts_indices = np.arange(0, len(z_hp), ts_step)
    time_points = [
        {"t": round(float(i / fs), 4), "z": round(float(z_hp[i]), 5)}
        for i in ts_indices
    ]
    peak_windows = [
        {"tStart": round(float(ps / fs), 4), "tEnd": round(float((ps + win_samples) / fs), 4)}
        for ps in peak_starts
    ]

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
        "freqRatio":        features["freqRatio"],
        "secondFreq":       features["secondFreq"],
        "qFactor":          features["qFactor"],
        "dampingRatio":     features["dampingRatio"],
        "decayTime":        features["decayTime"],
        "note":             note,
        "noMotor":          _NO_MOTOR,
        "fftPoints":        fft_points,
        "timePoints":       time_points,
        "peakWindows":      peak_windows,
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
    if _NO_MOTOR:
        print(f"Collecting data — background noise mode (no motor impulse), running for {MEASURE_DURATION_S}s...")
    else:
        print(f"Collecting data — will stop 1s after motor finishes...")

    # Launch motor_control.py 2 s after measurement starts (separate process)
    # Keep a reference so we can wait for it to finish.
    _motor_script = Path(__file__).parent / "motor_control.py"
    _motor_proc = [None]   # list so the closure can write to it

    def _launch_motor():
        print("[motor] Starting motor_control.py...")
        _motor_proc[0] = subprocess.Popen(["python3", str(_motor_script)])
    if not _NO_MOTOR:
        threading.Timer(2.0, _launch_motor).start()

    motor_done_at = None   # timestamp when motor process exits
    rms_window_buf = []          # accumulates z samples for the current 2s RMS window
    rms_window_start = time.perf_counter()
    RMS_WINDOW_S = 2.0
    RMS_AUTOSTOP_THRESH = 3.6    # g — sustained RMS above this triggers auto-stop
    RMS_AUTOSTOP_DURATION_S = 5.0  # stop if RMS stays above threshold for this long
    high_rms_since = None        # wall time when RMS first exceeded threshold

    while True:
        # Check if motor has finished
        proc = _motor_proc[0]
        if proc is not None and motor_done_at is None and proc.poll() is not None:
            motor_done_at = time.perf_counter()
            print(f"[motor] Finished — stopping measurement in 1s...")

        # Stop 1 s after motor done, or fall back to MEASURE_DURATION_S safety cap
        if motor_done_at is not None and time.perf_counter() >= motor_done_at + 1.0:
            break
        if time.perf_counter() >= measure_end:
            print(f"Safety timeout ({MEASURE_DURATION_S}s) reached.")
            break

        actual_fs, z_chunk = collect_data(CHUNK_SIZE)
 
        n_got = len(z_chunk)
        if n_got == 0:
            continue
 
        append_csv_rows(csv_writer, sample_counter, z_chunk)
        sample_counter += n_got

        # Accumulate samples for 2s RMS window
        rms_window_buf.extend(z_chunk.tolist())
        now = time.perf_counter()
        if now - rms_window_start >= RMS_WINDOW_S:
            rms = float(np.sqrt(np.mean(np.array(rms_window_buf) ** 2)))
            window_idx = int((rms_window_start - (measure_end - MEASURE_DURATION_S)) / RMS_WINDOW_S) + 1
            print(f"[RMS] window {window_idx} ({RMS_WINDOW_S:.0f}s): {rms:.4f} g")
            rms_window_buf = []
            rms_window_start = now

            # Auto-stop if RMS stays above threshold for too long
            if rms > RMS_AUTOSTOP_THRESH:
                if high_rms_since is None:
                    high_rms_since = now
                    print(f"[RMS] High RMS detected ({rms:.4f}g > {RMS_AUTOSTOP_THRESH}g) — "
                          f"will auto-stop if sustained for {RMS_AUTOSTOP_DURATION_S:.0f}s.")
                elif now - high_rms_since >= RMS_AUTOSTOP_DURATION_S:
                    print(f"[RMS] Auto-stop triggered: RMS = {rms:.4f}g > {RMS_AUTOSTOP_THRESH}g "
                          f"for {now - high_rms_since:.1f}s.")
                    break
            else:
                if high_rms_since is not None:
                    print(f"[RMS] RMS back below threshold ({rms:.4f}g) — auto-stop timer reset.")
                high_rms_since = None

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