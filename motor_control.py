# motor_control.py — Position-controlled move for GA37-520 via TB6612FNG
#
# Motor: GA37-520 (JGB37-520)
#   - M1/M2: motor power (via TB6612FNG AO1/AO2)
#   - VCC/GND: encoder power (3.3V from Pi)
#   - C1 (channel A) → GPIO 17 (BCM)
#   - C2 (channel B) → GPIO 27 (BCM)
#
# TB6612FNG wiring:
#   PWMA  → GPIO 18  (hardware PWM0, 1 kHz)
#   AIN1  → GPIO 23  (direction)
#   AIN2  → GPIO 24  (direction)
#   STBY  → GPIO 25  (HIGH = driver enabled)
#   VM    → external motor supply (6–12V)
#   VCC   → Pi 3.3V (logic)
#   GND   → shared ground
#
# Motion:
#   Phase 1 — wait at 0 (script starts here)
#   Phase 2 — drive to -100
#   Phase 3 — return to 0

import time
import math
import RPi.GPIO as GPIO

# ── Pin definitions ───────────────────────────────────────────
ENC_A = 17   # encoder channel A (C1)
ENC_B = 27   # encoder channel B (C2)
PWMA  = 18   # PWM speed control
AIN1  = 23   # direction pin 1
AIN2  = 24   # direction pin 2
STBY  = 25   # standby (HIGH = enabled)

# ── Motion parameters ─────────────────────────────────────────
MOTOR_SPEED = 50     # PWM duty cycle, 0–100 (%)
STROKE_POS  = 50   # encoder count at end of stroke
HOME_POS    = 0      # home / return position
TIMEOUT_S   = 30.0   # per-phase safety timeout (seconds)

# ── Encoder state ─────────────────────────────────────────────
count = 0
_enc_state = 0  # initialised after GPIO setup

# Full X4 quadrature state-transition table.
# Index = (prev_state << 2) | curr_state  where state = (A << 1) | B
# Sequence CW : 00→01→11→10→00  (+1 each step)
# Sequence CCW: 00→10→11→01→00  (-1 each step)
# Invalid / no-move transitions → 0
_TRANS = [
#   curr: 00  01  10  11
         0, +1, -1,  0,   # prev: 00
        -1,  0,  0, +1,   # prev: 01
        +1,  0,  0, -1,   # prev: 10
         0, -1, +1,  0,   # prev: 11
]

def _enc_callback(channel):
    """Full quadrature state-machine — fires on any edge of A or B.
    Back-and-forth oscillation cancels cleanly: each step forward
    is undone by the matching step back."""
    global count, _enc_state
    a = GPIO.input(ENC_A)
    b = GPIO.input(ENC_B)
    curr_state = (a << 1) | b
    count += _TRANS[(_enc_state << 2) | curr_state]
    _enc_state = curr_state

# ── GPIO setup ────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)

# Encoder inputs with pull-ups (same as encoder.py)
GPIO.setup(ENC_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(ENC_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
# Initialise state before attaching interrupts
_enc_state = (GPIO.input(ENC_A) << 1) | GPIO.input(ENC_B)
GPIO.add_event_detect(ENC_A, GPIO.BOTH, callback=_enc_callback)
GPIO.add_event_detect(ENC_B, GPIO.BOTH, callback=_enc_callback)

# Motor driver outputs
GPIO.setup(AIN1, GPIO.OUT)
GPIO.setup(AIN2, GPIO.OUT)
GPIO.setup(STBY, GPIO.OUT)
GPIO.setup(PWMA, GPIO.OUT)

pwm = GPIO.PWM(PWMA, 1000)   # 1 kHz carrier
pwm.start(0)
GPIO.output(STBY, GPIO.HIGH)  # enable driver

# ── Motor helpers ─────────────────────────────────────────────
def motor_cw(speed):
    """Spin clockwise — count increases."""
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.LOW)
    pwm.ChangeDutyCycle(speed)

def motor_ccw(speed):
    """Spin counter-clockwise — count decreases."""
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.HIGH)
    pwm.ChangeDutyCycle(speed)

def motor_stop():
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.LOW)
    pwm.ChangeDutyCycle(0)

# Exponential decay parameters
DECAY_RATE = 3.0   # higher = faster drop-off; 3.0 gives ~95% speed reduction over the stroke
MIN_SPEED  = 5    # minimum duty cycle (%) — below this most motors stall

def move_to(target, speed=MOTOR_SPEED, timeout=TIMEOUT_S, decay=False):
    """Drive motor until count reaches target, then stop.
    Handles both directions; stops on timeout.
    decay=True: speed follows exponential decay from full speed to MIN_SPEED."""
    t0 = time.perf_counter()
    last_printed = None
    T = []
    initial_dist = abs(target - count)
    while True:
        pos = count
        T.append(pos)
        if pos != last_printed:
            print(f"  count = {pos}")
            last_printed = pos
        # Compute current speed
        if decay and initial_dist > 0:
            fraction_done = 1.0 - abs(target - pos) / initial_dist
            current_speed = max(MIN_SPEED, speed * math.exp(-DECAY_RATE * fraction_done))
        else:
            current_speed = speed
        if pos < target:
            motor_cw(current_speed)
            if len(T) > 50 and (max(T[-70:]) - min(T[-70:]) < 2):
                break
        elif pos > target:
            motor_ccw(current_speed)
            if len(T) > 50 and (max(T[-70:]) - min(T[-70:]) < 2):
                break
        else:
            break
        if time.perf_counter() - t0 > timeout:
            print(f"Timeout! Stopped at count={count}, target={target}")
            break
        time.sleep(0.001)
    motor_stop()



# ── Main sequence ─────────────────────────────────────────────
NUM_CYCLES = 10

try:
    for cycle in range(NUM_CYCLES):
        print(f"\nCycle {cycle + 1}/{NUM_CYCLES}")

        move_to(count + 1000)
        print(f"  Forward done: {count}")

        move_to(count - 1000, decay=True)
        print(f"  Return done:  {count}")

        if cycle < NUM_CYCLES - 1:
            print("  Pausing 0.5s...")
            time.sleep(0.5)

    motor_stop()
    print("\nAll cycles complete.")

except KeyboardInterrupt:
    print("\nInterrupted.")
    motor_stop()

finally:
    
    pwm.stop()
    del pwm
    GPIO.cleanup()
