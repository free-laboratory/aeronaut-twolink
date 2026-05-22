import serial
import time
import os
import threading
import csv
from datetime import datetime

# ===== RS485 SETTINGS =====
PORT = "COM8"
BAUD = 115200

# ===== Arduino (pump pressure) settings =====
ARD_PORT = "COM4"
ARD_BAUD = 115200

# ===== Power supply settings =====
# Used to log pump voltage/current from the PSU.
PSU_PORT = "COM19"
PSU_BAUD = 115200

# ===== SAVE SETTINGS =====
SAVE_DIR = r"C:\Users\april\Documents\SCHOOL\research\FREE\Fabric Based Robot\Code\mocap_multiprocess\data_log\untethered inchworm"
os.makedirs(SAVE_DIR, exist_ok=True)

SAMPLE_HZ = 10
DT = 1.0 / SAMPLE_HZ
SAVE_EVERY_S = 2.0

# ===== DEFAULT ACTUATOR IDS =====
ACTUATORS = [19, 15, 18, 17]

TARGET_PSI = 5

command_lock = threading.Lock()
latest_command_text = ""
latest_actuator_cmds = {addr: "" for addr in ACTUATORS}


def update_command_log(cmd):
    global latest_command_text

    with command_lock:
        latest_command_text = cmd.strip()

        parts = cmd.strip().split()

        try:
            if parts[0].startswith("bb"):
                addr = int(parts[1])
                if addr in latest_actuator_cmds:
                    latest_actuator_cmds[addr] = cmd.strip()

            elif parts[0] in ["ex", "sp", "ss", "in"]:
                addr = int(parts[2])
                if addr in latest_actuator_cmds:
                    latest_actuator_cmds[addr] = cmd.strip()
        except:
            pass


def send_cmd(ser, cmd):
    print("Sending:", cmd.strip())
    update_command_log(cmd)

    ser.write((cmd + "\n").encode())
    ser.flush()
    time.sleep(0.05)

    # print any response
    while ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if line:
            print("  RS485:", line)


def query_psu(psu_ser, cmd: bytes):
    """
    Query PSU and return a float when possible.
    Example commands:
      MEAS:VOLT?
      MEAS:CURR?
    """
    if psu_ser is None:
        return None

    try:
        psu_ser.reset_input_buffer()
        psu_ser.write(cmd + b"\n")
        psu_ser.flush()
        time.sleep(0.05)
        out = psu_ser.readline().decode(errors="ignore").strip()
        return float(out)
    except Exception:
        return None


def _drain_latest_line(ser) -> str:
    line = ""
    while ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
    time.sleep(0.005)
    while ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
    return line


def parse_arduino_pressure(line):
    if line and (not line.lower().startswith("time_s")) and (not line.startswith("#")):
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                return float(parts[1])
            except:
                pass
    return None


def pressure_logger(ard_ser, psu_ser, stop_event, filename):
    f = open(filename, "w", newline="", encoding="utf-8")
    w = csv.writer(f)

    header = ["timestamp", "t_seconds", "arduino_raw_line", "pressure_psig", "voltage_V", "current_A", "latest_command"]
    header += [f"actuator_{addr}_cmd" for addr in ACTUATORS]
    w.writerow(header)
    f.flush()

    start_time = time.monotonic()
    last_save = time.monotonic()

    print(f"\nLogging CSV file to:\n{filename}\n")

    while not stop_event.is_set():
        now = time.monotonic()
        t = now - start_time

        line = _drain_latest_line(ard_ser)
        pressure = parse_arduino_pressure(line)

        voltage = query_psu(psu_ser, b"MEAS:VOLT?")
        current = query_psu(psu_ser, b"MEAS:CURR?")

        with command_lock:
            cmd_text = latest_command_text
            actuator_cmds = [latest_actuator_cmds[addr] for addr in ACTUATORS]

        timestamp = datetime.now().isoformat(timespec="milliseconds")

        w.writerow([
            timestamp,
            f"{t:.4f}",
            line,
            pressure,
            voltage,
            current,
            cmd_text,
            *actuator_cmds
        ])

        if pressure is not None:
            pressure_text = f"{pressure:.2f} psig"
        else:
            pressure_text = "no valid reading"

        if voltage is not None and current is not None:
            print(f"[log] t={t:.2f}s | pressure={pressure_text} | V={voltage:.3f} V | I={current:.3f} A")
        else:
            print(f"[log] t={t:.2f}s | pressure={pressure_text} | V/I unavailable")

        if (now - last_save) >= SAVE_EVERY_S:
            f.flush()
            last_save = now

        time.sleep(DT)

    f.flush()
    f.close()
    print(f"\nSaved CSV file:\n{filename}")


def inflate_all(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"bb{TARGET_PSI} {addr}")


def exhaust_all(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"ex 0 {addr}")


def inflate_one(ser, addr):
    inflate_selected(ser, [addr])


def inflate_selected(ser, selected_addrs):
    for addr in ACTUATORS:
        if addr in selected_addrs:
            send_cmd(ser, f"bb{TARGET_PSI} {addr}")
        else:
            send_cmd(ser, f"ex 0 {addr}")


def exhaust_one(ser, addr):
    send_cmd(ser, f"ex 0 {addr}")


def enable_prints(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"sp 1 {addr}")


def disable_prints(ser):
    for addr in ACTUATORS:
        send_cmd(ser, f"sp 0 {addr}")


def main():

    print("Opening RS485 port...")
    ser = serial.Serial(PORT, BAUD, timeout=0.5)

    print("Opening Arduino port...")
    ard_ser = serial.Serial(ARD_PORT, ARD_BAUD, timeout=0.5)

    print("Opening PSU port...")
    psu_ser = serial.Serial(PSU_PORT, PSU_BAUD, timeout=1)

    time.sleep(2)

    start_wall = datetime.now()
    filename = os.path.join(
        SAVE_DIR,
        f"untethered_inchworm_log_{start_wall.strftime('%Y%m%d_%H%M%S')}.csv"
    )

    stop_event = threading.Event()
    logger_thread = threading.Thread(
        target=pressure_logger,
        args=(ard_ser, psu_ser, stop_event, filename),
        daemon=True
    )
    logger_thread.start()

    enable_prints(ser)

    print("\nCommands:")
    print("  a          -> inflate ALL actuators")
    print("  s          -> exhaust ALL actuators")
    print("  z          -> inflate 18 and 17, exhaust 19 and 15")
    print("  x          -> inflate 15 and 19, exhaust 18 and 17")
    print("  <id>       -> inflate actuator, exhaust all others (ex: 19)")
    print("  <id> <id>  -> inflate two actuators, exhaust all others (ex: 19 15)")
    print("  x<id>      -> exhaust actuator (ex: x19)")
    print("  psi <n>    -> change target pressure")
    print("  q          -> quit and save CSV file")

    global TARGET_PSI

    while True:

        cmd = input("\nEnter command: ").strip()

        if cmd == "a":
            inflate_all(ser)

        elif cmd == "s":
            exhaust_all(ser)

        elif cmd == "z":
            inflate_selected(ser, [18, 17])

        elif cmd == "x":
            inflate_selected(ser, [15, 19])

        elif cmd.startswith("x"):
            try:
                addr = int(cmd[1:])
                exhaust_one(ser, addr)
            except:
                print("Invalid command (use x<ID>)")

        elif cmd.startswith("psi"):
            try:
                TARGET_PSI = int(cmd.split()[1])
                print("New target PSI:", TARGET_PSI)
            except:
                print("Usage: psi 10")

        elif all(part.isdigit() for part in cmd.split()):
            selected_addrs = [int(part) for part in cmd.split()]
            inflate_selected(ser, selected_addrs)

        elif cmd == "q":
            break

        else:
            print("Unknown command")

    stop_event.set()
    logger_thread.join()

    disable_prints(ser)

    ser.close()
    ard_ser.close()
    psu_ser.close()
    print("RS485 closed.")
    print("Arduino closed.")
    print("PSU closed.")


if __name__ == "__main__":
    main()