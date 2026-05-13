import serial
import time

PORT = "COM4"
BAUD = 115200

ACTUATORS = [19, 15, 18, 12]


def send_cmd(ser, cmd):
    print(f"  Sending: {cmd}")
    ser.write((cmd + "\n").encode())
    ser.flush()


def exhaust_all(ser):
    print("\nExhausting all actuators...")
    for addr in ACTUATORS:
        send_cmd(ser, f"ex 0 {addr}")


def set_actuators(ser, selected, psi):
    exhausting = [a for a in ACTUATORS if a not in selected]
    print(f"  Inflating actuators: {selected} to {psi} PSI")
    print(f"  Exhausting actuators: {exhausting}")

    for addr in ACTUATORS:
        if addr in selected:
            send_cmd(ser, f"bb{psi} {addr}")
        else:
            send_cmd(ser, f"ex 0 {addr}")


SEQUENCE = [
    {"actuators": [18],         "psi": 5, "time": 3},
    {"actuators": [18, 19],     "psi": 3, "time": 3},
    {"actuators": [19],         "psi": 5, "time": 3},
    {"actuators": [19, 15],     "psi": 3, "time": 3},
    {"actuators": [15],         "psi": 5, "time": 3},
    {"actuators": [15, 12],     "psi": 3, "time": 3},
    {"actuators": [12],         "psi": 5, "time": 3},
    {"actuators": [12, 18],     "psi": 3, "time": 3},
]


def run_sequence(ser, sequence, loop=False):

    step_count = len(sequence)
    cycle_num = 1

    while True:

        print(f"\n========== STARTING CYCLE {cycle_num} ==========")

        for i, step in enumerate(sequence):

            print("\n----------------------------------------")
            print(f"Step {i+1}/{step_count}")
            print(f"Duration: {step['time']} seconds")
            set_actuators(
                ser,
                step["actuators"],
                step["psi"]
            )
            time.sleep(step["time"])

        cycle_num += 1

        if not loop:
            break


def main():
    print("Opening serial port...")
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    time.sleep(1)

    try:
        run_sequence(ser, SEQUENCE, loop=True)

    except KeyboardInterrupt:
        print("\n\nKeyboard interrupt detected.")

    finally:
        # ALWAYS exhaust everything before closing
        exhaust_all(ser)
        ser.close()
        print("Serial port closed.")


if __name__ == "__main__":
    main()