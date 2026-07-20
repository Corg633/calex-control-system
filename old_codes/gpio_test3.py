import subprocess
import time

class AaeonGPIO:
    def __init__(self, line=144):
        self.line = line
        self.chip = 0

    def set_state(self, state: int):
        """
        0 = LOW (0V) -> Transistor OFF 
        1 = HIGH (3.3V) -> Transistor ON (assuming pull-up is present)
        """
        try:
            # We use subprocess to call the system binary directly.
            # This requires no additional pip installs.
            subprocess.run(['sudo', 'gpioset', str(self.chip), f'{self.line}={state}'], check=True)
            print(f"Set Line {self.line} to {state}")
        except subprocess.CalledProcessError as e:
            print(f"Error: {e}")

# --- Test Sequence ---
pin = AaeonGPIO(144)

print("Starting Calex Sequence...")

# Set to HIGH (3.3V)
pin.set_state(1) 
print("Check multimeter now: Should be 3.3V")
time.sleep(5)

# Set to LOW (0V)
pin.set_state(0)
print("Check multimeter now: Should be 0V")
time.sleep(5)

print("Done.")