import cantools
import can
import os
import time
import csv
import sys
from datetime import datetime

# ==========================================
# 1. TIMING & FREQUENCY CONFIGURATION
# ==========================================
CAN_HZ = 10.0          
PRINT_HZ = 10.0          
LOG_HZ = 10.0          

# ==========================================
# 2. TARGET CONFIGURATION
# ==========================================
# BMS Wake-Up Settings (Still needed to latch the BMS initially)
BMS_WAKE_LSV = 33.0     
BMS_WAKE_AMP = 0.0      
BMS_WAKE_TIME = 1.0     

# Normal Operation Settings (CONTINUOUS DISCHARGE)
# Boost (Discharging Battery into 1-Ohm Resistor)
BOOST_HSV = 52.0        # Headroom to push current into the 48V node
BOOST_LSV = 24.0 - 4.0 #20.0 + 0.0 #26.4        # SAFTEY LIMIT: 2.2V/cell. Stops the JKBMS from tripping at 1.8V!
BOOST_AMP = 45.0 #40.0        # Set to 40A. Warning: 40A into 1-Ohm = 1600W of heat! 

# Dummy Buck params for wake-up only
BUCK_HSV = 48.0         
BUCK_LSV = 40.0 #33.9         

# ==========================================
# 3. DIRECTORY & FILE SETUP
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DBC_PATH = os.path.join(SCRIPT_DIR, 'CALEX_DCDC_Database_BCE-24V_V4.dbc')
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
CSV_FILENAME = os.path.join(LOG_DIR, f"calex_discharge_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

try:
    db = cantools.database.load_file(DBC_PATH)
    bus = can.interface.Bus(interface='socketcan', channel='can1')
except Exception as e:
    print(f"CRITICAL ERROR: {e}")
    sys.exit(1)

# ==========================================
# 4. HARDWARE FUNCTIONS
# ==========================================
def setup_gpio():
    if not os.path.exists('/sys/class/gpio/PAC.06'):
        os.system('echo "PAC.06" > /sys/class/gpio/export 2>/dev/null')
    os.system('echo "out" > /sys/class/gpio/PAC.06/direction')
    os.system('echo 1 > /sys/class/gpio/PAC.06/value') 

    if not os.path.exists('/sys/class/gpio/PQ.06'):
        os.system('echo "PQ.06" > /sys/class/gpio/export 2>/dev/null')
    os.system('echo "out" > /sys/class/gpio/PQ.06/direction')
    os.system('echo 0 > /sys/class/gpio/PQ.06/value') 

def sleep_gpio():
    os.system('echo 1 > /sys/class/gpio/PAC.06/value') 
    os.system('echo 0 > /sys/class/gpio/PQ.06/value') 

def send_command(run, direction, hs_v, ls_v, ls_curr):
    try:
        data = db.encode_message('CommandMsg', {
            'CMD_RUN': 1 if run else 0,
            'CMD_DXN': direction, 'CMD_HSV': hs_v, 'CMD_LSV': ls_v, 'CMD_LS_CURR': ls_curr
        })
        bus.send(can.Message(arbitration_id=0x260, data=data, is_extended_id=False), timeout=0.01)
    except Exception:
        pass

# ==========================================
# 5. INITIALIZATION & SAFETY
# ==========================================
setup_gpio()

print("\n[BOOT] 1. Closing Pre-Charge Relay (PQ.06) to trick Calex...")
os.system('echo 1 > /sys/class/gpio/PQ.06/value')
time.sleep(1.0) 

print("[BOOT] 2. Waking Calex (PAC.06 LOW)... waiting for DSP to boot...")
os.system('echo 0 > /sys/class/gpio/PAC.06/value')
time.sleep(3.0) 

print("[BOOT] 3. Sending safety limits and clearing hardware faults...")
try:
    bus.send(can.Message(arbitration_id=0x261, data=db.encode_message('LimitMsg', {'LIM_HS_OVP': 58.0, 'LIM_LS_OVP': 40.0, 'LIM_HS_UVP': 22.5, 'LIM_LS_UVP': 20.0}), is_extended_id=False), timeout=0.1)
except Exception as e:
    print(f"   [WARNING] LimitMsg failed to send ({e}). Calex might still be booting.")

send_command(False, 0, 48.0, 24.0, 0.0) 
time.sleep(0.5)

# ==========================================
# 6. JKBMS WAKE-UP ROUTINE
# ==========================================
print(f"\n[BOOT] 4. Pushing 33V to trigger JKBMS MOSFETs...")
wake_start = time.time()

while time.time() - wake_start < BMS_WAKE_TIME:
    send_command(run=True, direction=0, hs_v=BUCK_HSV, ls_v=BMS_WAKE_LSV, ls_curr=BMS_WAKE_AMP)
    time.sleep(1.0 / CAN_HZ)

print("[BOOT] 5. Opening Pre-Charge Relay (PQ.06) - JKBMS is now holding the load.")
os.system('echo 0 > /sys/class/gpio/PQ.06/value')
time.sleep(0.5)

print("[BOOT] Initialization complete. Transitioning to CONTINUOUS DISCHARGE.")

# ==========================================
# 7. MAIN SEQUENCE (CONSTANT BOOST)
# ==========================================
seq_tag = "BOOST_DIS"

print(f"\n---> Starting Continuous Discharge | Target: {BOOST_AMP}A | Cutoff: {BOOST_LSV}V")

with open(CSV_FILENAME, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Timestamp", "Sequence", "Mode", "HS_V", "LS_V", "HS_A", "LS_A", "Faults"])

    last_can_time, last_print_time, last_log_time = 0, 0, 0
    telem = {"HS_V": 0, "LS_V": 0, "HS_A": 0, "LS_A": 0}
    current_mode = 0

    active_faults = "None"

    try:
        while True:
            now = time.time()
            timestamp_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            
            # --- A. FAULT RECOVERY ROUTINE ---
            # If the Calex reports an error, toggle CMD_RUN to clear it
            if active_faults != "None":
                print(f"[{timestamp_str}] !!! FAULT DETECTED: {active_faults}. Clearing...")
                send_command(run=False, direction=1, hs_v=BOOST_HSV, ls_v=BOOST_LSV, ls_curr=0.0)
                time.sleep(0.5) # Allow internal state to clear
                # Reset Faults is handled automatically by the next run=True cycle
            
            # --- B. CAN HEARTBEAT (CONSTANT BOOST) ---
            if now - last_can_time >= (1.0 / CAN_HZ):
                # Ensure the Target LS_V is significantly lower than current battery V 
                # to force the converter to pull the full 45A (Constant Current mode)
                send_command(run=True, direction=1, hs_v=BOOST_HSV, ls_v=BOOST_LSV, ls_curr=BOOST_AMP)
                last_can_time = now

            # --- C. READ TELEMETRY ---
            # ... (Keep your existing message decoding logic)
            msg = bus.recv(0.001)
            active_faults = "None"
            if msg:
                if msg.arbitration_id == 0x268:
                    data = db.decode_message(msg.arbitration_id, msg.data)
                    telem["HS_V"] = data.get('HS_VOLT_MEAS', 0)
                    telem["LS_V"] = data.get('LS_VOLT_MEAS', 0)
                    telem["HS_A"] = data.get('HS_CURR_MEAS', 0)
                    telem["LS_A"] = data.get('LS_CURR_MEAS', 0)
                elif msg.arbitration_id == 0x269:
                    data = db.decode_message(msg.arbitration_id, msg.data)
                    #current_mode = data.get('DCDC_MODE', 0)
                    faults = [k.replace('DCDC_ERROR_', '') for k, v in data.items() if 'ERROR' in k and v == 1]
                    if faults: active_faults = "|".join(faults)

            # --- C. LOGGING & PRINTING ---
            if now - last_log_time >= (1.0 / LOG_HZ):
                writer.writerow([timestamp_str, seq_tag, current_mode, round(telem["HS_V"], 2), round(telem["LS_V"], 2), round(telem["HS_A"], 2), round(telem["LS_A"], 2), active_faults])
                last_log_time = now

            if now - last_print_time >= (1.0 / PRINT_HZ):
                if active_faults != "None":
                    print(f"[{timestamp_str}] !!! FAULT: {active_faults} !!! (Mode: {current_mode})")
                else:
                    print(f"[{timestamp_str}] [{seq_tag:9} | Mode:{current_mode}] HS_V:{telem['HS_V']:05.2f}V | LS_V:{telem['LS_V']:05.2f}V | HS_A:{telem['HS_A']:05.2f}A | LS_A:{telem['LS_A']:05.2f}A")
                last_print_time = now

    except KeyboardInterrupt:
        print("\nSequence interrupted.")
    finally:
        send_command(False, 0, 48.0, 24.0, 0)
        time.sleep(0.2)
        sleep_gpio()
        bus.shutdown()