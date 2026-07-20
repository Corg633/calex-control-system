import os
import time

# Force the pin Low (which you previously identified as the "Wake" state for your circuit)
gpio_id = "PAC.06"
base_path = f"/sys/class/gpio/{gpio_id}"

# Ensure it's exported and set to out
if not os.path.exists(base_path):
    os.system(f'echo {gpio_id} > /sys/class/gpio/export')
os.system(f'echo "out" > {base_path}/direction')

print(f"Forcing {gpio_id} LOW (Wake) permanently...")
os.system(f'echo 0 > {base_path}/value')

while True:
    time.sleep(1)