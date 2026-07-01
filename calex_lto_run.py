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

RUN_TIME = 0.5         # Duration of the 60A pulse
DEAD_TIME = 0.001      # Hardware relay switch time

# ==========================================
# 2. TARGET CONFIGURATION
# ==========================================
# BMS Wake-Up Settings
BMS_WAKE_LSV = 33.0     
BMS_WAKE_AMP = 2.0      
BMS_WAKE_TIME = 3.0     

# Normal Operation Settings (60A PULSE LIMITS)
# Buck (Charging Battery)
BUCK_HSV = 42.0         
BUCK_LSV = 34.9         # 12S LTO Absolute Max - Provides headroom for 60A
BUCK_AMP = 30.0         # 60 Amps into the LTO Pack

# Boost (Discharging Battery into 1-Ohm Resistor)
BOOST_HSV = 52.0        # Pushing up to 51V into the 48V node (allows 60A to flow into resistor)
BOOST_LSV = 24.0        # Drops target LVS so Calex pulls current from the battery
BOOST_AMP = 60.0        # 60 Amps pulled from the LTO Pack

# ==========================================
# 3. DIRECTORY & FILE SETUP
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DBC_PATH = os.path.join(SCRIPT_DIR, 'CALEX_DCDC_Database_BCE-24V_V4.dbc')
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
CSV_FILENAME = os.path.join(LOG_DIR, f"calex_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

try:
    db = cantools.database.load_file(DBC_PATH)
    bus = can.interface.Bus(interface='socketcan', channel='can0')
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
    bus.send(can.Message(arbitration_id=0x261, data=db.encode_message('LimitMsg', {'LIM_HS_OVP': 56.0, 'LIM_LS_OVP': 35.0, 'LIM_HS_UVP': 36.0, 'LIM_LS_UVP': 18.0}), is_extended_id=False), timeout=0.1)
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

print("[BOOT] Initialization complete. Transitioning to 60A BUCK/BOOST Cycle mode.")

# ==========================================
# 7. MAIN SEQUENCE (STATE MACHINE)
# ==========================================
S_BUCK = 0
S_DEAD_1 = 1
S_BOOST = 2
S_DEAD_2 = 3

current_state = S_BUCK
last_state_change = time.time()
seq_tag = "BUCK"

print(f"\n---> Starting 60A Pulse Sequence | CAN: {CAN_HZ}Hz | DeadTime: {DEAD_TIME}s")

with open(CSV_FILENAME, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Timestamp", "Sequence", "Mode", "HS_V", "LS_V", "HS_A", "LS_A", "Faults"])

    last_can_time, last_print_time, last_log_time = 0, 0, 0
    telem = {"HS_V": 0, "LS_V": 0, "HS_A": 0, "LS_A": 0}
    current_mode = 0

    try:
        while True:
            now = time.time()
            timestamp_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]

            # --- A. STATE MACHINE ---
            if current_state == S_BUCK:
                seq_tag = "BUCK"
                if now - last_state_change >= RUN_TIME:
                    current_state = S_DEAD_1
                    last_state_change = now
            
            elif current_state == S_DEAD_1:
                seq_tag = "DEAD_TIME"
                if now - last_state_change >= DEAD_TIME:
                    current_state = S_BOOST
                    last_state_change = now
            
            elif current_state == S_BOOST:
                seq_tag = "BOOST"
                if now - last_state_change >= RUN_TIME:
                    current_state = S_DEAD_2
                    last_state_change = now
            
            elif current_state == S_DEAD_2:
                seq_tag = "DEAD_TIME"
                if now - last_state_change >= DEAD_TIME:
                    current_state = S_BUCK
                    last_state_change = now

            # --- B. CAN HEARTBEAT ---
            if now - last_can_time >= (1.0 / CAN_HZ):
                if current_state == S_BUCK:
                    send_command(run=True, direction=0, hs_v=BUCK_HSV, ls_v=BUCK_LSV, ls_curr=BUCK_AMP)
                elif current_state == S_BOOST:
                    send_command(run=True, direction=1, hs_v=BOOST_HSV, ls_v=BOOST_LSV, ls_curr=BOOST_AMP)
                else: 
                    send_command(run=False, direction=0, hs_v=48.0, ls_v=24.0, ls_curr=0.0)
                last_can_time = now

            # --- C. READ TELEMETRY ---
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
                    current_mode = data.get('DCDC_MODE', 0)
                    faults = [k.replace('DCDC_ERROR_', '') for k, v in data.items() if 'ERROR' in k and v == 1]
                    if faults: active_faults = "|".join(faults)

            # --- D. LOGGING & PRINTING ---
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