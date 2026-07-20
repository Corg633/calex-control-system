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
CAN_HZ = 10.0          # CAN heartbeat frequency
PRINT_HZ = 10.0          # Terminal printout frequency
LOG_HZ = 10.0          # CSV logging frequency

RUN_TIME = 0.5         # Seconds to spend actively running (Buck or Boost)
DEAD_TIME = 0.001       # Seconds to rest between modes (Hardware relay switch time)

# ==========================================
# 2. TARGET CONFIGURATION
# ==========================================
BUCK_HSV = 44.0 - 0.0 #- 0.0
BUCK_LSV = 26.5 + 0.5
BUCK_AMP = 20.0 - 3.0 #- 18.0 #- 14.5

BOOST_HSV = 54.0 + 0.0 #+ 0.0
BOOST_LSV = 20.0 - 1.5
BOOST_AMP = 12.5 + 55.0 #- 5.0 #- 1.25

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
    os.system('echo 0 > /sys/class/gpio/PAC.06/value') 

def sleep_gpio():
    os.system('echo 1 > /sys/class/gpio/PAC.06/value') 

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
# 5. MAIN SEQUENCE (STATE MACHINE)
# ==========================================
setup_gpio()
time.sleep(1.0)
bus.send(can.Message(arbitration_id=0x261, data=db.encode_message('LimitMsg', {'LIM_HS_OVP': 56.0, 'LIM_LS_OVP': 28.0, 'LIM_HS_UVP': 36.0, 'LIM_LS_UVP': 18.0}), is_extended_id=False))
send_command(False, 0, 48.0, 24.0, 0.0) # Clear faults
time.sleep(0.5)

# State Machine Definitions
S_BUCK = 0
S_DEAD_1 = 1
S_BOOST = 2
S_DEAD_2 = 3

current_state = S_BUCK
last_state_change = time.time()
seq_tag = "BUCK"

print(f"\n---> Starting Pulse Sequence | CAN: {CAN_HZ}Hz | DeadTime: {DEAD_TIME}s")

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

            # --- A. STATE MACHINE (NO SLEEP BLOCKS!) ---
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
                else: # Dead states
                    # Command run=False but maintain nominal target voltages to prevent shock
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
                    # New Print Format with Mode and Tag
                    print(f"[{timestamp_str}] [{seq_tag:9} | Mode:{current_mode}] HS_V:{telem['HS_V']:05.2f}V | LS_V:{telem['LS_V']:05.2f}V | HS_A:{telem['HS_A']:05.2f}A | LS_A:{telem['LS_A']:05.2f}A")
                last_print_time = now

    except KeyboardInterrupt:
        print("\nSequence interrupted.")
    finally:
        send_command(False, 0, 48.0, 24.0, 0)
        time.sleep(0.2)
        sleep_gpio()
        bus.shutdown()