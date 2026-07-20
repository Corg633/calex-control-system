import serial
import time

# Define the serial port based on your dmesg output
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200  # Modern JK firmware defaults to 115200 for Modbus

try:
    print(f"Opening {SERIAL_PORT} at {BAUD_RATE} baud...")
    ser = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUD_RATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2 # Wait up to 2 seconds for a response
    )
    
    # Standard Modbus RTU Command to Read Holding Registers
    # This example frame requests general battery information
    # Structure: [Device ID (0x01), Function (0x03), Address High, Address Low, Count High, Count Low, CRC Low, CRC High]
    modbus_request = bytearray([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A, 0xC5, 0xCD])
    
    print(f"Sending Modbus Request: {modbus_request.hex().upper()}")
    ser.write(modbus_request)
    
    # Small pause to allow the BMS to compute and send data back
    time.sleep(0.1)
    
    # Read whatever bytes the BMS returns
    if ser.in_waiting > 0:
        response = ser.read(ser.in_waiting)
        print(f"Success! Received Raw Hex Data: {response.hex().upper()}")
    else:
        print("No response from BMS. Double-check your app settings or cross RX/TX lines.")
        
    ser.close()

except Exception as e:
    print(f"Error communicating with serial port: {e}")
