# motor_control2.py — Ballistic-strike impulse control for GA37-520 via TB6612FNG
#
# Algorithm (4-state per cycle):
#   State 1 — HOME:    retract at low speed until stall at wall → count = 0
#   State 2 — LAUNCH:  drive forward at high PWM, cut drive at RELEASE_COUNT
#                      (before ground contact) so hammer hits by pure momentum
#   State 3 — RELEASE: coast — hammer impacts and bounces freely, no motor push
#   State 4 — RETRACT: reverse hard, slow near home, short-brake to park at wall
#
# Why this is better than stall-at-ground (motor_control.py):
#   - Drive is cut BEFORE contact → no sustained motor force during impact
#   - Contact time ≈ elastic collision, not "push until stall" (50 ms+ savings)
#   - Clean impulse → wider high-frequency excitation bandwidth
#
# TB6612FNG drive modes used:
#   CW          AIN1=H AIN2=L PWM>0   — forward drive
#   CCW         AIN1=L AIN2=H PWM>0   — reverse drive
#   Coast       AIN1=L AIN2=L PWM=0   — high-Z, motor spins freely
#   Short brake AIN1=H AIN2=H PWM=100 — active regen brake, holds position

import time
import RPi.GPIO as GPIO

# ── Pin definitions ───────────────────────────────────────────
ENC_A = 17   # encoder channel A (C1)
ENC_B = 27   # encoder channel B (C2)
PWMA  = 18   # PWM speed control
AIN1  = 23   # direction pin 1
AIN2  = 24   # direction pin 2
STBY  = 25   # standby (HIGH = enabled)

# ── Tunable parameters ────────────────────────────────────────
NUM_CYCLES          = 10

# State 1 — Home
HOME_SPEED          = 20    # PWM % for homing retract
HOME_STALL_WINDOW   = 100    # samples to check for stall
HOME_STALL_COUNTS   = 2     # max count change within window to declare stall

# State 2 — Launch
LAUNCH_SPEED        = 100    # PWM % for forward strike
RELEASE_COUNT       = 116    # encoder count at which forward drive is cut
                             # tune this so the hammer just barely reaches the target
                             # with residual momentum (< actual ground-contact count)

# State 3 — Release / Impact
COAST_DEADTIME_MS   = 12     # ms to wait in coast before retracting
                             # long enough for hammer to hit and start bouncing back

# State 4 — Retract
RETRACT_SPEED       = 35    # PWM % for fast retract
RETRACT_SLOW_AT     = 50   # switch to slow speed when count <= this (near home)
RETRACT_SLOW_SPEED  = 0     # PWM % for final slow settle onto wall

CYCLE_PAUSE_S       = 0.5   # pause between cycles (s)
TIMEOUT_S           = 10.0  # per-state safety timeout (s)

# ── Encoder state ─────────────────────────────────────────────
count = 0
_enc_state = 0  # initialised after GPIO setup

# Full X4 quadrature state-transition table.
# Index = (prev_state << 2) | curr_state  where state = (A<<1)|B
_TRANS = [
#   curr: 00  01  10  11
         0, +1, -1,  0,   # prev: 00
        -1,  0,  0, +1,   # prev: 01
        +1,  0,  0, -1,   # prev: 10
         0, -1, +1,  0,   # prev: 11
]

def _enc_callback(channel):
    global count, _enc_state
    a = GPIO.input(ENC_A)
    b = GPIO.input(ENC_B)
    curr_state = (a << 1) | b
    count += _TRANS[(_enc_state << 2) | curr_state]
    _enc_state = curr_state

# ── GPIO setup ────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setup(ENC_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(ENC_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
_enc_state = (GPIO.input(ENC_A) << 1) | GPIO.input(ENC_B)
GPIO.add_event_detect(ENC_A, GPIO.BOTH, callback=_enc_callback)
GPIO.add_event_detect(ENC_B, GPIO.BOTH, callback=_enc_callback)

GPIO.setup(AIN1, GPIO.OUT)
GPIO.setup(AIN2, GPIO.OUT)
GPIO.setup(STBY, GPIO.OUT)
GPIO.setup(PWMA, GPIO.OUT)
pwm = GPIO.PWM(PWMA, 1000)   # 1 kHz carrier
pwm.start(0)
GPIO.output(STBY, GPIO.HIGH)

# ── Driver helpers ────────────────────────────────────────────
def motor_cw(speed):
    """Forward drive — count increases."""
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.HIGH)
    pwm.ChangeDutyCycle(speed)

def motor_ccw(speed):
    """Reverse drive — count decreases."""
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.LOW)
    pwm.ChangeDutyCycle(speed)

def motor_coast():
    """High-Z: remove all drive, motor spins freely."""
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.LOW)
    pwm.ChangeDutyCycle(0)

def motor_brake():
    """Short brake: both outputs HIGH — active regenerative braking."""
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.HIGH)
    pwm.ChangeDutyCycle(100)

# ── State machine ─────────────────────────────────────────────

def state_home():
    """STATE 1: Retract to home wall at low speed; stall → short-brake → count = 0."""
    global count
    print("  [HOME] Retracting to home wall...")
    t0 = time.perf_counter()
    history = []
    while True:
        motor_cw(HOME_SPEED)
        history.append(count)
        if len(history) > HOME_STALL_WINDOW:
            window = history[-HOME_STALL_WINDOW:]
            if max(window) - min(window) <= HOME_STALL_COUNTS:
                break
        if time.perf_counter() - t0 > TIMEOUT_S:
            print("  [HOME] Timeout!")
            break
        time.sleep(0.001)
    motor_brake()          # hold firmly against wall
    time.sleep(0.02)
    motor_coast()
    count = 0              # wall = absolute zero reference
    print("  [HOME] Done — count reset to 0.")


def state_launch():
    """STATE 2: Drive forward at LAUNCH_SPEED; cut drive at RELEASE_COUNT."""
    print(f"  [LAUNCH] Driving to release point (count={RELEASE_COUNT})...")
    t0 = time.perf_counter()
    while True:
        motor_ccw(LAUNCH_SPEED)
        if count <= -RELEASE_COUNT:
            break
        if time.perf_counter() - t0 > TIMEOUT_S:
            print("  [LAUNCH] Timeout!")
            break
        time.sleep(0.0005)   # tight poll for accurate release timing
    motor_coast()            # cut drive — hammer continues by momentum
    print(f"  [LAUNCH] Drive cut at count={count}.")
    
def state_launch_reversed():
    """STATE 2: Drive forward at LAUNCH_SPEED; cut drive at RELEASE_COUNT."""
    print(f"  [LAUNCH] Driving to release point (count={RELEASE_COUNT})...")
    t0 = time.perf_counter()
    while True:
        motor_cw(80)
        if count >= -120:
            motor_ccw(0)
            print(count)
            time.sleep(0.5)
            break
        if time.perf_counter() - t0 > TIMEOUT_S:
            print("  [LAUNCH] Timeout!")
            break
        time.sleep(0.0005)   # tight poll for accurate release timing
    print(f"  [LAUNCH] Drive cut at count={count}.")


def state_release():
    """STATE 3: Coast while hammer impacts target and bounces back freely."""
    print(f"  [RELEASE] Coasting {COAST_DEADTIME_MS} ms through impact...")
    time.sleep(COAST_DEADTIME_MS / 1000.0)
    print(f"  [RELEASE] Done, count={count}.")


def state_retract():
    """STATE 4: Fast retract, slow near home, short-brake to park at wall."""
    print("  [RETRACT] Retracting...")
    t0 = time.perf_counter()
    history = []
    while True:
        pos = count
        history.append(pos)
        # Two-speed: fast retract until close to home, then settle slowly
        if pos >= -RETRACT_SLOW_AT:
            motor_cw(RETRACT_SLOW_SPEED)
            # Stall detection only active in slow zone (near home)
            if len(history) > HOME_STALL_WINDOW:
                window = history[-HOME_STALL_WINDOW:]
                if max(window) - min(window) <= HOME_STALL_COUNTS:
                    break
        else:
            motor_cw(RETRACT_SPEED)
        if time.perf_counter() - t0 > TIMEOUT_S:
            print("  [RETRACT] Timeout!")
            break
        time.sleep(0.001)
    motor_brake()
    time.sleep(0.02)
    motor_coast()
    print(f"  [RETRACT] Parked at count={count}.")


# ── Main sequence ─────────────────────────────────────────────
try:
    for cycle in range(NUM_CYCLES):
        print(f"\nCycle {cycle + 1}/{NUM_CYCLES}")
        state_home()
        state_launch()
        state_release()
        state_launch_reversed()
        state_home()
        #state_retract()
        if cycle < NUM_CYCLES - 1:
            print(f"  Pausing {CYCLE_PAUSE_S}s...")
            time.sleep(CYCLE_PAUSE_S)

    motor_coast()
    print("\nAll cycles complete.")

except KeyboardInterrupt:
    print("\nInterrupted.")
    motor_coast()

finally:
    pwm.stop()
    del pwm
    GPIO.cleanup()
