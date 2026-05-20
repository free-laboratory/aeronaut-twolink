import serial
import time
from pynput import keyboard

# ===== RS485 SETTINGS =====
PORT = "COM4"
BAUD = 115200

# ===== ACTUATOR IDS =====
# 15, 12 = top
# 18, 19 = bottom
ACTUATORS = [19, 15, 18, 12]

KEY_TO_ACTUATOR = {
    "w": 19,
    "a": 15,
    "s": 18,
    "d": 12,
}

TARGET_PSI = 5

# Track currently pressed keys
pressed_keys = set()

# Prevent resending identical commands repeatedly
last_selected = set()


def send_cmd(ser, cmd):
    print("Sending:", cmd.strip())
    ser.write((cmd + "\n").encode())
    ser.flush()
    time.sleep(0.01)

    while ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if line:
            print("  RS485:", line)


def inflate_selected(ser, selected_addrs):
    global last_selected
    # Avoid spamming same commands repeatedly
    if set(selected_addrs) == last_selected:
        return
    last_selected = set(selected_addrs)
    for addr in ACTUATORS:
        if addr in selected_addrs:
            send_cmd(ser, f"bb{TARGET_PSI} {addr}")
        else:
            send_cmd(ser, f"ex 0 {addr}")


def exhaust_all(ser):
    global last_selected
    last_selected = set()
    for addr in ACTUATORS:
        send_cmd(ser, f"ex 0 {addr}")


def enable_prints(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"sp 1 {addr}")


def disable_prints(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"sp 0 {addr}")


def update_actuators(ser):
    selected = []

    for key in pressed_keys:
        if key in KEY_TO_ACTUATOR:
            selected.append(KEY_TO_ACTUATOR[key])

    if selected:
        inflate_selected(ser, selected)
    else:
        exhaust_all(ser)


def on_press(key, ser):
    global TARGET_PSI

    try:
        k = key.char.lower()

        if k == "q":
            print("Quitting...")
            return False

        elif k == "+":
            TARGET_PSI += 1
            print(f"Target PSI: {TARGET_PSI}")

        elif k == "-":
            TARGET_PSI = max(0, TARGET_PSI - 1)
            print(f"Target PSI: {TARGET_PSI}")

        pressed_keys.add(k)
        update_actuators(ser)

    except AttributeError:
        pass


def on_release(key, ser):
    try:
        k = key.char.lower()

        if k in pressed_keys:
            pressed_keys.remove(k)

        update_actuators(ser)

    except AttributeError:
        pass


def main():
    print("Opening RS485 port...")

    ser = serial.Serial(PORT, BAUD, timeout=0.1)

    time.sleep(1)

    enable_prints(ser)

    print("\nControls:")
    print("  W/A/S/D -> pressurize actuators")
    print("  Multiple keys supported")
    print("  + / -   -> increase/decrease PSI")
    print("  Q       -> quit")

    listener = keyboard.Listener(
        on_press=lambda key: on_press(key, ser),
        on_release=lambda key: on_release(key, ser)
    )

    listener.start()

    try:
        while listener.is_alive():
            time.sleep(0.01)

    except KeyboardInterrupt:
        pass

    print("Exhausting all actuators...")

    exhaust_all(ser)
    disable_prints(ser)

    ser.close()

    print("RS485 closed.")


if __name__ == "__main__":
    main()