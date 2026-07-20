import cantools
import can
import os
import time

class CalexDCDC:
    def __init__(self, bus, dbc_path, settings):
        self.bus = bus
        self.db = cantools.database.load_file(dbc_path)
        self.cfg = settings
        
        self.telem = {"HS_V": 0, "LS_V": 0, "HS_A": 0, "LS_A": 0}
        self.mode = 0
        self.faults = "None"
        
        # State Machine Constants
        self.S_BUCK = 0
        self.S_DEAD_1 = 1
        self.S_BOOST = 2
        self.S_DEAD_2 = 3
        
        self.state = self.S_BUCK
        self.seq_tag = "INIT"
        self.last_state_change = time.time()
        self.last_can_time = time.time()
        
        # Pre-encode Limit Message (0x261) to save CPU cycles in the loop
        self.limit_msg = self.db.encode_message('LimitMsg', {
            'LIM_HS_OVP': self.cfg['LIM_HS_OVP'],  
            'LIM_HS_UVP': self.cfg['LIM_HS_UVP'],  
            'LIM_LS_OVP': self.cfg['LIM_LS_OVP'],  
            'LIM_LS_UVP': self.cfg['LIM_LS_UVP']   
        })

    def _setup_gpio(self):
        if not os.path.exists('/sys/class/gpio/PAC.06'):
            os.system('echo "PAC.06" > /sys/class/gpio/export 2>/dev/null')
        os.system('echo "out" > /sys/class/gpio/PAC.06/direction')
        os.system('echo 1 > /sys/class/gpio/PAC.06/value') 

        if not os.path.exists('/sys/class/gpio/PQ.06'):
            os.system('echo "PQ.06" > /sys/class/gpio/export 2>/dev/null')
        os.system('echo "out" > /sys/class/gpio/PQ.06/direction')
        os.system('echo 1 > /sys/class/gpio/PQ.06/value') 

    def sleep_hardware(self):
        os.system('echo 1 > /sys/class/gpio/PAC.06/value') 
        os.system('echo 1 > /sys/class/gpio/PQ.06/value')

    def send_command(self, run, direction, hs_v, ls_v, ls_curr):
        try:
            data = self.db.encode_message('CommandMsg', {
                'CMD_RUN': 1 if run else 0,
                'CMD_DXN': direction, 'CMD_HSV': hs_v, 'CMD_LSV': ls_v, 'CMD_LS_CURR': ls_curr
            })
            self.bus.send(can.Message(arbitration_id=0x260, data=data, is_extended_id=False), timeout=0.01)
        except Exception:
            pass

    def boot(self, init_hardware=True):
        if init_hardware:
            self._setup_gpio()
            print("\n[CALEX] 1. Waking Calex 1 (LA) (PQ.06)...")
            os.system('echo 0 > /sys/class/gpio/PQ.06/value')
            time.sleep(1.0) 

            print("[CALEX] 2. Waking Calex 2 (LTO) (PAC.06)...")
            os.system('echo 0 > /sys/class/gpio/PAC.06/value')
            time.sleep(3.0) 

        print("[CALEX] 3. Sending safety limits...")
        try:
            self.bus.send(can.Message(arbitration_id=0x261, data=self.limit_msg, is_extended_id=False), timeout=0.1)
        except Exception: pass
        self.send_command(False, 0, 48.0, 24.0, 0.0) 
        time.sleep(0.5)

        if self.cfg['BMS_WAKE_TIME'] > 0:
            print(f"[CALEX] 4. Triggering JKBMS Wake-Up ({self.cfg['BMS_WAKE_LSV']}V)...")
            start = time.time()
            while time.time() - start < self.cfg['BMS_WAKE_TIME']:
                self.send_command(True, 0, self.cfg['BUCK_HSV'], self.cfg['BMS_WAKE_LSV'], self.cfg['BMS_WAKE_AMP'])
                time.sleep(0.1)

        print("[CALEX] Boot complete.")

    def parse(self, msg):
        """Called by main loop when a CAN frame matches Calex IDs"""
        if msg.arbitration_id == 0x268:
            data = self.db.decode_message(msg.arbitration_id, msg.data)
            self.telem["HS_V"] = data.get('HS_VOLT_MEAS', 0)
            self.telem["LS_V"] = data.get('LS_VOLT_MEAS', 0)
            self.telem["HS_A"] = data.get('HS_CURR_MEAS', 0)
            self.telem["LS_A"] = data.get('LS_CURR_MEAS', 0)
        elif msg.arbitration_id == 0x269:
            data = self.db.decode_message(msg.arbitration_id, msg.data)
            self.mode = data.get('DCDC_MODE', 0)
            errs = [k.replace('DCDC_ERROR_', '') for k, v in data.items() if 'ERROR' in k and v == 1]
            self.faults = "|".join(errs) if errs else "None"

    def tick(self, now):
        """Called by main loop to manage state machine and 10Hz heartbeat"""
        # A. STATE MACHINE (Only progress if no faults)
        if self.faults != "None":
            self.last_state_change = now # Stall the timer
        else:
            # B. STATE MACHINE TRANSITIONS
            if self.state == self.S_BUCK:
                self.seq_tag = "BUCK"
                if now - self.last_state_change >= self.cfg['RUN_TIME']:
                    self.state = self.S_DEAD_1; self.last_state_change = now
            elif self.state == self.S_DEAD_1:
                self.seq_tag = "DEAD"
                if now - self.last_state_change >= self.cfg['DEAD_TIME']:
                    self.state = self.S_BOOST; self.last_state_change = now
            elif self.state == self.S_BOOST:
                self.seq_tag = "BOOST"
                if now - self.last_state_change >= self.cfg['RUN_TIME']:
                    self.state = self.S_DEAD_2; self.last_state_change = now
            elif self.state == self.S_DEAD_2:
                self.seq_tag = "DEAD"
                if now - self.last_state_change >= self.cfg['DEAD_TIME']:
                    self.state = self.S_BUCK; self.last_state_change = now

        # C. 10HZ CAN HEARTBEAT (Always runs to keep DSP alive and paced)
        if now - self.last_can_time >= (1.0 / self.cfg['CAN_HZ']):
            try:
                self.bus.send(can.Message(arbitration_id=0x261, data=self.limit_msg, is_extended_id=False))
            except Exception: pass
            
            if self.faults != "None":
                # Fault recovery hold (Must be > UVP limits to prevent immediate re-fault!)
                self.send_command(run=False, direction=0, hs_v=48.0, ls_v=24.0, ls_curr=0.0)
            elif self.state == self.S_BUCK:
                self.send_command(True, 0, self.cfg['BUCK_HSV'], self.cfg['BUCK_LSV'], self.cfg['BUCK_AMP'])
            elif self.state == self.S_BOOST:
                self.send_command(True, 1, self.cfg['BOOST_HSV'], self.cfg['BOOST_LSV'], self.cfg['BOOST_AMP'])
            else: 
                # Dead-Time safe hold (Must be > UVP limits!)
                self.send_command(False, 0, 48.0, 24.0, 0.0)
            
            self.last_can_time = now