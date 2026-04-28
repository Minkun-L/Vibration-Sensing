import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import solve_ivp
from scipy.fft import rfft, rfftfreq
from scipy.signal import find_peaks


# =========================================================
# User settings
# =========================================================
# Geometry (meters)
# "three palm lengths" and "one palm width" are rough.
# Change these to your real measured values.
L = 0.5          # beam length
b = 0.18          # beam width
# h = 0.0127       # thickness: 0.5 inch = 0.0127 m
h = 0.0254 / 2     # thickness: 1 inch = 0.0254 m

# Material: A36 steel (approx)
E = 200e9         # Pa
rho = 7850        # kg/m^3

# Damping model (mode-dependent)
zeta_base = 0.012          # baseline damping for mode 1
zeta_mode_slope = 0.006    # higher modes are usually more damped in tests
zeta_max = 0.08            # cap to avoid non-physical over-damping

# How many bending modes to keep
n_modes = 3

# Excitation and sensor locations along beam
x_force = 0.95 * L
x_sensor = 0.95 * L

# Solenoid force pulse
force_amplitude = 20.0      # N
pulse_duration = 0.001      # s, short half-sine pulse
pulse_rise_tau = 0.00025    # s, current/force build-up time constant
pulse_fall_tau = 0.0015     # s, force decay after switch-off

# Accelerometer mass (optional lumped mass near sensor)
# Set to 0 if you want to ignore sensor mass.
sensor_mass = 0.005         # kg

# Time settings
t_end = 0.2
fs = 20000                  # sampling rate for output
n_time = int(t_end * fs)

# Plot options
show_mode_shapes = True
show_time_response = True
show_fft = True

# =========================================================
# Cantilever beam mode constants (Euler-Bernoulli)
# First several roots of cosh(beta)*cos(beta) + 1 = 0
# =========================================================
BETA_L = np.array([
    1.875104068711961,
    4.694091132974174,
    7.854757438237612,
    10.995540734875466,
    14.13716839104647,
    17.27875953258811,
    20.42035225104125,
    23.56194490180644
])


# =========================================================
# Helper functions
# =========================================================
def area_rect(width, thickness):
    return width * thickness


def inertia_rect(width, thickness):
    return width * thickness**3 / 12.0


def force_pulse(t, amp, duration, rise_tau=2.5e-4, fall_tau=1.5e-3):
    """
    Approximate solenoid force profile with finite rise and finite decay.
    """
    if t < 0.0:
        return 0.0
    if t <= duration:
        return amp * (1.0 - np.exp(-t / rise_tau))
    return amp * (1.0 - np.exp(-duration / rise_tau)) * np.exp(-(t - duration) / fall_tau)


def build_modal_damping(freqs_hz, zeta_base=0.012, zeta_mode_slope=0.006, zeta_max=0.08):
    """
    Build mode-dependent damping ratios (higher modes get larger damping).
    """
    f1 = max(freqs_hz[0], 1e-9)
    scale = np.sqrt(freqs_hz / f1)
    zetas = zeta_base + zeta_mode_slope * (scale - 1.0)
    return np.clip(zetas, 0.0, zeta_max)


def mode_shape_cantilever(x, L, betaL):
    """
    Unnormalized cantilever bending mode shape.
    """
    beta = betaL / L
    xi = x / L

    c1 = np.cosh(betaL * xi) - np.cos(betaL * xi)
    gamma = (np.cosh(betaL) + np.cos(betaL)) / (np.sinh(betaL) + np.sin(betaL))
    c2 = np.sinh(betaL * xi) - np.sin(betaL * xi)
    return c1 - gamma * c2


def validate_inputs(L, b, h, E, rho, n_modes, zeta_base, zeta_mode_slope,
                    x_force, x_sensor, force_amplitude, pulse_duration,
                    pulse_rise_tau, pulse_fall_tau, t_end, fs, sensor_mass):
    if L <= 0 or b <= 0 or h <= 0:
        raise ValueError("Geometry must be positive: L, b, h > 0")
    if E <= 0 or rho <= 0:
        raise ValueError("Material properties must be positive: E, rho > 0")
    if n_modes < 1:
        raise ValueError("n_modes must be >= 1")
    if n_modes > len(BETA_L):
        raise ValueError(f"n_modes must be <= {len(BETA_L)} for current BETA_L table")
    if zeta_base < 0 or zeta_mode_slope < 0:
        raise ValueError("zeta_base and zeta_mode_slope must be >= 0")
    if not (0.0 <= x_force <= L):
        raise ValueError("x_force must satisfy 0 <= x_force <= L")
    if not (0.0 <= x_sensor <= L):
        raise ValueError("x_sensor must satisfy 0 <= x_sensor <= L")
    if pulse_duration <= 0:
        raise ValueError("pulse_duration must be > 0")
    if pulse_rise_tau <= 0 or pulse_fall_tau <= 0:
        raise ValueError("pulse_rise_tau and pulse_fall_tau must be > 0")
    if t_end <= 0 or fs <= 0:
        raise ValueError("t_end and fs must be > 0")
    if sensor_mass < 0:
        raise ValueError("sensor_mass must be >= 0")
    # Allow negative force (direction), but disallow NaN-like values by finite check.
    if not np.isfinite(force_amplitude):
        raise ValueError("force_amplitude must be finite")


def build_modes(L, b, h, E, rho, n_modes, sensor_mass=0.0, x_sensor=None, n_grid=4000):
    """
    Build modal data:
    - natural frequencies
    - mode shapes on grid
    - modal masses
    - normalized mode functions
    """
    A = area_rect(b, h)
    I = inertia_rect(b, h)

    x_grid = np.linspace(0.0, L, n_grid)
    betas = BETA_L[:n_modes]
    modes_raw = []
    freqs_hz = []
    modal_masses = []
    modes_norm = []

    for betaL in betas:
        phi = mode_shape_cantilever(x_grid, L, betaL)
        omega_beam = (betaL**2) * np.sqrt(E * I / (rho * A * L**4))

        # Continuous beam mass contribution
        m_modal_beam = rho * A * np.trapz(phi**2, x_grid)
        m_modal_total = m_modal_beam

        # Optional point mass from accelerometer
        if sensor_mass > 0.0 and x_sensor is not None:
            phi_sensor = np.interp(x_sensor, x_grid, phi)
            m_modal_total += sensor_mass * phi_sensor**2

        # Keep assumed mode shape but adjust modal frequency by added modal mass.
        # This is still an approximation, but it is internally consistent.
        omega = omega_beam * np.sqrt(m_modal_beam / m_modal_total)
        f_hz = omega / (2 * np.pi)

        phi_norm = phi / np.sqrt(m_modal_total)

        modes_raw.append(phi)
        freqs_hz.append(f_hz)
        modal_masses.append(m_modal_total)
        modes_norm.append(phi_norm)

    return {
        "x_grid": x_grid,
        "A": A,
        "I": I,
        "freqs_hz": np.array(freqs_hz),
        "omegas": 2 * np.pi * np.array(freqs_hz),
        "modes_raw": np.array(modes_raw),
        "modes_norm": np.array(modes_norm),
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


def simulate_response(L, b, h, E, rho, n_modes, zeta_base, zeta_mode_slope,
                      x_force, x_sensor, force_amplitude, pulse_duration,
                      pulse_rise_tau, pulse_fall_tau, t_end, fs, sensor_mass=0.0):
    validate_inputs(
        L=L,
        b=b,
        h=h,
        E=E,
        rho=rho,
        n_modes=n_modes,
        zeta_base=zeta_base,
        zeta_mode_slope=zeta_mode_slope,
        x_force=x_force,
        x_sensor=x_sensor,
        force_amplitude=force_amplitude,
        pulse_duration=pulse_duration,
        pulse_rise_tau=pulse_rise_tau,
        pulse_fall_tau=pulse_fall_tau,
        t_end=t_end,
        fs=fs,
        sensor_mass=sensor_mass,
    )

    modal = build_modes(
        L=L, b=b, h=h, E=E, rho=rho,
        n_modes=n_modes,
        sensor_mass=sensor_mass,
        x_sensor=x_sensor
    )

    x_grid = modal["x_grid"]
    omegas = modal["omegas"]
    freqs_hz = modal["freqs_hz"]
    modes_norm = modal["modes_norm"]
    zetas = build_modal_damping(
        freqs_hz,
        zeta_base=zeta_base,
        zeta_mode_slope=zeta_mode_slope,
        zeta_max=zeta_max,
    )
    n_active_modes = len(omegas)

    phi_force = np.array([np.interp(x_force, x_grid, modes_norm[i]) for i in range(n_active_modes)])
    phi_sensor = np.array([np.interp(x_sensor, x_grid, modes_norm[i]) for i in range(n_active_modes)])

    t_eval = np.linspace(0.0, t_end, int(t_end * fs))
    y0 = np.zeros(2 * n_active_modes)

    # Ensure the adaptive solver resolves a short force pulse.
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

    # Reconstruct sensor acceleration
    # qdd_i = Q_i(t) - 2*zeta*w_i*qdot_i - w_i^2*q_i
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

    a_sensor = np.sum(phi_sensor[:, None] * qdd, axis=0)
    disp_sensor = np.sum(phi_sensor[:, None] * q, axis=0)
    vel_sensor = np.sum(phi_sensor[:, None] * qd, axis=0)

    return {
        "t": t,
        "freqs_hz": freqs_hz,
        "omegas": omegas,
        "zetas": zetas,
        "x_grid": x_grid,
        "modes_norm": modes_norm,
        "phi_force": phi_force,
        "phi_sensor": phi_sensor,
        "q": q,
        "qd": qd,
        "qdd": qdd,
        "disp_sensor": disp_sensor,
        "vel_sensor": vel_sensor,
        "acc_sensor": a_sensor,
    }


def plot_mode_shapes(x_grid, modes_norm, freqs_hz, n_to_show=4):
    plt.figure(figsize=(9, 5))
    for i in range(min(n_to_show, len(freqs_hz))):
        y = modes_norm[i] / np.max(np.abs(modes_norm[i]))
        plt.plot(x_grid, y, label=f"Mode {i+1}: {freqs_hz[i]:.1f} Hz")
    plt.axhline(0, linewidth=1)
    plt.xlabel("x (m)")
    plt.ylabel("Normalized shape")
    plt.title("Cantilever Mode Shapes")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()


def plot_time_response(t, acc_sensor, disp_sensor=None):
    plt.figure(figsize=(10, 5))
    plt.plot(t, acc_sensor)
    plt.xlabel("Time (s)")
    plt.ylabel("Acceleration (m/s^2)")
    plt.title("Sensor-Side Acceleration Response")
    plt.grid(True)
    plt.tight_layout()

    if disp_sensor is not None:
        plt.figure(figsize=(10, 5))
        plt.plot(t, disp_sensor)
        plt.xlabel("Time (s)")
        plt.ylabel("Displacement (m)")
        plt.title("Sensor-Side Displacement Response")
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
    plt.xlim(0, min(1000, fs / 2))
    plt.grid(True)

    if natural_freqs is not None:
        for f in natural_freqs:
            plt.axvline(f, linestyle="--", alpha=0.5)

    plt.tight_layout()
    return freqs, mag


def report_main_peaks(freqs, mag, n_peaks=8, min_prom_ratio=0.02, min_sep_hz=10.0):
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
        L=L,
        b=b,
        h=h,
        E=E,
        rho=rho,
        n_modes=n_modes,
        zeta_base=zeta_base,
        zeta_mode_slope=zeta_mode_slope,
        x_force=x_force,
        x_sensor=x_sensor,
        force_amplitude=force_amplitude,
        pulse_duration=pulse_duration,
        pulse_rise_tau=pulse_rise_tau,
        pulse_fall_tau=pulse_fall_tau,
        t_end=t_end,
        fs=fs,
        sensor_mass=sensor_mass
    )

    t = result["t"]
    freqs_hz = result["freqs_hz"]
    zetas = result["zetas"]
    x_grid = result["x_grid"]
    modes_norm = result["modes_norm"]
    acc_sensor = result["acc_sensor"]
    disp_sensor = result["disp_sensor"]

    print("Natural frequencies (Hz):")
    for i, f in enumerate(freqs_hz, start=1):
        print(f"  Mode {i}: {f:.2f}  (zeta = {zetas[i-1]:.4f})")

    if show_mode_shapes:
        plot_mode_shapes(x_grid, modes_norm, freqs_hz, n_to_show=min(4, n_modes))

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