import serial
import time
import os
import csv
import struct
from datetime import datetime

# ==========================================
# 1. CONFIGURATION (MODBUS MODE)
# ==========================================
RS485_PORT = '/dev/ttyTHS0' 
BAUDRATE = 115200       # Modbus standard for JKBMS
SLAVE_ADDRESS = 0x01    # Default address for JK BMS

# ==========================================
# 2. FILE SETUP
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
CSV_FILENAME = os.path.join(LOG_DIR, f"jkbms_modbus_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

def calculate_crc(data: bytes) -> bytes:
    """CRC16/MODBUS calculation."""
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 0x0001) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return struct.pack('<H', crc)

def build_modbus_read(address, start_reg, count):
    """Builds a Modbus 0x03 read request."""
    cmd = struct.pack('>BBHH', address, 0x03, start_reg, count)
    return cmd + calculate_crc(cmd)

def run_jkbms_rs485_logger():
    print(f"Starting JKBMS Modbus Logger on {RS485_PORT} at {BAUDRATE}bps...")
    
    # Request basic data: Register 0x0100 range (Example addresses based on V1.1 map)
    # Check your BMS Modbus Register map for specific addresses if these return 0.
    REQ_DATA = build_modbus_read(SLAVE_ADDRESS, 0x0100, 10) 

    try:
        ser = serial.Serial(RS485_PORT, BAUDRATE, timeout=0.5)
        
        with open(CSV_FILENAME, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Raw_Hex_Dump"])
            
            while True:
                ser.flushInput()
                ser.write(REQ_DATA)
                time.sleep(0.2)
                
                if ser.in_waiting > 0:
                    raw_data = ser.read(ser.in_waiting)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG RX] {raw_data.hex().upper()}")
                    writer.writerow([datetime.now().strftime('%H:%M:%S'), raw_data.hex().upper()])
                
                time.sleep(1.0)

    except serial.SerialException as e:
        print(f"\nSerial Port Error: {e}")
    except KeyboardInterrupt:
        print("\nLogging interrupted.")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    run_jkbms_rs485_logger()