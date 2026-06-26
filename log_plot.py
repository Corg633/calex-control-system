import os
import csv
import glob
from datetime import datetime

import matplotlib
matplotlib.use('Agg')  # <-- MUST BE BEFORE IMPORTING PYPLOT to fix Gdk-CRITICAL error!
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ==========================================
# 1. DIRECTORY CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
PLOT_DIR = os.path.join(SCRIPT_DIR, 'plots')

if not os.path.exists(PLOT_DIR):
    os.makedirs(PLOT_DIR)

# Find the most recently created CSV file
list_of_files = glob.glob(os.path.join(LOG_DIR, '*.csv'))
latest_log = max(list_of_files, key=os.path.getctime)
filename_base = os.path.basename(latest_log).replace('.csv', '')
print(f"Processing Log: {latest_log}")

# ==========================================
# 2. PARSE CSV DATA
# ==========================================
time_s, hs_v, ls_v, hs_a, ls_a, modes = [], [], [], [], [], []
start_time_obj = None

with open(latest_log, mode='r') as file:
    reader = csv.DictReader(file)
    for row in reader:
        try:
            t_obj = datetime.strptime(row["Timestamp"], '%H:%M:%S.%f')
            if start_time_obj is None: start_time_obj = t_obj
            
            delta = (t_obj - start_time_obj).total_seconds()
            if delta < 0: delta += 86400 
            
            time_s.append(delta)
            hs_v.append(float(row["HS_V"]))
            ls_v.append(float(row["LS_V"]))
            hs_a.append(float(row["HS_A"]))
            ls_a.append(float(row["LS_A"]))
            modes.append(row["Sequence"])
        except Exception:
            pass 

# ==========================================
# 3. GENERATE PLOT
# ==========================================
print("Generating figure in headless mode...")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
fig.suptitle(f'Calex Telemetry: {filename_base}', fontsize=16, fontweight='bold')

ax1.plot(time_s, hs_v, label='High-Side (48V) Voltage', color='#d62728', linewidth=2)
ax1.plot(time_s, ls_v, label='Low-Side (24V) Voltage', color='#1f77b4', linewidth=2)
ax1.set_ylabel('Voltage (V)', fontweight='bold')
ax1.grid(True, linestyle='--')
ax1.legend(loc='upper right')

ax2.plot(time_s, hs_a, label='High-Side Current', color='#ff7f0e', linewidth=2)
ax2.plot(time_s, ls_a, label='Low-Side Current', color='#2ca02c', linewidth=2)
ax2.axhline(0, color='black', linewidth=1.5) 
ax2.set_ylabel('Current (A)', fontweight='bold')
ax2.set_xlabel('Elapsed Time (Seconds)', fontweight='bold')
ax2.grid(True, linestyle='--')
ax2.legend(loc='upper right')

# --- Background Shading for Modes ---
mode_start_idx = 0
current_mode = modes[0]
for i in range(1, len(time_s)):
    if modes[i] != current_mode or i == len(time_s) - 1:
        if current_mode == 'BUCK': color = '#e5f5e0'
        elif current_mode == 'BOOST': color = '#fee0d2'
        else: color = '#ffffff' # White for dead-time
        
        ax1.axvspan(time_s[mode_start_idx], time_s[i], facecolor=color, alpha=0.5)
        ax2.axvspan(time_s[mode_start_idx], time_s[i], facecolor=color, alpha=0.5)
        current_mode = modes[i]
        mode_start_idx = i

plt.tight_layout(rect=[0, 0.03, 1, 0.96]) 
output_png = os.path.join(PLOT_DIR, f"{filename_base}_plot.png")
plt.savefig(output_png, dpi=300)
print(f"Plot successfully saved to: {output_png}")