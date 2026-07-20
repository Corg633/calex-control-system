# %%
import os
import time

gpio_id = "PAC.06"
base_path = f"/sys/class/gpio/{gpio_id}"

# Safety Check: If the system rebooted, make sure the directory exists
if not os.path.exists(base_path):
    os.system(f'echo {gpio_id} > /sys/class/gpio/export')
    time.sleep(0.1)

# Set to Output mode
os.system(f'echo "out" > {base_path}/direction')

print("Starting infinite 2-second cycle loop. Press Ctrl+C to stop...")

try:
    while True:
        # 1. Force High (Actively drives 3.3V)
        print(f"Setting {gpio_id} to HIGH (1)...")
        os.system(f'echo 1 > {base_path}/value')
        time.sleep(1.0)  # Hold for 1 second

        # 2. Force Low (Actively drives 0V / GND)
        print(f"Setting {gpio_id} to LOW (0)...")
        os.system(f'echo 0 > {base_path}/value')
        time.sleep(1.0)  # Hold for 1 second

except KeyboardInterrupt:
    print("\nLoop stopped cleanly by user.")
    
    # Force the hardware pin to HIGH on exit
    print(f"Safely forcing {gpio_id} to HIGH (1) state...")
    os.system(f'echo 1 > {base_path}/value')
