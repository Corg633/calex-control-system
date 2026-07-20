import os
import csv
import glob
import math
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
PLOT_DIR = os.path.join(SCRIPT_DIR, 'plots')

if not os.path.exists(PLOT_DIR): os.makedirs(PLOT_DIR)

list_of_files = glob.glob(os.path.join(LOG_DIR, 'sync_log_*.csv'))
if not list_of_files:
    print("No unified logs found.")
    exit(1)
    
latest_log = max(list_of_files, key=os.path.getctime)
filename_base = os.path.basename(latest_log).replace('.csv', '')
print(f"Processing Log: {latest_log}")

time_s = []
# Calex
calex_modes, hs_v, ls_v, hs_a, ls_a = [], [], [], [], []
# JKBMS
pack_v, pack_a, soc, t_max = [], [], [], []
cells = {i: [] for i in range(1, 25)}

start_time_obj = None

with open(latest_log, mode='r') as file:
    reader = csv.DictReader(file)
    for row in reader:
        try:
            t_obj = datetime.strptime(row["Timestamp"], '%H:%M:%S.%f')
            if start_time_obj is None: start_time_obj = t_obj
            time_s.append((t_obj - start_time_obj).total_seconds())
            
            # Safe parsing incase a module was disabled during logging
            calex_modes.append(row.get("Calex_Seq", "DISABLED"))
            hs_v.append(float(row.get("HS_V", float('nan'))))
            ls_v.append(float(row.get("LS_V", float('nan'))))
            hs_a.append(float(row.get("HS_A", float('nan'))))
            ls_a.append(float(row.get("LS_A", float('nan'))))
            
            pack_v.append(float(row.get("Pack_V", float('nan'))))
            pack_a.append(float(row.get("Pack_A", float('nan'))))
            soc.append(float(row.get("SOC_%", float('nan'))))
            t_max.append(float(row.get("T_Max", float('nan'))))
            
            for i in range(1, 25):
                val = float(row.get(f"Cell_{i}", 0))
                cells[i].append(val if val > 0 else float('nan'))
        except Exception:
            continue

fig, axs = plt.subplots(4, 1, figsize=(15, 16), sharex=True)
# Add some vertical padding (y=0.98) so the title doesn't crash into the top of the plot
fig.suptitle(f'Unified System Telemetry: {filename_base}', fontsize=16, fontweight='bold', y=0.98)

# Plot 1: Voltages
axs[0].plot(time_s, hs_v, label='Calex HS (48V)', color='#d62728', linewidth=2)
axs[0].plot(time_s, ls_v, label='Calex LS (24V)', color='#1f77b4', linewidth=2)
axs[0].plot(time_s, pack_v, label='BMS Pack (Actual)', color='#2ca02c', linewidth=2, linestyle='--')
axs[0].set_ylabel('Voltage (V)', fontweight='bold')
axs[0].grid(True, linestyle='--'); axs[0].legend(loc='upper right')

# Plot 2: Currents
axs[1].plot(time_s, hs_a, label='Calex HS Current', color='#ff7f0e', linewidth=2)
axs[1].plot(time_s, ls_a, label='Calex LS Current', color='#9467bd', linewidth=2)
axs[1].plot(time_s, pack_a, label='BMS Pack Current', color='#8c564b', linewidth=2, linestyle='--')
axs[1].axhline(0, color='black', linewidth=1)
axs[1].set_ylabel('Current (A)', fontweight='bold')
axs[1].grid(True, linestyle='--'); axs[1].legend(loc='upper right')

# Plot 3: Cell Imbalances
active_cells = 0
for i in range(1, 25):
    if any(not math.isnan(v) for v in cells[i]):
        axs[2].plot(time_s, cells[i], label=f'C{i}', linewidth=1.2)
        active_cells += 1
axs[2].set_ylabel('Cell Voltages (mV)', fontweight='bold')
axs[2].grid(True, linestyle='--')
if active_cells > 0: axs[2].legend(loc='upper left', bbox_to_anchor=(1.01, 1.0), fontsize='small', ncol=3)

# Plot 4: SOC, Temps & Mode Background
axs[3].plot(time_s, soc, label='SOC %', color='#e377c2', linewidth=3)
axs[3].set_ylabel('SOC (%)', fontweight='bold')
ax3_t = axs[3].twinx()
ax3_t.plot(time_s, t_max, label='Max Temp (°C)', color='red', linestyle=':')
ax3_t.set_ylabel('Temp (°C)', fontweight='bold')
axs[3].grid(True, linestyle='--')

# Color backgrounds for Calex Active Mode tracking
current_mode = calex_modes[0]
mode_start_idx = 0
for i in range(1, len(time_s)):
    if calex_modes[i] != current_mode or i == len(time_s) - 1:
        color = '#e5f5e0' if current_mode == 'BUCK' else '#fee0d2' if current_mode == 'BOOST' else '#ffffff'
        for ax in axs: ax.axvspan(time_s[mode_start_idx], time_s[i], facecolor=color, alpha=0.3)
        current_mode = calex_modes[i]
        mode_start_idx = i

# Adjusted top margin down to 0.95 to leave physical space for the suptitle
fig.tight_layout(rect=[0, 0, 0.88, 0.97])
output_path = os.path.join(PLOT_DIR, f"{filename_base}_plot.png")
plt.savefig(output_path, dpi=200, bbox_inches='tight')
print(f"Unified plot saved successfully to: {output_path}")