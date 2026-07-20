# %% 
# CELL 1: Verify Jetson Orin CUDA Driver Environment
import sys
import torch

print(f"Python Runtime Version: {sys.version}")
print(f"Is CUDA Acceleration Available?: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Target GPU Core Platform: {torch.cuda.get_device_name(0)}")

# %%
# CELL 2: Test Interactive Remote Plotting
import matplotlib.pyplot as plt
import numpy as np

# Simulate a battery decay curves or thermal monitoring metrics
epochs = np.linspace(0, 1500, 100)
soh_estimation = 100 - (0.02 * epochs) + np.random.normal(0, 0.5, 100)

plt.figure(figsize=(7, 4))
plt.plot(epochs, soh_estimation, label='Estimated State of Health (SOH)', color='crimson')
plt.title("Jetson Orin Remote SOH Validation Tracker")
plt.xlabel("Training Epochs")
plt.ylabel("Capacity (%)")
plt.grid(True)
plt.legend()
plt.show() # VS Code captures this signal and embeds it directly into your host screen!