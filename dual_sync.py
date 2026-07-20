import can
import os
import time
import csv
import sys
from datetime import datetime

# Import dedicated class files
from lib_calex import CalexDCDC
from lib_jkbms import JKBMS

# ==========================================
# 1. MAIN SYSTEM SETTINGS
# ==========================================
CAN_LTO_IFACE = 'can1' # Embedded Aaeon (LTO + JKBMS)
CAN_LA_IFACE = 'can0'  # PCAN USB (LA Battery)
BITRATE = 500000

LOG_HZ = 10.0
PRINT_HZ = 1.0

# --- PHASE SHIFT CONTROL ---
# False = Both Calexes Buck and Boost at the exact same time (0 degrees)
# True  = LTO Bucks while LA Boosts, and vice versa (180 degrees)
COUNTER_PHASE = False 

# ==========================================
# 2. LTO CALEX & JKBMS CONFIGURATION (can1)
# ==========================================
CALEX_DBC_PATH = 'CALEX_DCDC_Database_BCE-24V_V4.dbc'

LTO_SETTINGS = {
    'CAN_HZ': 10.0,
    'RUN_TIME': 5.0,         # Duration of cycle
    'DEAD_TIME': 0.001,      # Relay switch protection buffer
    'BMS_WAKE_LSV': 33.0,
    'BMS_WAKE_AMP': 0.1,
    'BMS_WAKE_TIME': 0.0,    # Set to >0 to trigger wake routine
    'BUCK_HSV': 42.0, 'BUCK_LSV': 34.0, 'BUCK_AMP': 15.0,
    'BOOST_HSV': 52.0, 'BOOST_LSV': 20.0, 'BOOST_AMP': 15.0,
    'LIM_HS_OVP': 56.0, 'LIM_HS_UVP': 22.5,
    'LIM_LS_OVP': 40.0, 'LIM_LS_UVP': 20.0
}

JKBMS_SETTINGS = {
    'CTRL_HZ': 1.0,
    'ENABLE_CHARGE': True,
    'ENABLE_DISCHARGE': True,
    'ENABLE_BALANCE': True
}

# ==========================================
# 3. LA CALEX CONFIGURATION (can0)
# ==========================================
LA_SETTINGS = {
    'CAN_HZ': 10.0,
    'RUN_TIME': 5.0,         # Keep identical to LTO for perfect sync
    'DEAD_TIME': 0.001,      
    'BMS_WAKE_TIME': 0.0,    # LA rig doesn't need BMS wake
    'BUCK_HSV': 42.0, 'BUCK_LSV': 34.0, 'BUCK_AMP': 15.0,
    'BOOST_HSV': 52.0, 'BOOST_LSV': 20.0, 'BOOST_AMP': 15.0,
    'LIM_HS_OVP': 56.0, 'LIM_HS_UVP': 22.5,
    'LIM_LS_OVP': 40.0, 'LIM_LS_UVP': 18.0
}

# ==========================================
# DIRECTORY & FILE SETUP
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
CSV_FILENAME = os.path.join(LOG_DIR, f"sync_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

def main():
    print("--- Starting Dual Unified Control System ---")
    
    # 1. Bind Interfaces
    try:
        bus_lto = can.interface.Bus(interface='socketcan', channel=CAN_LTO_IFACE, bitrate=BITRATE)
        print(f" -> Successfully bound to {CAN_LTO_IFACE} (LTO)")
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to bind to {CAN_LTO_IFACE}. Error: {e}")
        sys.exit(1)

    try:
        bus_la = can.interface.Bus(interface='socketcan', channel=CAN_LA_IFACE, bitrate=BITRATE)
        print(f" -> Successfully bound to {CAN_LA_IFACE} (LA)")
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to bind to {CAN_LA_IFACE}. Error: {e}")
        sys.exit(1)

    # 2. Instantiate Hardware
    dbc_full_path = os.path.join(SCRIPT_DIR, CALEX_DBC_PATH)
    if not os.path.exists(dbc_full_path):
        print(f"CRITICAL ERROR: DBC file not found at {dbc_full_path}")
        sys.exit(1)
        
    calex_lto = CalexDCDC(bus_lto, dbc_full_path, LTO_SETTINGS)
    jkbms = JKBMS(bus_lto, JKBMS_SETTINGS)
    
    calex_la = CalexDCDC(bus_la, dbc_full_path, LA_SETTINGS)

    # 3. Boot Sequence
    calex_lto.boot(init_hardware=True)  # Handles the physical GPIO wake-ups
    calex_la.boot(init_hardware=False)  # Skips GPIOs, only sends CAN limit messages

    # 4. Apply Phase Shift (180 degrees)
    if COUNTER_PHASE:
        print("\n[PHASE SHIFT] Enabled: LA Calex is starting 180-degrees out of phase (BOOST).")
        calex_la.state = calex_la.S_BOOST
        calex_la.seq_tag = "BOOST"

    # 5. Define CSV Header
    header = [
        "Timestamp", 
        "LTO_Seq", "LTO_Mode", "LTO_HS_V", "LTO_LS_V", "LTO_HS_A", "LTO_LS_A", "LTO_Faults",
        "LA_Seq", "LA_Mode", "LA_HS_V", "LA_LS_V", "LA_HS_A", "LA_LS_A", "LA_Faults",
        "Pack_V", "Pack_A", "SOC_%", "T_Max", "T_Min", "Cell_Max_mV", "Cell_Min_mV"
    ]
    header.extend([f"Cell_{i}" for i in range(1, 25)])

    last_log_time = time.time()
    last_print_time = time.time()

    # 6. Main Loop
    with open(CSV_FILENAME, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(header)
        
        print("\n---> Dual Synchronized Loop Running. Press CTRL+C to stop.")
        try:
            while True:
                now = time.time()
                
                # --- A. TIME-BASED TICKS ---
                calex_lto.tick(now)
                calex_la.tick(now)
                jkbms.tick(now)
                
                # --- B. MESSAGE PARSING (LTO BUS) ---
                for _ in range(10): 
                    msg_lto = bus_lto.recv(timeout=0.0) 
                    if not msg_lto: break 
                    
                    if not msg_lto.is_extended_id and msg_lto.arbitration_id in [0x268, 0x269]:
                        calex_lto.parse(msg_lto)
                    elif msg_lto.is_extended_id or msg_lto.arbitration_id in [0x2F4, 0x4F4, 0x5F4]:
                        jkbms.parse(msg_lto)

                # --- C. MESSAGE PARSING (LA BUS) ---
                for _ in range(10):
                    msg_la = bus_la.recv(timeout=0.0)
                    if not msg_la: break
                        
                    if not msg_la.is_extended_id and msg_la.arbitration_id in [0x268, 0x269]:
                        calex_la.parse(msg_la)

                # --- D. SYNCHRONIZED LOGGING ---
                if now - last_log_time >= (1.0 / LOG_HZ):
                    row = [datetime.now().strftime('%H:%M:%S.%f')[:-3]]
                    
                    # LTO Data
                    row.extend([calex_lto.seq_tag, calex_lto.mode, round(calex_lto.telem["HS_V"], 2), round(calex_lto.telem["LS_V"], 2), round(calex_lto.telem["HS_A"], 2), round(calex_lto.telem["LS_A"], 2), calex_lto.faults])
                    # LA Data
                    row.extend([calex_la.seq_tag, calex_la.mode, round(calex_la.telem["HS_V"], 2), round(calex_la.telem["LS_V"], 2), round(calex_la.telem["HS_A"], 2), round(calex_la.telem["LS_A"], 2), calex_la.faults])
                    # JKBMS Data
                    row.extend([round(jkbms.telem["Pack_V"], 2), round(jkbms.telem["Pack_A"], 2), jkbms.telem["SOC"], round(jkbms.telem["Temp_Max_C"], 1), round(jkbms.telem["Temp_Min_C"], 1), jkbms.telem["Cell_Max_mV"], jkbms.telem["Cell_Min_mV"]])
                    row.extend([jkbms.telem[f"Cell_{i}"] for i in range(1, 25)])
                    
                    writer.writerow(row)
                    file.flush() 
                    last_log_time = now

                # --- E. CLEAN TERMINAL PRINTING ---
                if now - last_print_time >= (1.0 / PRINT_HZ):
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f"[{ts}] LTO_CALEX [{calex_lto.seq_tag:5}] HS:{calex_lto.telem['HS_V']:05.2f}V LS:{calex_lto.telem['LS_V']:05.2f}V | BMS: {jkbms.telem['SOC']}%")
                    print(f"[{ts}]  LA_CALEX [{calex_la.seq_tag:5}] HS:{calex_la.telem['HS_V']:05.2f}V LS:{calex_la.telem['LS_V']:05.2f}V")
                    last_print_time = now
                    
                time.sleep(0.005)

        except KeyboardInterrupt:
            print("\nSequence interrupted by user.")
        finally:
            print("Safely sleeping Calexes...")
            calex_lto.send_command(False, 0, 48.0, 24.0, 0.0)
            calex_la.send_command(False, 0, 48.0, 24.0, 0.0)
            time.sleep(0.2)
            
            print("Setting GPIOs to 1 (Idle/High)...")
            os.system('echo 1 > /sys/class/gpio/PAC.06/value 2>/dev/null')
            os.system('echo 1 > /sys/class/gpio/PQ.06/value 2>/dev/null')
            
            calex_lto.sleep_hardware()
            
            bus_lto.shutdown()
            bus_la.shutdown()

if __name__ == "__main__":
    main()