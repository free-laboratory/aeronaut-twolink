import serial
import time

# ===== RS485 SETTINGS =====
PORT = "COM4"
BAUD = 115200

# ===== ACTUATOR IDS =====
# 15, 12 = top
# 18, 19 = bottom
ACTUATORS = [19, 15, 18, 12]

TOP_ACTUATORS = [15, 12]
BOTTOM_ACTUATORS = [18, 19]

KEY_TO_ACTUATOR = {
    "w": 19,
    "a": 15,
    "s": 18,
    "d": 12,
}

TARGET_PSI = 5


def send_cmd(ser, cmd):
    print("Sending:", cmd.strip())
    ser.write((cmd + "\n").encode())
    ser.flush()
    time.sleep(0.05)

    while ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if line:
            print("  RS485:", line)


def inflate_selected(ser, selected_addrs):
    for addr in ACTUATORS:
        if addr in selected_addrs:
            send_cmd(ser, f"bb{TARGET_PSI} {addr}")
        else:
            send_cmd(ser, f"ex 0 {addr}")


def exhaust_all(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"ex 0 {addr}")


def enable_prints(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"sp 1 {addr}")


def disable_prints(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"sp 0 {addr}")


def main():
    global TARGET_PSI

    print("Opening RS485 port...")
    ser = serial.Serial(PORT, BAUD, timeout=0.5)

    time.sleep(1)
    enable_prints(ser)

    print("\nCommands:")
    print("  w       -> inflate actuator 18, exhaust all others")
    print("  a       -> inflate actuator 19, exhaust all others")
    print("  s       -> inflate actuator 15, exhaust all others")
    print("  d       -> inflate actuator 12, exhaust all others")
    print("  b       -> inflate BOTTOM actuators 18 and 19 to target psi")
    print("  t       -> inflate TOP actuators 15 and 12 to target psi")
    print("  x       -> exhaust ALL actuators")
    print("  psi <n> -> change target pressure")
    print("  q       -> quit")

    while True:
        cmd = input("\nEnter command: ").strip().lower()

        if cmd in KEY_TO_ACTUATOR:
            inflate_selected(ser, [KEY_TO_ACTUATOR[cmd]])

        elif cmd == "b":
            inflate_selected(ser, BOTTOM_ACTUATORS)

        elif cmd == "t":
            inflate_selected(ser, TOP_ACTUATORS)

        elif cmd == "x":
            exhaust_all(ser)

        elif cmd.startswith("psi"):
            try:
                TARGET_PSI = int(cmd.split()[1])
                print("New target PSI:", TARGET_PSI)
            except:
                print("Usage: psi 3")

        elif cmd == "q":
            break

        else:
            print("Unknown command")

    exhaust_all(ser)
    disable_prints(ser)
    ser.close()
    print("RS485 closed.")


if __name__ == "__main__":
    main()