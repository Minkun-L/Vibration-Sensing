import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import solve_ivp
from scipy.fft import rfft, rfftfreq
from scipy.signal import find_peaks


# =========================================================
# User settings
# =========================================================
# Square plate geometry (meters)
# Side length is set to the previous beam length by default.
a = 0.5          # plate length in x
b = 0.5          # plate width in y
h = 0.0254       # plate thickness

# Material: A36 steel (approx)
E = 200e9        # Pa
rho = 7850       # kg/m^3
nu = 0.29        # Poisson ratio

# Damping model (mode-dependent)
zeta_base = 0.015         # baseline damping for first mode
zeta_mode_slope = 0.008   # higher modes are usually more damped
zeta_max = 0.10           # cap to avoid non-physical over-damping

# How many plate modes to keep
n_modes = 6
max_mode_index = 8        # candidate m,n range: 1..max_mode_index

# Excitation and sensor locations (meters)
x_force = 0.75 * a
y_force = 0.65 * b
x_sensor = 0.80 * a
y_sensor = 0.75 * b

# Solenoid force pulse
force_amplitude = 20.0     # N
pulse_duration = 0.001     # s
pulse_rise_tau = 0.00025   # s
pulse_fall_tau = 0.0015    # s

# Accelerometer mass (optional lumped mass at sensor)
sensor_mass = 0.005        # kg

# Time settings
t_end = 0.25
fs = 20000

# Plot options
show_mode_shapes = True
show_time_response = True
show_fft = True


# =========================================================
# Helper functions
# =========================================================
def force_pulse(t, amp, duration, rise_tau=2.5e-4, fall_tau=1.5e-3):
    """
    Approximate solenoid force profile with finite rise and finite decay.
    """
    if t < 0.0:
        return 0.0
    if t <= duration:
        return amp * (1.0 - np.exp(-t / rise_tau))
    return amp * (1.0 - np.exp(-duration / rise_tau)) * np.exp(-(t - duration) / fall_tau)


def build_modal_damping(freqs_hz, zeta_base=0.015, zeta_mode_slope=0.008, zeta_max=0.10):
    """
    Build mode-dependent damping ratios.
    """
    f1 = max(freqs_hz[0], 1e-9)
    scale = np.sqrt(freqs_hz / f1)
    zetas = zeta_base + zeta_mode_slope * (scale - 1.0)
    return np.clip(zetas, 0.0, zeta_max)


def validate_inputs(a, b, h, E, rho, nu, n_modes, max_mode_index,
                    zeta_base, zeta_mode_slope,
                    x_force, y_force, x_sensor, y_sensor,
                    force_amplitude, pulse_duration, pulse_rise_tau, pulse_fall_tau,
                    t_end, fs, sensor_mass):
    if a <= 0 or b <= 0 or h <= 0:
        raise ValueError("Geometry must be positive: a, b, h > 0")
    if E <= 0 or rho <= 0:
        raise ValueError("Material properties must be positive: E, rho > 0")
    if not (-1.0 < nu < 0.5):
        raise ValueError("Poisson ratio must satisfy -1 < nu < 0.5")
    if n_modes < 1:
        raise ValueError("n_modes must be >= 1")
    if max_mode_index < 1:
        raise ValueError("max_mode_index must be >= 1")
    if n_modes > max_mode_index * max_mode_index:
        raise ValueError("n_modes is larger than available mode candidates")
    if zeta_base < 0 or zeta_mode_slope < 0:
        raise ValueError("zeta_base and zeta_mode_slope must be >= 0")
    if not (0.0 <= x_force <= a) or not (0.0 <= y_force <= b):
        raise ValueError("force point must be inside the plate")
    if not (0.0 <= x_sensor <= a) or not (0.0 <= y_sensor <= b):
        raise ValueError("sensor point must be inside the plate")
    if pulse_duration <= 0 or pulse_rise_tau <= 0 or pulse_fall_tau <= 0:
        raise ValueError("pulse times must be > 0")
    if t_end <= 0 or fs <= 0:
        raise ValueError("t_end and fs must be > 0")
    if sensor_mass < 0:
        raise ValueError("sensor_mass must be >= 0")
    if not np.isfinite(force_amplitude):
        raise ValueError("force_amplitude must be finite")


def plate_flexural_rigidity(E, h, nu):
    return E * h**3 / (12.0 * (1.0 - nu**2))


def mode_shape_simply_supported(x, y, a, b, m, n):
    return np.sin(m * np.pi * x / a) * np.sin(n * np.pi * y / b)


def build_plate_modes(a, b, h, E, rho, nu, n_modes,
                      sensor_mass=0.0, x_sensor=None, y_sensor=None,
                      max_mode_index=8, n_grid=80):
    """
    Kirchhoff-Love thin plate, simply-supported boundary on all four edges.
    """
    D = plate_flexural_rigidity(E, h, nu)

    x_grid = np.linspace(0.0, a, n_grid)
    y_grid = np.linspace(0.0, b, n_grid)
    X, Y = np.meshgrid(x_grid, y_grid)

    mode_pairs = []
    for m in range(1, max_mode_index + 1):
        for n in range(1, max_mode_index + 1):
            omega = (np.pi**2) * np.sqrt(D / (rho * h)) * ((m**2 / a**2) + (n**2 / b**2))
            mode_pairs.append((m, n, omega))

    mode_pairs.sort(key=lambda item: item[2])
    chosen = mode_pairs[:n_modes]

    modes_raw = []
    modes_norm = []
    freqs_hz = []
    omegas = []
    modal_masses = []
    labels = []

    # For unnormalized sin-sin mode in simply supported rectangular plate:
    # integral(phi^2 dA) = a*b/4.
    m_modal_plate = rho * h * (a * b / 4.0)

    for m, n, omega_base in chosen:
        phi_grid = mode_shape_simply_supported(X, Y, a, b, m, n)

        m_modal_total = m_modal_plate
        if sensor_mass > 0.0 and x_sensor is not None and y_sensor is not None:
            phi_sensor = mode_shape_simply_supported(x_sensor, y_sensor, a, b, m, n)
            m_modal_total += sensor_mass * phi_sensor**2

        # Same approximation used in the beam script for mass loading consistency.
        omega = omega_base * np.sqrt(m_modal_plate / m_modal_total)
        f_hz = omega / (2.0 * np.pi)

        phi_norm = phi_grid / np.sqrt(m_modal_total)

        modes_raw.append(phi_grid)
        modes_norm.append(phi_norm)
        freqs_hz.append(f_hz)
        omegas.append(omega)
        modal_masses.append(m_modal_total)
        labels.append((m, n))

    return {
        "x_grid": x_grid,
        "y_grid": y_grid,
        "X": X,
        "Y": Y,
        "D": D,
        "mode_labels": labels,
        "modes_raw": np.array(modes_raw),
        "modes_norm": np.array(modes_norm),
        "freqs_hz": np.array(freqs_hz),
        "omegas": np.array(omegas),
        "modal_masses": np.array(modal_masses),
    }


def modal_force_vector(t, mode_values_at_force, amp, duration, force_params):
    f_t = force_pulse(
        t,
        amp,
        duration,
        rise_tau=force_params["rise_tau"],
        fall_tau=force_params["fall_tau"],
    )
    return mode_values_at_force * f_t


def modal_ode(t, y, omegas, zetas, phi_force, amp, duration, force_params):
    """
    State y = [q1..qn, qd1..qdn]
    """
    n = len(omegas)
    q = y[:n]
    qd = y[n:]

    Q = modal_force_vector(t, phi_force, amp, duration, force_params)
    qdd = Q - 2.0 * zetas * omegas * qd - (omegas**2) * q

    return np.concatenate([qd, qdd])


def simulate_response(a, b, h, E, rho, nu, n_modes, max_mode_index,
                      zeta_base, zeta_mode_slope,
                      x_force, y_force, x_sensor, y_sensor,
                      force_amplitude, pulse_duration, pulse_rise_tau, pulse_fall_tau,
                      t_end, fs, sensor_mass=0.0):
    validate_inputs(
        a=a,
        b=b,
        h=h,
        E=E,
        rho=rho,
        nu=nu,
        n_modes=n_modes,
        max_mode_index=max_mode_index,
        zeta_base=zeta_base,
        zeta_mode_slope=zeta_mode_slope,
        x_force=x_force,
        y_force=y_force,
        x_sensor=x_sensor,
        y_sensor=y_sensor,
        force_amplitude=force_amplitude,
        pulse_duration=pulse_duration,
        pulse_rise_tau=pulse_rise_tau,
        pulse_fall_tau=pulse_fall_tau,
        t_end=t_end,
        fs=fs,
        sensor_mass=sensor_mass,
    )

    modal = build_plate_modes(
        a=a,
        b=b,
        h=h,
        E=E,
        rho=rho,
        nu=nu,
        n_modes=n_modes,
        sensor_mass=sensor_mass,
        x_sensor=x_sensor,
        y_sensor=y_sensor,
        max_mode_index=max_mode_index,
    )

    X = modal["X"]
    Y = modal["Y"]
    modes_norm = modal["modes_norm"]
    freqs_hz = modal["freqs_hz"]
    omegas = modal["omegas"]
    mode_labels = modal["mode_labels"]

    zetas = build_modal_damping(
        freqs_hz,
        zeta_base=zeta_base,
        zeta_mode_slope=zeta_mode_slope,
        zeta_max=zeta_max,
    )

    n_active_modes = len(omegas)

    phi_force = np.array([
        mode_shape_simply_supported(x_force, y_force, a, b, mode_labels[i][0], mode_labels[i][1])
        / np.sqrt(modal["modal_masses"][i])
        for i in range(n_active_modes)
    ])
    phi_sensor = np.array([
        mode_shape_simply_supported(x_sensor, y_sensor, a, b, mode_labels[i][0], mode_labels[i][1])
        / np.sqrt(modal["modal_masses"][i])
        for i in range(n_active_modes)
    ])

    t_eval = np.linspace(0.0, t_end, int(t_end * fs))
    y0 = np.zeros(2 * n_active_modes)

    # Ensure adaptive solver resolves a short pulse.
    max_step = min(1.0 / fs, pulse_duration / 20.0)

    sol = solve_ivp(
        fun=lambda t, y: modal_ode(
            t,
            y,
            omegas,
            zetas,
            phi_force,
            force_amplitude,
            pulse_duration,
            force_params={"rise_tau": pulse_rise_tau, "fall_tau": pulse_fall_tau},
        ),
        t_span=(0.0, t_end),
        y0=y0,
        t_eval=t_eval,
        method="RK45",
        rtol=1e-6,
        atol=1e-9,
        max_step=max_step,
    )

    t = sol.t
    q = sol.y[:n_active_modes, :]
    qd = sol.y[n_active_modes:, :]

    F_t = np.array([
        force_pulse(
            tt,
            force_amplitude,
            pulse_duration,
            rise_tau=pulse_rise_tau,
            fall_tau=pulse_fall_tau,
        )
        for tt in t
    ])
    Q = np.outer(phi_force, F_t)
    qdd = Q - (2.0 * zetas[:, None] * omegas[:, None] * qd) - ((omegas[:, None] ** 2) * q)

    acc_sensor = np.sum(phi_sensor[:, None] * qdd, axis=0)
    disp_sensor = np.sum(phi_sensor[:, None] * q, axis=0)

    return {
        "t": t,
        "freqs_hz": freqs_hz,
        "omegas": omegas,
        "zetas": zetas,
        "mode_labels": mode_labels,
        "x_grid": modal["x_grid"],
        "y_grid": modal["y_grid"],
        "X": X,
        "Y": Y,
        "modes_norm": modes_norm,
        "phi_force": phi_force,
        "phi_sensor": phi_sensor,
        "q": q,
        "qd": qd,
        "qdd": qdd,
        "disp_sensor": disp_sensor,
        "acc_sensor": acc_sensor,
    }


def plot_mode_shapes(X, Y, modes_norm, freqs_hz, mode_labels, n_to_show=6):
    n_show = min(n_to_show, len(freqs_hz))
    n_cols = 3
    n_rows = int(np.ceil(n_show / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4.6 * n_cols, 3.8 * n_rows))
    axes = np.atleast_1d(axes).ravel()

    for i in range(n_show):
        ax = axes[i]
        shape = modes_norm[i]
        shape = shape / np.max(np.abs(shape))
        m, n = mode_labels[i]
        c = ax.contourf(X, Y, shape, levels=31, cmap="RdBu_r")
        ax.set_title(f"Mode {i+1} ({m},{n})  {freqs_hz[i]:.1f} Hz")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        plt.colorbar(c, ax=ax, shrink=0.85)

    for j in range(n_show, len(axes)):
        axes[j].axis("off")

    fig.suptitle("Square Plate Mode Shapes (simply supported)", y=0.995)
    fig.tight_layout()


def plot_time_response(t, acc_sensor, disp_sensor=None):
    plt.figure(figsize=(10, 5))
    plt.plot(t, acc_sensor)
    plt.xlabel("Time (s)")
    plt.ylabel("Acceleration (m/s^2)")
    plt.title("Sensor Acceleration Response")
    plt.grid(True)
    plt.tight_layout()

    if disp_sensor is not None:
        plt.figure(figsize=(10, 5))
        plt.plot(t, disp_sensor)
        plt.xlabel("Time (s)")
        plt.ylabel("Displacement (m)")
        plt.title("Sensor Displacement Response")
        plt.grid(True)
        plt.tight_layout()


def plot_fft(signal, fs, natural_freqs=None, t=None, t_start=None, pad_factor=4):
    # Optionally analyze only free-decay segment after excitation pulse.
    if t is not None and t_start is not None:
        i0 = np.searchsorted(t, t_start)
        sig = signal[i0:]
    else:
        sig = signal

    sig = sig - np.mean(sig)
    n = len(sig)
    if n < 16:
        raise ValueError("Signal segment too short for FFT")

    window = np.hanning(n)
    coherent_gain = np.sum(window) / n
    n_fft = int(max(n, pad_factor * n))

    fft_vals = rfft(sig * window, n=n_fft)
    freqs = rfftfreq(n_fft, d=1.0 / fs)

    mag = (2.0 / (n * coherent_gain)) * np.abs(fft_vals)
    mag[0] = 0.0

    plt.figure(figsize=(10, 5))
    plt.plot(freqs, mag)
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Amplitude")
    plt.title("FFT of Sensor Acceleration")
    plt.xlim(0, min(3000, fs / 2))
    plt.grid(True)

    if natural_freqs is not None:
        for f in natural_freqs:
            plt.axvline(f, linestyle="--", alpha=0.5)

    plt.tight_layout()
    return freqs, mag


def report_main_peaks(freqs, mag, n_peaks=8, min_prom_ratio=0.02, min_sep_hz=12.0):
    df = freqs[1] - freqs[0]
    distance_bins = max(1, int(min_sep_hz / df))
    prominence = np.max(mag) * min_prom_ratio
    peaks, props = find_peaks(mag, prominence=prominence, distance=distance_bins)

    if len(peaks) == 0:
        print("\nNo strong FFT peaks found.")
        return

    peak_freqs = freqs[peaks]
    peak_amps = mag[peaks]
    peak_prom = props["prominences"]

    order = np.argsort(peak_amps)[::-1]
    print("\nStrongest FFT peaks:")
    for idx in order[:n_peaks]:
        print(
            f"  {peak_freqs[idx]:8.2f} Hz   amplitude = {peak_amps[idx]:.4e}"
            f"   prominence = {peak_prom[idx]:.4e}"
        )


# =========================================================
# Main
# =========================================================
if __name__ == "__main__":
    result = simulate_response(
        a=a,
        b=b,
        h=h,
        E=E,
        rho=rho,
        nu=nu,
        n_modes=n_modes,
        max_mode_index=max_mode_index,
        zeta_base=zeta_base,
        zeta_mode_slope=zeta_mode_slope,
        x_force=x_force,
        y_force=y_force,
        x_sensor=x_sensor,
        y_sensor=y_sensor,
        force_amplitude=force_amplitude,
        pulse_duration=pulse_duration,
        pulse_rise_tau=pulse_rise_tau,
        pulse_fall_tau=pulse_fall_tau,
        t_end=t_end,
        fs=fs,
        sensor_mass=sensor_mass,
    )

    t = result["t"]
    freqs_hz = result["freqs_hz"]
    zetas = result["zetas"]
    mode_labels = result["mode_labels"]
    X = result["X"]
    Y = result["Y"]
    modes_norm = result["modes_norm"]
    acc_sensor = result["acc_sensor"]
    disp_sensor = result["disp_sensor"]

    print("Natural frequencies (Hz):")
    for i, f in enumerate(freqs_hz, start=1):
        m, n = mode_labels[i - 1]
        print(f"  Mode {i} ({m},{n}): {f:.2f}  (zeta = {zetas[i-1]:.4f})")

    if show_mode_shapes:
        plot_mode_shapes(X, Y, modes_norm, freqs_hz, mode_labels, n_to_show=min(6, n_modes))

    if show_time_response:
        plot_time_response(t, acc_sensor, disp_sensor=disp_sensor)

    if show_fft:
        freqs, mag = plot_fft(
            acc_sensor,
            fs=fs,
            natural_freqs=freqs_hz,
            t=t,
            t_start=2.0 * pulse_duration,
            pad_factor=4,
        )
        report_main_peaks(freqs, mag)

    plt.show()
