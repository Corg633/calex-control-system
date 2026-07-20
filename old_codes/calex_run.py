import os
import sys
import time
import cantools
import can

# Import your custom parser from your calex_dbc.py file
from calex_dbc import CalexDBCParser

# ==========================================
# CONFIGURATION
# ==========================================
DBC_FILE = "calex_dbc.py"  # Ensure this matches your actual dbc filename
CAN_CHANNEL = "can0"
BITRATE = 500000
GPIO_PIN = "PAC.06"

# Hardware Limits
HV_SETPOINT = 48.0
LV_SETPOINT = 26.0      # Slightly above 24V to push charge into Lead Acid
CURRENT_LIMIT = 10.0    # 10A on the Low Voltage side (approx 5A on the HV side)

# Calex Direction Mapping (Verify with your specific datasheet if needed)
DIR_BUCK = 0   # Buck: 48V -> 24V (Charging the Lead Acid)
DIR_BOOST = 1  # Boost: 24V -> 48V (Discharging Lead Acid into Resistor Bank)
# ==========================================

class CalexEnable:
    """Handles the Reversed-Logic Enable Pin for the Calex."""
    def __init__(self, pin):
        self.pin = pin
        self.base_path = f"/sys/class/gpio/{self.pin}"
        self._setup()

    def _setup(self):
        if not os.path.exists(self.base_path):
            os.system(f'echo {self.pin} > /sys/class/gpio/export')
            time.sleep(0.1)
        
        # Set to Output mode
        os.system(f'echo "out" > {self.base_path}/direction')
        
        # Default to IDLE (HIGH / 1) on startup
        self.sleep()

    def wake(self):
        print(f"[GPIO] Waking Calex (Driving {self.pin} LOW to 0V)...")
        os.system(f'echo 0 > {self.base_path}/value')

    def sleep(self):
        print(f"[GPIO] Isolating Calex (Driving {self.pin} HIGH to 3.3V)...")
        os.system(f'echo 1 > {self.base_path}/value')


def main():
    if not os.path.exists(DBC_FILE):
        print(f"Error: DBC file not found at {DBC_FILE}")
        return

    # 1. Initialize CAN and DBC
    parser = CalexDBCParser(DBC_FILE)
    bus = can.Bus(interface='socketcan', channel=CAN_CHANNEL, bitrate=BITRATE)
    print("CAN Bus initialized successfully.")

    # 2. Initialize GPIO (Defaults to Sleep/HIGH)
    calex_gpio = CalexEnable(GPIO_PIN)

    # 3. Transmit Hardware Limits before Waking
    print("Transmitting Boundary Limits...")
    limits_msg = parser.pack_limits(
        hs_ovp=52.0, ls_ovp=30.0, 
        hs_uvp=40.0, ls_uvp=20.0
    )
    bus.send(can.Message(arbitration_id=0x261, data=limits_msg, is_extended_id=False))
    time.sleep(0.1)

    # 4. Wake the Calex Hardware
    calex_gpio.wake()
    time.sleep(0.5) # Allow internal capacitors/DSPs to boot

    # 5. Initialize the Toggle Loop
    current_direction = DIR_BUCK
    last_toggle_time = time.time()
    start_time = time.time()
    
    print("\n--- Starting 1-Second Cyclic Charge/Discharge Test ---")
    print("Press Ctrl+C to emergency stop and isolate hardware.\n")

    try:
        while True:
            now = time.time()
            
            # --- THE 1-SECOND TOGGLE LOGIC ---
            if now - last_toggle_time >= 1.0:
                last_toggle_time = now
                
                # Flip the direction
                current_direction = DIR_BOOST if current_direction == DIR_BUCK else DIR_BUCK
                
                # Construct the command
                cmd_msg = parser.pack_command(
                    run=True,
                    direction=current_direction,
                    hs_voltage=HV_SETPOINT,
                    ls_voltage=LV_SETPOINT,
                    current_limit=CURRENT_LIMIT
                )
                
                # Transmit over CAN
                bus.send(can.Message(arbitration_id=0x260, data=cmd_msg, is_extended_id=False))
                
                # Print Status
                dir_str = "BUCK (48V->24V | CHARGING)" if current_direction == DIR_BUCK else "BOOST (24V->48V | DISCHARGING)"
                print(f"[{now - start_time:.1f}s] Switched to {dir_str} at {CURRENT_LIMIT}A")

            # --- NON-BLOCKING TELEMETRY READ ---
            # Wait a tiny fraction of a second for messages to keep the buffer empty
            msg = bus.recv(timeout=0.01)
            if msg:
                # Assuming Telemetry is broadcast on 0x262 (adjust to your DBC)
                if msg.arbitration_id == 0x262:
                    try:
                        data = parser.db.decode_message(msg.arbitration_id, msg.data)
                        # Print realtime current reading on the same line
                        lv_current = data.get('TELEM_LS_CURR', 0.0)
                        sys.stdout.write(f"\rReal-Time LV Current: {lv_current:.1f} A   ")
                        sys.stdout.flush()
                    except Exception:
                        pass # Ignore messages we can't parse

    except KeyboardInterrupt:
        print("\n\nUser Interrupted (Ctrl+C). Initiating Safe Shutdown...")
        
        # 1. Send 0 Amps / RUN=False over CAN immediately
        try:
            stop_msg = parser.pack_command(
                run=False, direction=DIR_BUCK, 
                hs_voltage=HV_SETPOINT, ls_voltage=LV_SETPOINT, 
                current_limit=0.0
            )
            bus.send(can.Message(arbitration_id=0x260, data=stop_msg, is_extended_id=False))
            print("CAN Command: 0 Amps / RUN=False broadcasted.")
        except Exception as e:
            print(f"Failed to send CAN stop command: {e}")

        # 2. Hard-Kill the GPIO (Pull High)
        calex_gpio.sleep()
        
        print("Hardware safely isolated. Test Complete.")

if __name__ == "__main__":
    main()