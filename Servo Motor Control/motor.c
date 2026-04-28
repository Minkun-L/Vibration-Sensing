#include <stdio.h>
#include <unistd.h>
#include <pigpio.h>

#define SERVO_PIN 18   // GPIO18 (Pin 12)


int angle_to_pulse(int angle)
{
    if (angle < 0) angle = 0;
    if (angle > 180) angle = 180;
    return 500 + (angle * (2500 - 500)) / 180;
}

int main()
{
    if (gpioInitialise() < 0)
    {
        printf("pigpio init failed\n");
        return 1;
    }

    gpioSetMode(SERVO_PIN, PI_OUTPUT);

    for (int angle = 0; angle <= 180; angle += 30)
    {
        int pulse = angle_to_pulse(angle);
        gpioServo(SERVO_PIN, pulse);
        printf("Angle %d → %dus\n", angle, pulse);
        sleep(1);
    }

    for (int angle = 180; angle >= 0; angle -= 30)
    {
        int pulse = angle_to_pulse(angle);
        gpioServo(SERVO_PIN, pulse);
        printf("Angle %d → %dus\n", angle, pulse);
        sleep(1);
    }

    gpioServo(SERVO_PIN, 0);   // Stop PWM
    gpioTerminate();
    return 0;
}
