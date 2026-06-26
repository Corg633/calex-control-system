import cantools
import can
import os
import time

# 1. Setup
dbc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CALEX_DCDC_Database_BCE-24V_V4.dbc')
db = cantools.database.load_file(dbc_path)
bus = can.interface.Bus(interface='socketcan', channel='can0')

def send_command(run, direction, hs_v, ls_v, ls_curr):
    try:
        msg = can.Message(
            arbitration_id=0x260, 
            data=db.encode_message('CommandMsg', {
                'CMD_RUN': 1 if run else 0,
                'CMD_DXN': direction, 
                'CMD_HSV': hs_v,
                'CMD_LSV': ls_v,
                'CMD_LS_CURR': ls_curr,
            }),
            is_extended_id=False
        )
        bus.send(msg, timeout=0.1)
    except Exception:
        pass

# 2. Setup GPIO
if not os.path.exists('/sys/class/gpio/PAC.06'):
    os.system('echo "PAC.06" > /sys/class/gpio/export 2>/dev/null')
os.system('echo "out" > /sys/class/gpio/PAC.06/direction')
os.system('echo 0 > /sys/class/gpio/PAC.06/value') # Wake

print("Sending Limits and initiating fault reset...")
data = db.encode_message('LimitMsg', {'LIM_HS_OVP': 56.0, 'LIM_LS_OVP': 28.0, 'LIM_HS_UVP': 36.0, 'LIM_LS_UVP': 18.0})
bus.send(can.Message(arbitration_id=0x261, data=data, is_extended_id=False))

# 3. Main Loop
print("Entering steady-state monitoring and control loop...")
try:
    while True:
        # 1. Read the bus for 100ms
        msg = bus.recv(0.1)
        fault_found = False
        
        # 2. Check for Faults in StatusMsg_2
        if msg and msg.arbitration_id == 0x269:
            data = db.decode_message(msg.arbitration_id, msg.data)
            
            # Find any active errors
            faults = [k for k, v in data.items() if 'ERROR' in k and v == 1]
            mode = data.get('DCDC_MODE', 0)
            
            if faults:
                print(f"\n!!! FAULT DETECTED: {faults} - Sending Latch Reset !!!")
                # Send CMD_RUN=0 (Reset)
                send_command(run=False, direction=0, hs_v=50.0, ls_v=24.5, ls_curr=0.0)
                fault_found = True
            else:
                print(f"Status - Mode: {mode} | No faults active.", end='\r')
        
        # 3. If no fault was found this cycle, send the Heartbeat Run command
        if not fault_found:
            # Lock Buck Mode (Direction 0), 2.0A test limit
            send_command(run=True, direction=0, hs_v=50.0, ls_v=24.5, ls_curr=2.0)
            
except KeyboardInterrupt:
    print("\nShutting down safely...")
    send_command(run=False, direction=0, hs_v=0, ls_v=0, ls_curr=0)
    bus.shutdown()