import can
import time

class JKBMS:
    def __init__(self, bus, settings):
        self.bus = bus
        self.cfg = settings
        
        self.telem = {
            "Pack_V": 0.0, "Pack_A": 0.0, "SOC": 0,
            "Cell_Max_mV": 0, "Cell_Min_mV": 0,
            "Temp_Max_C": 0, "Temp_Min_C": 0
        }
        for i in range(1, 25): self.telem[f"Cell_{i}"] = 0
        
        self.last_ctrl_time = time.time()

    def parse(self, msg):
        """Called by main loop when a CAN frame matches JKBMS IDs"""
        if not msg.is_extended_id:
            # 0x02F4: Pack V, I, SOC
            if msg.arbitration_id == 0x02F4:
                self.telem["Pack_V"] = (msg.data[0] | (msg.data[1] << 8)) * 0.1
                curr_raw = msg.data[2] | (msg.data[3] << 8)
                self.telem["Pack_A"] = (curr_raw - 4000) * 0.1
                self.telem["SOC"] = msg.data[4]
            # 0x04F4: Min/Max Voltages
            elif msg.arbitration_id == 0x04F4:
                self.telem["Cell_Max_mV"] = msg.data[0] | (msg.data[1] << 8)
                self.telem["Cell_Min_mV"] = msg.data[3] | (msg.data[4] << 8)
            # 0x05F4: Temperatures
            elif msg.arbitration_id == 0x05F4:
                self.telem["Temp_Max_C"] = msg.data[0] - 50
                self.telem["Temp_Min_C"] = msg.data[2] - 50

        else:
            # Extended IDs (Cell Data Mapping)
            frame_prefix = (msg.arbitration_id >> 16) & 0xFFFF
            frame_offsets = {
                0x18E0: 1, 0x18E1: 5, 0x18E2: 9, 
                0x18E3: 13, 0x18E4: 17, 0x18E5: 21
            }
            if frame_prefix in frame_offsets:
                base_cell = frame_offsets[frame_prefix]
                for idx in range(4): 
                    if base_cell + idx <= 24 and (idx * 2 + 1) < msg.dlc:
                        self.telem[f"Cell_{base_cell + idx}"] = msg.data[idx * 2] | (msg.data[idx * 2 + 1] << 8)

    def tick(self, now):
        """Called by main loop to manage 1Hz BMS heartbeat"""
        if now - self.last_ctrl_time >= (1.0 / self.cfg['CTRL_HZ']):
            mask_code = 0x07
            chg_sw = 1 if self.cfg['ENABLE_CHARGE'] else 0
            dsg_sw = 1 if self.cfg['ENABLE_DISCHARGE'] else 0
            bal_sw = 1 if self.cfg['ENABLE_BALANCE'] else 0
            
            data = [mask_code, chg_sw, dsg_sw, bal_sw, 0x00, 0x00, 0x00, 0x00]
            try:
                self.bus.send(can.Message(arbitration_id=0x18F0F428, data=data, is_extended_id=True))
            except can.exceptions.CanOperationError:
                pass
                
            self.last_ctrl_time = now