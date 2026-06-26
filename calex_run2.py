import cantools
import can
import os
import time
import sys

# ==========================================
# 1. CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DBC_PATH = os.path.join(SCRIPT_DIR, 'CALEX_DCDC_Database_BCE-24V_V4.dbc')

try:
    db = cantools.database.load_file(DBC_PATH)
except Exception as e:
    print("CRITICAL ERROR: Could not load DBC file. Check filename.")
    sys.exit(1)

try:
    bus = can.interface.Bus(interface='socketcan', channel='can0')
    print("Connected to can0 successfully.")
except Exception as e:
    print(f"Failed to connect to can0: {e}")
    sys.exit(1)

# ==========================================
# 2. HARDWARE GPIO CONTROL
# ==========================================
class CalexEnable:
    """Handles the Reversed-Logic Enable Pin for the Calex via TIP31C Transistor."""
    def __init__(self, pin):
        self.pin = pin
        self.base_path = f"/sys/class/gpio/{self.pin}"
        self._setup()

    def _setup(self):
        if not os.path.exists(self.base_path):
            # Using your working export logic
            os.system(f'echo {self.pin} > /sys/class/gpio/export')
            time.sleep(0.1)
        
        # Set to Output mode
        os.system(f'echo "out" > {self.base_path}/direction')
        
        # Default to SLEEP on startup
        self.sleep()

    def wake(self):
        print(f"[GPIO] Waking Calex (Driving {self.pin} LOW to 0V -> 12V at Calex Enable)...")
        os.system(f'echo 0 > {self.base_path}/value')

    def sleep(self):
        print(f"[GPIO] Isolating Calex (Driving {self.pin} HIGH to 3.3V -> 0V at Calex Enable)...")
        os.system(f'echo 1 > {self.base_path}/value')

# ==========================================
# 3. CAN BUS COMMANDS
# ==========================================
def send_calex_limits(hs_ovp: float, ls_ovp: float, hs_uvp: float, ls_uvp: float):
    """Packs and sends the LimitMsg (0x261) to define safety bounds"""
    signals = {
        'LIM_HS_OVP': hs_ovp,
        'LIM_LS_OVP': ls_ovp,
        'LIM_HS_UVP': hs_uvp,
        'LIM_LS_UVP': ls_uvp
    }
    try:
        data = db.encode_message('LimitMsg', signals)
        msg = can.Message(arbitration_id=0x261, data=data, is_extended_id=False)
        bus.send(msg)
    except Exception as e:
        print(f"Limit Config Error: {e}")

def send_calex_command(run: bool, direction: int, hs_v: float, ls_v: float, ls_curr: float):
    """Packs and sends the CommandMsg (0x260)"""
    signals = {
        'CMD_RUN': 1 if run else 0,
        'CMD_DXN': direction, 
        'CMD_HSV': hs_v,
        'CMD_LSV': ls_v,
        'CMD_LS_CURR': ls_curr,
    }
    try:
        data = db.encode_message('CommandMsg', signals)
        msg = can.Message(arbitration_id=0x260, data=data, is_extended_id=False)
        bus.send(msg)
    except can.exceptions.CanOperationError:
        pass 

def read_telemetry_for(seconds: float):
    """Listens to the CAN bus and prints Telemetry, State, and Errors"""
    end_time = time.time() + seconds
    while time.time() < end_time:
        msg = bus.recv(0.1) 
        if not msg:
            continue
            
        if msg.arbitration_id == 0x268: # StatusMsg 1 (Voltages & Currents)
            try:
                data = db.decode_message(msg.arbitration_id, msg.data)
                print(f"[TELEM] HS_V: {data.get('HS_VOLT_MEAS', 0):.2f}V | "
                      f"LS_V: {data.get('LS_VOLT_MEAS', 0):.2f}V | "
                      f"HS_A: {data.get('HS_CURR_MEAS', 0):.2f}A | "
                      f"LS_A: {data.get('LS_CURR_MEAS', 0):.2f}A")
            except Exception:
                pass 

        elif msg.arbitration_id == 0x269: # StatusMsg 2 (States & Faults)
            try:
                data = db.decode_message(msg.arbitration_id, msg.data)
                
                # Accurately read states from the correct message
                ready = data.get('DCDC_READY', '?')
                mode = data.get('DCDC_MODE', '?')
                
                active_errors = [key for key, value in data.items() if 'ERROR' in key and value == 1]
                if active_errors:
                    print(f"!!! [CALEX FAULT] !!! -> {active_errors}")
                else:
                    # Print normal operating state if no errors exist
                    print(f"[STATE] Ready: {ready} | Mode: {mode}")
            except Exception:
                pass

# ==========================================
# 4. EXECUTION SEQUENCE
# ==========================================
calex_gpio = CalexEnable("PAC.06")

print("\n[BOOT] 1. Waking Hardware via GPIO...")
calex_gpio.wake()
time.sleep(1.0) # Give the Calex DSP a second to boot up after getting 12V

print("[BOOT] 2. Configuring Safety Limits (OVP/UVP)...")
send_calex_limits(hs_ovp=56.0, ls_ovp=28.0, hs_uvp=40.0, ls_uvp=18.0)
time.sleep(0.2)

print("[BOOT] 3. Sending Error Reset (CMD_RUN = 0)...")
send_calex_command(run=False, direction=0, hs_v=48.0, ls_v=24.0, ls_curr=0.0)
time.sleep(0.5)

# --- Main Sequence ---
print("\nStarting 1Hz Pulse Sequence. Press Ctrl+C to stop.")
try:
    while True:
        send_calex_limits(hs_ovp=56.0, ls_ovp=28.0, hs_uvp=36.0, ls_uvp=18.0)
        
# --- BUCK (48V to 24V) ---
        print("\n---> BUCK MODE (Charging) | 10A PULSE")
        send_calex_command(run=False, direction=0, hs_v=44.0, ls_v=26.5, ls_curr=0.0)
        time.sleep(0.05) 
        send_calex_command(run=True, direction=0, hs_v=44.0, ls_v=26.5, ls_curr=10.0)
        read_telemetry_for(1.0)

        # --- BOOST (24V to 48V) ---
        print("\n---> BOOST MODE (Discharging) | 10A PULSE")
        send_calex_command(run=False, direction=1, hs_v=54.0, ls_v=20.0, ls_curr=0.0)
        time.sleep(0.05)
        send_calex_command(run=True, direction=1, hs_v=54.0, ls_v=20.0, ls_curr=10.0)
        read_telemetry_for(1.0)

except KeyboardInterrupt:
    print("\nSequence interrupted by user.")
finally:
    print("Shutting down Calex output...")
    send_calex_command(run=False, direction=0, hs_v=0, ls_v=0, ls_curr=0)
    time.sleep(0.1)
    calex_gpio.sleep()
    bus.shutdown()