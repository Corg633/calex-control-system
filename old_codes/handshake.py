import can
import time

# Direct bus access
bus = can.interface.Bus(interface='socketcan', channel='can0')

def send_msg(id, data):
    msg = can.Message(arbitration_id=id, data=data, is_extended_id=False)
    try:
        bus.send(msg)
        print(f"Sent {hex(id)}: {data.hex()}")
    except Exception as e:
        print(f"Send Error: {e}")

# 1. Send Limits (0x261)
# Default values from your DBC/Manual
# We'll use safe, mid-range values.
print("Step 1: Sending LimitMsg (0x261)...")
send_msg(0x261, bytes.fromhex("0070007000700070")) 
time.sleep(0.5)

# 2. Send Command (0x260) - Run=1 (Bit 0 of byte 0 = 0x80)
# Byte 0 is CMD_RUN and CMD_DXN
print("Step 2: Sending CommandMsg (0x260) - RUN=1...")
send_msg(0x260, bytes.fromhex("8000000000000000"))

print("Observation: Watch your 'candump' window.")
print("If the Calex Mode (Byte 0 of 0x269) changes from 0x11, you have succeeded.")