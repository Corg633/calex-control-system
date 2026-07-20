import can
import os
import time
import csv
import sys
from datetime import datetime

# Import the dedicated Calex class
from lib_calex import CalexDCDC

# ==========================================
# 1. MAIN SETTINGS (PCAN TEST RIG)
# ==========================================
# Set to can0 for the PCAN USB adapter
CAN_INTERFACE = 'can0'
BITRATE = 500000

LOG_HZ = 10.0
PRINT_HZ = 1.0

# ==========================================
# 2. CALEX CONFIGURATION (LA Battery Test)
# ==========================================
CALEX_DBC_PATH = 'CALEX_DCDC_Database_BCE-24V_V4.dbc'

# Edit these limits based on the LA battery pack specs
CALEX_SETTINGS = {
    'CAN_HZ': 10.0,
    'RUN_TIME': 5.0,         # Duration of charge/discharge cycle
    'DEAD_TIME': 0.001,      # Relay switch protection buffer
    'BMS_WAKE_LSV': 0.0,     # Assuming no JK BMS to wake up on this rig
    'BMS_WAKE_AMP': 0.0,
    'BMS_WAKE_TIME': 0.0,    
    
    # LA Battery Target Settings
    'BUCK_HSV': 42.0, 
    'BUCK_LSV': 34.0, # Adjust for LA
    'BUCK_AMP': 10.0, # Adjust for LA
    
    'BOOST_HSV': 52.0, 
    'BOOST_LSV': 20.0, # Adjust for LA
    'BOOST_AMP': 10.0, # Adjust for LA
    
    # Safety Limits
    'LIM_HS_OVP': 56.0, 
    'LIM_HS_UVP': 22.5,
    'LIM_LS_OVP': 40.0, 
    'LIM_LS_UVP': 18.0   
}

# ==========================================
# 3. DIRECTORY & FILE SETUP
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
CSV_FILENAME = os.path.join(LOG_DIR, f"la_calex_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

def main():
    print(f"--- Starting LA Calex Standalone Test on {CAN_INTERFACE} ---")
    
    try:
        bus = can.interface.Bus(interface='socketcan', channel=CAN_INTERFACE, bitrate=BITRATE)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to bind to {CAN_INTERFACE}. Error: {e}")
        sys.exit(1)

    calex = CalexDCDC(bus, os.path.join(SCRIPT_DIR, CALEX_DBC_PATH), CALEX_SETTINGS)
    calex.boot()

    header = ["Timestamp", "Calex_Seq", "Calex_Mode", "HS_V", "LS_V", "HS_A", "LS_A", "Calex_Faults"]
    last_log_time = time.time()
    last_print_time = time.time()

    with open(CSV_FILENAME, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(header)
        
        print("\n---> LA Calex Test Loop Running. Press CTRL+C to stop.")
        try:
            while True:
                now = time.time()
                
                # A. Control Logic Tick
                calex.tick(now)
                
                # B. Receive Telemetry
                msg = bus.recv(timeout=0.01)
                if msg and not msg.is_extended_id and msg.arbitration_id in [0x268, 0x269]:
                    calex.parse(msg)

                # C. CSV Logging
                if now - last_log_time >= (1.0 / LOG_HZ):
                    row = [
                        datetime.now().strftime('%H:%M:%S.%f')[:-3],
                        calex.seq_tag, calex.mode, 
                        round(calex.telem["HS_V"], 2), round(calex.telem["LS_V"], 2), 
                        round(calex.telem["HS_A"], 2), round(calex.telem["LS_A"], 2), 
                        calex.faults
                    ]
                    writer.writerow(row)
                    last_log_time = now

                # D. Terminal Printing
                if now - last_print_time >= (1.0 / PRINT_HZ):
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f"[{ts}] LA CALEX [{calex.seq_tag:5}] HS:{calex.telem['HS_V']:05.2f}V LS:{calex.telem['LS_V']:05.2f}V HS_A:{calex.telem['HS_A']:05.2f}A LS_A:{calex.telem['LS_A']:05.2f}A FLT:{calex.faults}")
                    last_print_time = now

        except KeyboardInterrupt:
            print("\nSequence interrupted by user.")
        finally:
            print("Safely sleeping Calex...")
            calex.send_command(False, 0, 48.0, 24.0, 0.0)
            time.sleep(0.2)
            calex.sleep_hardware()
            bus.shutdown()

if __name__ == "__main__":
    main()