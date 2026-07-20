import can
import os
import time
import csv
from datetime import datetime

# ==========================================
# 1. CONFIGURATION
# ==========================================
CAN_INTERFACE = 'can1'
BITRATE = 500000

LOG_HZ = 10.0
PRINT_HZ = 1.0 
CTRL_HZ = 1.0

BMS_ENABLE_CHARGE = True
BMS_ENABLE_DISCHARGE = True
BMS_ENABLE_BALANCE = True

# ==========================================
# 2. FILE SETUP
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
CSV_FILENAME = os.path.join(LOG_DIR, f"jkbms_can_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

# ==========================================
# 3. CONTROL FUNCTION
# ==========================================
def send_bms_control(bus):
    mask_code = 0x07
    chg_sw = 1 if BMS_ENABLE_CHARGE else 0
    dsg_sw = 1 if BMS_ENABLE_DISCHARGE else 0
    bal_sw = 1 if BMS_ENABLE_BALANCE else 0
    data = [mask_code, chg_sw, dsg_sw, bal_sw, 0x00, 0x00, 0x00, 0x00]
    
    try:
        msg = can.Message(arbitration_id=0x18F0F428, data=data, is_extended_id=True)
        bus.send(msg)
    except can.exceptions.CanOperationError:
        pass

# ==========================================
# 4. MAIN LOGGING LOOP
# ==========================================
def run_jkbms_logger():
    print(f"Starting JKBMS CAN Logger on {CAN_INTERFACE} at {BITRATE}bps...")
    print(f"Logging telemetry to: {CSV_FILENAME}")
    
    jkbms_data = {
        "Pack_V": 0.0, "Pack_A": 0.0, "SOC": 0,
        "Cell_Max_mV": 0, "Cell_Min_mV": 0,
        "Temp_Max_C": 0, "Temp_Min_C": 0,
        **{f"Cell_{i}": 0 for i in range(1, 25)}
    }

    try:
        bus = can.interface.Bus(interface='socketcan', channel=CAN_INTERFACE, bitrate=BITRATE)
        
        with open(CSV_FILENAME, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                "Timestamp", "Pack_V", "Pack_A", "SOC_%", 
                "Temp_Max_C", "Temp_Min_C", "Cell_Max_mV", "Cell_Min_mV",
                *[f"Cell_{i}" for i in range(1, 25)],
                "Chg_ON", "Dsg_ON", "Bal_ON"
            ])
            
            last_print_time = time.time()
            last_ctrl_time = time.time()
            last_log_time = time.time()
            last_msg_time = 0
            
            while True:
                now = time.time()
                
                # --- A. CONTROL STAGE ---
                if now - last_ctrl_time >= (1.0 / CTRL_HZ):
                    send_bms_control(bus)
                    last_ctrl_time = now

                # --- B. RECEIVE & PARSE ---
                msg = bus.recv(timeout=0.05)
                if msg:
                    last_msg_time = now
                    
                    if not msg.is_extended_id:
                        if msg.arbitration_id == 0x02F4:
                            jkbms_data["Pack_V"] = (msg.data[0] | (msg.data[1] << 8)) * 0.1
                            curr_raw = msg.data[2] | (msg.data[3] << 8)
                            jkbms_data["Pack_A"] = (curr_raw - 4000) * 0.1
                            jkbms_data["SOC"] = msg.data[4]

                        elif msg.arbitration_id == 0x04F4:
                            jkbms_data["Cell_Max_mV"] = msg.data[0] | (msg.data[1] << 8)
                            jkbms_data["Cell_Min_mV"] = msg.data[3] | (msg.data[4] << 8)

                        elif msg.arbitration_id == 0x05F4:
                            jkbms_data["Temp_Max_C"] = msg.data[0] - 50
                            jkbms_data["Temp_Min_C"] = msg.data[2] - 50

                    else:
                        frame_prefix = (msg.arbitration_id >> 16) & 0xFFFF
                        
                        # Corrected Map: 4 cells per frame (Protocol V2.0 Page 10)
                        # Frame 0x18E0: 1, 2, 3, 4
                        # Frame 0x18E1: 5, 6, 7, 8
                        # Frame 0x18E2: 9, 10, 11, 12
                        # Frame 0x18E3: 13, 14, 15, 16
                        # Frame 0x18E4: 17, 18, 19, 20
                        # Frame 0x18E5: 21, 22, 23, 24
                        frame_offsets = {
                            0x18E0: 1, 0x18E1: 5, 0x18E2: 9, 
                            0x18E3: 13, 0x18E4: 17, 0x18E5: 21
                        }
                        
                        if frame_prefix in frame_offsets:
                            base_cell = frame_offsets[frame_prefix]
                            # Each frame contains 4 cells (2 bytes per cell)
                            for idx in range(4): 
                                if base_cell + idx <= 24 and (idx * 2 + 1) < msg.dlc:
                                    jkbms_data[f"Cell_{base_cell + idx}"] = msg.data[idx * 2] | (msg.data[idx * 2 + 1] << 8)

                # --- C. TIME-BASED CSV WRITE ---
                if now - last_log_time >= (1.0 / LOG_HZ):
                    timestamp_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    writer.writerow([
                        timestamp_str, 
                        round(jkbms_data["Pack_V"], 2), round(jkbms_data["Pack_A"], 2), jkbms_data["SOC"], 
                        jkbms_data["Temp_Max_C"], jkbms_data["Temp_Min_C"],
                        jkbms_data["Cell_Max_mV"], jkbms_data["Cell_Min_mV"],
                        *[jkbms_data[f"Cell_{i}"] for i in range(1, 25)],
                        int(BMS_ENABLE_CHARGE), int(BMS_ENABLE_DISCHARGE), int(BMS_ENABLE_BALANCE)
                    ])
                    file.flush()
                    last_log_time = now
                    
                # --- D. ASYNCHRONOUS PRINTING ---
                if PRINT_HZ > 0 and (now - last_print_time >= (1.0 / PRINT_HZ)):
                    # Diagnostics: Showing Cell 1 and Cell 12 as requested
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] V: {jkbms_data['Pack_V']:05.2f}V | SOC: {jkbms_data['SOC']:03d}% | C1: {jkbms_data['Cell_1']}mV | C12: {jkbms_data['Cell_12']}mV")
                    last_print_time = now

    except KeyboardInterrupt:
        print("\nLogging interrupted.")
    finally:
        if 'bus' in locals():
            bus.shutdown()

if __name__ == "__main__":
    run_jkbms_logger()