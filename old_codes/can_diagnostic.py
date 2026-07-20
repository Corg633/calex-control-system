import can
import os
import time

CAN_INTERFACE = 'can0'
BITRATE = 500000

def run_diagnostics():
    print("=========================================")
    print("   CAN Bus Hardware Diagnostic Tool")
    print("=========================================")
    
    # 1. Check interface status at the OS level
    print(f"\n[1] Checking OS Interface status for {CAN_INTERFACE}...")
    os.system(f"ip -details link show {CAN_INTERFACE}")
    
    print(f"\n[2] Attempting to bind to {CAN_INTERFACE} at {BITRATE}bps...")
    try:
        # We open the bus in listen-only mode if possible, but standard socketcan works
        bus = can.interface.Bus(interface='socketcan', channel=CAN_INTERFACE, bitrate=BITRATE)
        print(" -> Successfully bound to SocketCAN.")
    except Exception as e:
        print(f" -> [ERROR] Failed to bind: {e}")
        print(" -> Note: If you installed proprietary PEAK drivers, your interface might be named 'pcan32' or 'pcan0' instead of 'can0'.")
        return

    print("\n[3] Listening for traffic (Press CTRL+C to stop)...")
    print(" -> If you see nothing here, the Calex/BMS is asleep, wiring is bad, or baud rate is mismatched.")
    
    try:
        last_print = time.time()
        while True:
            msg = bus.recv(timeout=1.0)
            if msg:
                if msg.is_error_frame:
                    print(f"[HW ERROR FRAME] {msg}")
                else:
                    print(f"[RX] ID: 0x{msg.arbitration_id:03X} | Data: {msg.data.hex()}")
            
            # Print a heartbeat every 3 seconds so we know it hasn't frozen
            if time.time() - last_print > 3.0:
                print(" -> Still listening... (Bus is silent)")
                last_print = time.time()

    except KeyboardInterrupt:
        print("\nDiagnostics stopped.")
    finally:
        bus.shutdown()

if __name__ == "__main__":
    run_diagnostics()