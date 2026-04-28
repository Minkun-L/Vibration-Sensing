# encoder.py — Quadrature encoder reader for GA37-520 (JGB37-520) DC gearmotor
#
# Motor: GA37-520 (JGB37-520)
#   - 6-wire DC gearmotor with integrated Hall-effect quadrature encoder
#   - M1/M2: motor power terminals (driven at ~6–12V via TB6612FNG)
#   - VCC/GND: encoder power supply (3.3V from Pi)
#   - C1/C2: encoder output channels (digital square waves, A/B phase)
#
# Motor driver: TB6612FNG dual H-bridge
#   - VM: motor supply (2.5–13.5V), VCC: logic supply (2.7–5.5V from Pi)
#   - AIN1/AIN2: direction control pins (driven by Pi GPIO)
#   - PWMA: speed control (PWM from Pi)
#   - AO1/AO2: output to motor M1/M2 (~1.2A continuous per channel)
#   - The TB6612FNG only handles motor actuation — it does NOT process encoder signals
#
# Control loop architecture:
#   Pi → TB6612FNG → motor (actuation)
#   encoder (C1/C2) → Pi GPIO 17/27 (feedback)
#   Shared ground across Pi, TB6612FNG, and motor encoder
#
# Encoder wiring:
#   C1 (channel A) → GPIO 17 (BCM)
#   C2 (channel B) → GPIO 27 (BCM)

import RPi.GPIO as GPIO

ENC_A = 17   # encoder channel A (C1)
ENC_B = 27   # encoder channel B (C2)

count = 0

GPIO.setmode(GPIO.BCM)
GPIO.setup(ENC_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(ENC_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)

prev_a = GPIO.input(ENC_A)

try:
    while True:
        a = GPIO.input(ENC_A)
        b = GPIO.input(ENC_B)
        if a != prev_a:          # edge detected on A — encoder has moved
            # B's level relative to A at the transition determines direction
            if a == b:
                count += 1       # clockwise
            else:
                count -= 1       # counter-clockwise
            print(count)
        prev_a = a

except KeyboardInterrupt:
    GPIO.cleanup()
