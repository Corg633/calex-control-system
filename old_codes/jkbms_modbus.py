import logging
import time
from pymodbus.client import ModbusSerialClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

# --- CONFIGURATION ---
# Using the Tegra hardware UART port for the Aaeon Boxer
SERIAL_PORT = '/dev/ttyTHS0' 

# Set logging to ERROR so it doesn't spam the console while scanning
logging.basicConfig(level=logging.ERROR)

def parse_alarms(alarm_mask):
    """Parses the 32-bit alarm bitmask."""
    alarms = []
    if alarm_mask & (1 << 0): alarms.append("Balance Wire Resistance High")
    if alarm_mask & (1 << 1): alarms.append("MOS Over-Temperature")
    if alarm_mask & (1 << 2): alarms.append("Cell Quantity Mismatch")
    if alarm_mask & (1 << 4): alarms.append("Cell Over-Voltage Protection")
    if alarm_mask & (1 << 6): alarms.append("Charge Over-Current Protection")
    if alarm_mask & (1 << 11): alarms.append("Cell Under-Voltage Protection")
    if alarm_mask & (1 << 13): alarms.append("Discharge Over-Current Protection")
    if alarm_mask & (1 << 14): alarms.append("Discharge Short Circuit Protection")
    return alarms if alarms else ["System Normal"]

def scan_and_read():
    print(f"🔍 Starting JK-BMS Modbus Auto-Scanner on {SERIAL_PORT}...")
    
    # Common JK BMS Configurations to test
    baud_rates = [115200, 9600]
    slave_ids = [1, 0, 2, 255]
    
    found_client = None
    found_slave = None
    
    for baud in baud_rates:
        print(f"\n--- Testing Baud Rate: {baud} ---")
        client = ModbusSerialClient(
            port=SERIAL_PORT,
            baudrate=baud,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1.0  # 1 second timeout for fast scanning
        )
        
        if not client.connect():
            print(f"❌ Failed to open {SERIAL_PORT}")
            return
            
        for slave in slave_ids:
            print(f"  -> Pinging Slave ID {slave}...")
            # Ping the MOS Temperature register (0x008A) as a test
            result = client.read_holding_registers(address=0x008A, count=2, slave=slave)
            
            if not result.isError():
                print(f"✅ SUCCESS! BMS found at Baud {baud}, Slave ID {slave}")
                found_client = client
                found_slave = slave
                break
        
        if found_client:
            break
        client.close()
        
    if not found_client:
        print("\n❌ NO BMS FOUND. Please check the following:")
        print("1. SWAP your RS485 A and B wires (This causes 90% of 'No Response' errors!).")
        print("2. Ensure 'RS485' or 'Modbus' is selected as the External Port Protocol in the JK Bluetooth App.")
        print("3. Check that your Aaeon Boxer has a common Ground wire with the BMS.")
        return
        
    # ==========================================
    # PROCEED WITH FULL TELEMETRY READ
    # ==========================================
    try:
        print("\n📥 Fetching full telemetry...")
        start_register = 0x008A 
        num_registers = 30
        
        result = found_client.read_holding_registers(address=start_register, count=num_registers, slave=found_slave)
        
        if result.isError():
            print(f"❌ Failed to read full block: {result}")
            return

        decoder = BinaryPayloadDecoder.fromRegisters(
            result.registers, 
            byteorder=Endian.BIG, 
            wordorder=Endian.BIG
        )

        temp_mos = decoder.decode_16bit_int() / 10.0
        _ = decoder.decode_32bit_uint() 
        bat_voltage = decoder.decode_32bit_uint() / 1000.0
        _ = decoder.decode_32bit_uint() 
        bat_current = decoder.decode_32bit_int() / 1000.0
        temp_bat1 = decoder.decode_16bit_int() / 10.0
        temp_bat2 = decoder.decode_16bit_int() / 10.0
        alarm_mask = decoder.decode_32bit_uint()
        _ = decoder.decode_16bit_int() 
        
        soc = result.registers[14] & 0x00FF

        print("\n================ JK-BMS Live Telemetry ================")
        print(f"Voltage: {bat_voltage:.2f} V")
        print(f"Current: {bat_current:.2f} A")
        print(f"SOC    : {soc} %")
        print(f"MOS T  : {temp_mos:.1f} °C")
        print(f"Alarms : {parse_alarms(alarm_mask)}")
        print("====================================================\n")

    except Exception as e:
        print(f"💥 Runtime Exception: {e}")
    finally:
        found_client.close()

if __name__ == "__main__":
    scan_and_read()