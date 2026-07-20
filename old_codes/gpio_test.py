# %%
import os
import time
import matplotlib.pyplot as plt

class AaeonGPIO:
    def __init__(self, gpio_id="PAC.06"):
        self.gpio_id = gpio_id
        self.export_path = "/sys/class/gpio/export"
        self.base_path = f"/sys/class/gpio/{self.gpio_id}"
        
        # Export pin to userspace
        if not os.path.exists(self.base_path):
            os.system(f'echo {self.gpio_id} > {self.export_path}')
            time.sleep(0.1)
            
        # Set to Output mode
        os.system(f'echo "out" > {self.base_path}/direction')

    def set_state(self, state: int):
        """0 = TIP31C OFF (Calex WAKE), 1 = TIP31C ON (Calex SLEEP)"""
        os.system(f'echo {state} > {self.base_path}/value')

    def read_state(self) -> int:
        """Reads the actual hardware state from the Linux kernel"""
        with open(f"{self.base_path}/value", "r") as f:
            return int(f.read().strip())

# Initialize our pin and plotting arrays
pin = AaeonGPIO("PAC.06")
time_log = []
state_log = []
start_time = time.time()

print("Starting Calex Wake-Up Sequence...")

# Phase 1: Sleep state for 2 seconds (Pin HIGH -> TIP31C ON -> Enable Grounded)
pin.set_state(1)
while time.time() - start_time < 2.0:
    time_log.append(time.time() - start_time)
    state_log.append(pin.read_state())
    time.sleep(0.1)

# Phase 2: Wake state for 4 seconds (Pin LOW -> TIP31C OFF -> Enable pulled to 12V)
print("Waking Calex (Applying 12V to Enable)...")
pin.set_state(0)
while time.time() - start_time < 6.0:
    time_log.append(time.time() - start_time)
    state_log.append(pin.read_state())
    time.sleep(0.1)

# Phase 3: Return to Sleep state
print("Putting Calex back to sleep...")
pin.set_state(1)
time_log.append(time.time() - start_time)
state_log.append(pin.read_state())

# Plot the state over time
plt.figure(figsize=(8, 4))
plt.step(time_log, state_log, where='post', color='blue', linewidth=2)
plt.title("GPIO PQ.05 Output State (Logic Inverted for Wake)")
plt.xlabel("Time (seconds)")
plt.ylabel("GPIO Logic Level")
plt.yticks([0, 1], ["0 (LOW = Calex AWAKE)", "1 (HIGH = Calex SLEEP)"])
plt.grid(True, linestyle='--', alpha=0.7)
plt.show()