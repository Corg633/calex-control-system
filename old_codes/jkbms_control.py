import can
import os
import time
from datetime import datetime

# Updated to can0
CAN_INTERFACE = 'can0'
BITRATE = 500000

def run_jkbms_logger():
    print(f"Starting JKBMS Logger on {CAN_INTERFACE} at {BITRATE}bps...")
    
    try:
        bus = can.interface.Bus(interface='socketcan', channel=CAN_INTERFACE, bitrate=BITRATE)
        
        # Pylontech/General Inverter heartbeat (0x351)
        inverter_heartbeat = can.Message(arbitration_id=0x0351, data=[0x00]*8, is_extended_id=False)
        
        last_heartbeat = 0
        while True:
            # 1. Send heartbeat only if we have time, with a safety buffer
            if time.time() - last_heartbeat > 2.0: # Reduced to 2s to clear buffer
                try:
                    bus.send(inverter_heartbeat)
                    last_heartbeat = time.time()
                except can.exceptions.CanOperationError:
                    pass # Silently drop if buffer is full
            
            # 2. Receive
            msg = bus.recv(timeout=0.1)
            if msg:
                # Filter out the 0x88 noise and 0x0004
                if msg.arbitration_id not in [0x0088, 0x0004]:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ID: 0x{msg.arbitration_id:03X} | Data: {msg.data.hex().upper()}")
                
                # Check for BMS Broadcast IDs (V2.1 Protocol)
                if 0x02F4 <= msg.arbitration_id <= 0x0303:
                    volt = (msg.data[0] | (msg.data[1] << 8)) * 0.01
                    print(f"*** BMS BROADCAST DETECTED: {volt}V ***")

    except KeyboardInterrupt:
        print("\nLogging interrupted.")
    finally:
        if 'bus' in locals():
            bus.shutdown()

if __name__ == "__main__":
    run_jkbms_logger()