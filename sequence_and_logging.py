import serial
import time
import os
import threading
import csv
from datetime import datetime

# ===== RS485 SETTINGS =====
PORT = "COM4"
BAUD = 115200

# ===== Arduino pressure sensor =====
ARD_PORT = "COM8"
ARD_BAUD = 115200

# ===== Power supply =====
PSU_PORT = "COM19"
PSU_BAUD = 115200

# ===== SAVE SETTINGS =====
SAVE_DIR = r"C:\Users\askar\University of Michigan Dropbox\ENGIN-freelab\people\ahusaini\twolink\sequence_logs"
os.makedirs(SAVE_DIR, exist_ok=True)

SAMPLE_HZ = 10
DT = 1.0 / SAMPLE_HZ
SAVE_EVERY_S = 2.0

# ===== ACTUATORS =====
ACTUATORS = [19, 15, 18, 12]

# ===== THREAD-SAFE COMMAND LOGGING =====
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

    print(f"  Sending: {cmd}")

    update_command_log(cmd)

    ser.write((cmd + "\n").encode())
    ser.flush()

    time.sleep(0.02)

    while ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()

        if line:
            print("  RS485:", line)


def exhaust_all(ser):

    print("\nExhausting all actuators...")

    for addr in ACTUATORS:
        send_cmd(ser, f"ex 0 {addr}")


def set_actuators(ser, selected, psi):

    exhausting = [a for a in ACTUATORS if a not in selected]

    print(f"  Inflating actuators: {selected} to {psi} PSI")
    print(f"  Exhausting actuators: {exhausting}")

    for addr in ACTUATORS:

        if addr in selected and psi > 0:
            send_cmd(ser, f"bb{psi} {addr}")

        else:
            send_cmd(ser, f"ex 0 {addr}")


# ===== PRESSURE / PSU LOGGING =====

def query_psu(psu_ser, cmd: bytes):

    if psu_ser is None:
        return None

    try:

        psu_ser.reset_input_buffer()

        psu_ser.write(cmd + b"\n")
        psu_ser.flush()

        time.sleep(0.05)

        out = psu_ser.readline().decode(errors="ignore").strip()

        return float(out)

    except:
        return None


def _drain_latest_line(ser):

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

    header = [
        "timestamp",
        "t_seconds",
        "arduino_raw_line",
        "pressure_psig",
        "voltage_V",
        "current_A",
        "latest_command"
    ]

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

            actuator_cmds = [
                latest_actuator_cmds[addr]
                for addr in ACTUATORS
            ]

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

            print(
                f"[log] "
                f"t={t:.2f}s | "
                f"pressure={pressure_text} | "
                f"V={voltage:.3f} V | "
                f"I={current:.3f} A"
            )

        else:

            print(
                f"[log] "
                f"t={t:.2f}s | "
                f"pressure={pressure_text} | "
                f"V/I unavailable"
            )

        if (now - last_save) >= SAVE_EVERY_S:

            f.flush()

            last_save = now

        time.sleep(DT)

    f.flush()
    f.close()

    print(f"\nSaved CSV file:\n{filename}")


# ===== SEQUENCES =====

ROLLING_SEQUENCE = [
    {"actuators": [18],         "psi": 5, "time": 3},
    {"actuators": [18, 12],     "psi": 3, "time": 3},
    {"actuators": [12],         "psi": 5, "time": 3},
    {"actuators": [12, 19],     "psi": 3, "time": 3},
    {"actuators": [19],         "psi": 5, "time": 3},
    {"actuators": [19, 15],     "psi": 3, "time": 3},
    {"actuators": [15],         "psi": 5, "time": 3},
    {"actuators": [15, 18],     "psi": 3, "time": 3},
]

INCHING_SEQUENCE = [
    {"actuators": [15, 12], "psi": 5, "time": 1},
    {"actuators": [],       "psi": 0, "time": 1.5},
]

STRAFING_SEQUENCE = [
    {"actuators": [18],         "psi": 5, "time": 1},
    {"actuators": [18, 12],     "psi": 5, "time": 1},
    {"actuators": [12],         "psi": 5, "time": 1},
    {"actuators": [12, 19],     "psi": 5, "time": 1},
    {"actuators": [19],         "psi": 5, "time": 1},
    {"actuators": [19, 15],     "psi": 5, "time": 1},
    {"actuators": [15],         "psi": 5, "time": 1},
    {"actuators": [15, 18],     "psi": 5, "time": 1},
]

SEQUENCE = INCHING_SEQUENCE


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
        f"sequence_log_{start_wall.strftime('%Y%m%d_%H%M%S')}.csv"
    )

    stop_event = threading.Event()

    logger_thread = threading.Thread(
        target=pressure_logger,
        args=(ard_ser, psu_ser, stop_event, filename),
        daemon=True
    )

    logger_thread.start()

    try:

        run_sequence(ser, SEQUENCE, loop=True)

    except KeyboardInterrupt:

        print("\nKeyboard interrupt detected.")

    finally:

        stop_event.set()
        logger_thread.join()

        exhaust_all(ser)

        ser.close()
        ard_ser.close()
        psu_ser.close()

        print("RS485 closed.")
        print("Arduino closed.")
        print("PSU closed.")


if __name__ == "__main__":
    main()