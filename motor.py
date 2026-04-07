
import pigpio
import time

SERVO_PIN = 18  # GPIO18 (Pin 12)

pi = pigpio.pi()
if not pi.connected:
    exit()

def set_angle(angle):
    # SG90/Micro servo range
    pulsewidth = 500 + (angle / 180.0) * 2000
    pi.set_servo_pulsewidth(SERVO_PIN, pulsewidth)

# Move servo
set_angle(0)
time.sleep(1)

set_angle(90)
time.sleep(1)

set_angle(180)
time.sleep(1)

# Stop PWM
pi.set_servo_pulsewidth(SERVO_PIN, 0)
pi.stop()
