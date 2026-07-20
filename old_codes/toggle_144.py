import gpiod
import time

# Based on your logs, your main Jetson chip is indexed as gpiochip0
CHIP_NAME = 'gpiochip0'
LINE_OFFSET = 144

print(f"Opening {CHIP_NAME} to control Line {LINE_OFFSET}...")

# The 'with' context manager guarantees the line is safely closed even if the script crashes
with gpiod.Chip(CHIP_NAME) as chip:
    # Fetch the line object
    line = chip.get_line(LINE_OFFSET)
    
    # Request the line as an output pin under a custom label
    line.request(consumer="calex_control_144", type=gpiod.LINE_REQ_DIR_OUT)
    
    try:
        print("Loop started. Press Ctrl+C to stop.")
        while True:
            print("Pin 144 -> HIGH (3.3V)")
            line.set_value(1)
            time.sleep(2)
            
            print("Pin 144 -> LOW (0V)")
            line.set_value(0)
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nScript stopped by user.")
        
print("Hardware line cleanly closed and released.")
