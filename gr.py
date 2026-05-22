"""
================================================================
  GreenCell ESP32 → CSV Logger
  Reads JSON from ESP32 via Serial and saves to CSV file.

  Install dependencies:
      pip install pyserial

  Usage:
      python greencell_logger.py
      python greencell_logger.py --port COM3          (Windows)
      python greencell_logger.py --port /dev/ttyUSB0  (Linux/Mac)
      python greencell_logger.py --port COM3 --baud 115200 --output my_data.csv
================================================================
"""

import serial
import serial.tools.list_ports
import json
import csv
import os
import time
import argparse
from datetime import datetime

# ----------------------------------------------------------------
#  CONFIG DEFAULTS
# ----------------------------------------------------------------
DEFAULT_BAUD    = 115200
DEFAULT_OUTPUT  = "greencell_data.csv"

CSV_HEADERS = [
    "timestamp",
    "openVoltage",
    "loadVoltage",
    "voltageDrop",
    "current",
    "internalResistance",
    "temperature",
    "soc",
    "timeRemaining",
    "status"
]

REQUIRED_KEYS = [
    "openVoltage", "loadVoltage", "current",
    "internalResistance", "temperature", "soc",
    "timeRemaining", "status"
]


# ----------------------------------------------------------------
#  AUTO-DETECT ESP32 PORT
# ----------------------------------------------------------------
def find_esp32_port():
    ports = serial.tools.list_ports.comports()
    keywords = ['usbserial', 'usbmodem', 'esp32', 'cp210', 'ch340', 'ftdi', 'uart', 'acm']

    for port in ports:
        desc = (port.description + port.device).lower()
        if any(k in desc for k in keywords):
            print(f"[✓] Auto-detected ESP32 on: {port.device}")
            return port.device

    # Manual selection if auto-detect fails
    print("\n[!] Could not auto-detect ESP32. Available ports:\n")
    if not ports:
        print("    No serial ports found. Check USB connection.")
        return None

    for i, port in enumerate(ports):
        print(f"    [{i}] {port.device}  —  {port.description}")

    try:
        choice = int(input("\nEnter port number: "))
        return ports[choice].device
    except (ValueError, IndexError):
        print("[✗] Invalid selection.")
        return None


# ----------------------------------------------------------------
#  OPEN SERIAL WITH RETRY
# ----------------------------------------------------------------
def open_serial(port, baud, retries=5, delay=2):
    for attempt in range(1, retries + 1):
        try:
            ser = serial.Serial(port, baud, timeout=3)
            time.sleep(2)   # Wait for ESP32 to reset after DTR toggle
            print(f"[✓] Connected to {port} @ {baud} baud")
            return ser
        except serial.SerialException as e:
            err = str(e)
            if "PermissionError" in err or "Access is denied" in err or "13," in err:
                print(f"[!] Port busy (attempt {attempt}/{retries}). Close Arduino IDE / Serial Monitor and retry in {delay}s...")
                time.sleep(delay)
            else:
                print(f"[✗] Serial error: {e}")
                return None
    print(f"[✗] Could not open {port} after {retries} attempts.")
    return None


# ----------------------------------------------------------------
#  SETUP CSV FILE
# ----------------------------------------------------------------
def setup_csv(filepath):
    file_exists = os.path.isfile(filepath)
    csvfile = open(filepath, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)

    if not file_exists or os.path.getsize(filepath) == 0:
        writer.writeheader()
        print(f"[✓] Created new CSV: {filepath}")
    else:
        print(f"[✓] Appending to existing CSV: {filepath}")

    return csvfile, writer


# ----------------------------------------------------------------
#  PARSE + WRITE ROW
# ----------------------------------------------------------------
def process_line(line, writer, csvfile, row_count):
    line = line.strip()
    if not line.startswith("{"):
        return row_count  # Skip non-JSON lines (human-readable summary)

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        print(f"[!] JSON parse error — skipped: {line[:60]}")
        return row_count

    if not all(k in data for k in REQUIRED_KEYS):
        print(f"[!] Missing keys — skipped: {line[:60]}")
        return row_count

    row = {
        "timestamp":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "openVoltage":        round(data.get("openVoltage", 0), 3),
        "loadVoltage":        round(data.get("loadVoltage", 0), 3),
        "voltageDrop":        round(data.get("voltageDrop", data["openVoltage"] - data["loadVoltage"]), 3),
        "current":            round(data.get("current", 0), 3),
        "internalResistance": round(data.get("internalResistance", 0), 4),
        "temperature":        round(data.get("temperature", 0), 1),
        "soc":                round(data.get("soc", 0), 1),
        "timeRemaining":      round(data.get("timeRemaining", 0), 2),
        "status":             data.get("status", "UNKNOWN")
    }

    writer.writerow(row)
    csvfile.flush()   # Write to disk immediately — no data lost on Ctrl+C

    row_count += 1
    print(
        f"  [{row_count:>4}] {row['timestamp']} | "
        f"V={row['openVoltage']:.3f}V | "
        f"IR={row['internalResistance']:.4f}Ω | "
        f"T={row['temperature']:.1f}°C | "
        f"SoC={row['soc']:.1f}% | "
        f"Status={row['status']}"
    )
    return row_count


# ----------------------------------------------------------------
#  MAIN
# ----------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="GreenCell ESP32 → CSV Logger")
    parser.add_argument("--port",   type=str, default=None,           help="Serial port (e.g. COM3 or /dev/ttyUSB0)")
    parser.add_argument("--baud",   type=int, default=DEFAULT_BAUD,   help="Baud rate (default: 115200)")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT,  help="Output CSV filename")
    args = parser.parse_args()

    print("=" * 60)
    print("  GreenCell ESP32 → CSV Logger")
    print("=" * 60)

    # Resolve port
    port = args.port or find_esp32_port()
    if not port:
        print("[✗] No port available. Exiting.")
        return

    # Open serial
    ser = open_serial(port, args.baud)
    if not ser:
        return

    # Setup CSV
    csvfile, writer = setup_csv(args.output)

    print(f"\n[→] Logging to: {os.path.abspath(args.output)}")
    print("     Press Ctrl+C to stop.\n")
    print(f"  {'#':>4}  {'Timestamp':<21}  {'Open V':>7}  {'IR':>9}  {'Temp':>7}  {'SoC':>6}  Status")
    print("  " + "-" * 75)

    row_count = 0
    line_buffer = ""

    try:
        while True:
            try:
                chunk = ser.read(ser.in_waiting or 1).decode("utf-8", errors="ignore")
                line_buffer += chunk

                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    row_count = process_line(line, writer, csvfile, row_count)

            except serial.SerialException as e:
                print(f"\n[✗] Serial connection lost: {e}")
                print("[→] Attempting to reconnect in 3 seconds...")
                time.sleep(3)
                ser = open_serial(port, args.baud)
                if not ser:
                    print("[✗] Reconnect failed. Exiting.")
                    break

    except KeyboardInterrupt:
        print(f"\n\n[✓] Logging stopped by user.")

    finally:
        csvfile.close()
        if ser and ser.is_open:
            ser.close()
        print(f"[✓] {row_count} rows saved to: {os.path.abspath(args.output)}")
        print("=" * 60)


if __name__ == "__main__":
    main()
