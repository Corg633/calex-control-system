import cantools
import can
import os
import time
import signal
import sys

# FIX: Added missing constants
CAN_INTERFACE = 'can1' 
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DBC_FILE = os.path.join(SCRIPT_DIR, 'CALEX_DCDC_Database_BCE-24V_V4.dbc')

# Safety Limits
HS_OVP = 55.0
HS_UVP = 20.0
LS_OVP = 38.0
LS_UVP = 10.0

class CalexController:
    def __init__(self):
        # Ensure path is handled correctly if file is local
        self.db = cantools.database.load_file(DBC_FILE)
        self.bus = can.interface.Bus(interface='socketcan', channel=CAN_INTERFACE, bitrate=500000)
        self.running = True
        self.mode = 'BUCK'
        
        signal.signal(signal.SIGINT, self.stop)
        
        print("[INIT] Sending initial safety limits...")
        self.send_limits()

    def stop(self, signum=None, frame=None):
        print("\n[STOP] Shutting down converter safely...")
        self.running = False
        # Send Stop Command
        self.send_command(run=False, direction=0, hs_v=0, ls_v=0, ls_curr=0)
        time.sleep(0.5)
        self.bus.shutdown()
        sys.exit(0)

    #    def send_limits(self):
        """Sends the OVP/UVP limits to the converter."""
        data = self.db.encode_message('LimitMsg', {
            'LIM_HS_OVP': HS_OVP,
            'LIM_HS_UVP': HS_UVP,
            'LIM_LS_OVP': LS_OVP,
            'LIM_LS_UVP': LS_UVP
        })
        msg = can.Message(arbitration_id=0x261, data=data, is_extended_id=False)
        self.bus.send(msg)

    def send_command(self, run, direction, hs_v, ls_v, ls_curr):
        """
        direction: 0=BUCK, 1=BOOST
        """
        data = self.db.encode_message('CommandMsg', {
            'CMD_RUN': 1 if run else 0,
            'CMD_DXN': direction,
            'CMD_HSV': hs_v,
            'CMD_LSV': ls_v,
            'CMD_LS_CURR': ls_curr
        })
        msg = can.Message(arbitration_id=0x260, data=data, is_extended_id=False)
        self.bus.send(msg)

    #    def run_loop(self):
        print("[START] Control loop active.")
        last_heartbeat = 0
        
        while self.running:
            # 10Hz Heartbeat/Control rate
            if time.time() - last_heartbeat > 0.1:
                
                # Logic: Choose mode (Example: Toggle or based on state)
                # Ensure we don't toggle faster than 1 second to avoid hardware damage
                direction = 0 if self.mode == 'BUCK' else 1
                
                # Send Command (Run=1, Direction, HS_Volts, LS_Volts, LS_Current)
                self.send_command(
                    run=True, 
                    direction=direction, 
                    hs_v=43.0,  # Target High Side Volts
                    ls_v=34.0,  # Target Low Side Volts
                    ls_curr=20  # Current Limit (Amps)
                )
                
                last_heartbeat = time.time()
                
            time.sleep(0.01)

if __name__ == "__main__":
    ctrl = CalexController()
    ctrl.run_loop()