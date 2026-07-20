import can
import os
import time
import csv
import sys
from datetime import datetime

# Import dedicated class files
from lib_calex import CalexDCDC
from lib_jkbms import JKBMS

# = STREAMING_CHUNK:Configuring system flags and properties
# ==========================================
# 1. MAIN SETTINGS (FLAGS)
# ==========================================
ENABLE_CALEX = True
ENABLE_JKBMS = True

CAN_INTERFACE = 'can1'
BITRATE = 500000

LOG_HZ = 10.0
PRINT_HZ = 1.0

# ==========================================
# 2. CALEX CONFIGURATION
# ==========================================
CALEX_DBC_PATH = 'CALEX_DCDC_Database_BCE-24V_V4.dbc'

CALEX_SETTINGS = {
    'CAN_HZ': 10.0,
    'RUN_TIME': 5.0,         # Duration of cycle
    'DEAD_TIME': 0.001,      # Relay switch protection buffer
    'BMS_WAKE_LSV': 33.0,
    'BMS_WAKE_AMP': 0.1,
    'BMS_WAKE_TIME': 0.0,    # Set to >0 to trigger wake routine
    'BUCK_HSV': 42.0, 'BUCK_LSV': 35.0, 'BUCK_AMP': 22.5,
    'BOOST_HSV': 52.0, 'BOOST_LSV': 20.0, 'BOOST_AMP': 20.0,
    'LIM_HS_OVP': 56.0, 'LIM_HS_UVP': 22.5,
    'LIM_LS_OVP': 40.0, 'LIM_LS_UVP': 20.0
}

# ==========================================
# 3. JKBMS CONFIGURATION
# ==========================================
JKBMS_SETTINGS = {
    'CTRL_HZ': 1.0,
    'ENABLE_CHARGE': True,
    'ENABLE_DISCHARGE': True,
    'ENABLE_BALANCE': True
}

# = STREAMING_CHUNK:Initializing directory, file writers, and CAN Bus
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
CSV_FILENAME = os.path.join(LOG_DIR, f"sync_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

def main():
    print(f"--- Starting Unified Control System on {CAN_INTERFACE} ---")
    
    try:
        bus = can.interface.Bus(interface='socketcan', channel=CAN_INTERFACE, bitrate=BITRATE)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to bind to {CAN_INTERFACE}. Is it up? Error: {e}")
        sys.exit(1)

    calex, jkbms = None, None

    # Instantiate only the enabled components
    if ENABLE_CALEX:
        calex = CalexDCDC(bus, os.path.join(SCRIPT_DIR, CALEX_DBC_PATH), CALEX_SETTINGS)
        calex.boot()
        
    if ENABLE_JKBMS:
        jkbms = JKBMS(bus, JKBMS_SETTINGS)

# = STREAMING_CHUNK:Building dynamic CSV header
    # Define standard CSV header format
    header = ["Timestamp"]
    if ENABLE_CALEX: header.extend(["Calex_Seq", "Calex_Mode", "HS_V", "LS_V", "HS_A", "LS_A", "Calex_Faults"])
    if ENABLE_JKBMS: header.extend(["Pack_V", "Pack_A", "SOC_%", "T_Max", "T_Min", "Cell_Max_mV", "Cell_Min_mV"])
    if ENABLE_JKBMS: header.extend([f"Cell_{i}" for i in range(1, 25)])

    last_log_time = time.time()
    last_print_time = time.time()

# = STREAMING_CHUNK:Running synchronized while-loop
    with open(CSV_FILENAME, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(header)
        
        print("\n---> Main Synchronized Loop Running. Press CTRL+C to stop.")
        try:
            while True:
                now = time.time()
                
                # --- A. TIME-BASED TICKS (Control logic) ---
                if ENABLE_CALEX: calex.tick(now)
                if ENABLE_JKBMS: jkbms.tick(now)
                
                # --- B. MESSAGE PARSING (Listen to bus) ---
                msg = bus.recv(timeout=0.01) # Small timeout prevents 100% CPU lock
                if msg:
                    # Message ID routing (Objects internally ignore IDs they don't care about)
                    if ENABLE_CALEX and not msg.is_extended_id and msg.arbitration_id in [0x268, 0x269]:
                        calex.parse(msg)
                    if ENABLE_JKBMS:
                        # JKBMS uses standard 0xXF4 and extended 0x18...
                        if msg.is_extended_id or msg.arbitration_id in [0x2F4, 0x4F4, 0x5F4]:
                            jkbms.parse(msg)

                # --- C. SYNCHRONIZED LOGGING ---
                if now - last_log_time >= (1.0 / LOG_HZ):
                    row = [datetime.now().strftime('%H:%M:%S.%f')[:-3]]
                    if ENABLE_CALEX:
                        row.extend([calex.seq_tag, calex.mode, round(calex.telem["HS_V"], 2), round(calex.telem["LS_V"], 2), round(calex.telem["HS_A"], 2), round(calex.telem["LS_A"], 2), calex.faults])
                    if ENABLE_JKBMS:
                        row.extend([round(jkbms.telem["Pack_V"], 2), round(jkbms.telem["Pack_A"], 2), jkbms.telem["SOC"], jkbms.telem["Temp_Max_C"], jkbms.telem["Temp_Min_C"], jkbms.telem["Cell_Max_mV"], jkbms.telem["Cell_Min_mV"]])
                        row.extend([jkbms.telem[f"Cell_{i}"] for i in range(1, 25)])
                    
                    writer.writerow(row)
                    last_log_time = now

                # --- D. CLEAN TERMINAL PRINTING ---
                if now - last_print_time >= (1.0 / PRINT_HZ):
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f"[{ts}]", end=" ")
                    if ENABLE_CALEX:
                        print(f"CALEX [{calex.seq_tag:5}] HS:{calex.telem['HS_V']:05.2f}V LS:{calex.telem['LS_V']:05.2f}V FLT:{calex.faults}", end=" | ")
                    if ENABLE_JKBMS:
                        print(f"BMS: {jkbms.telem['Pack_V']:05.2f}V {jkbms.telem['Pack_A']:05.2f}A {jkbms.telem['SOC']}% TMax:{jkbms.telem['Temp_Max_C']}C", end="")
                    print("") # Newline
                    last_print_time = now

        except KeyboardInterrupt:
            print("\nSequence interrupted by user.")
        finally:
            if ENABLE_CALEX:
                print("Safely sleeping Calex...")
                calex.send_command(False, 0, 48.0, 24.0, 0.0)
                time.sleep(0.2)
                calex.sleep_hardware()
            bus.shutdown()

if __name__ == "__main__":
    main()