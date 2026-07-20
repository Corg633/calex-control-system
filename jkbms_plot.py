import os
import csv
import glob
import math
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ==========================================
# 1. DIRECTORY CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
PLOT_DIR = os.path.join(SCRIPT_DIR, 'plots')

if not os.path.exists(PLOT_DIR):
    os.makedirs(PLOT_DIR)

# Find the most recently created JKBMS CAN CSV file
list_of_files = glob.glob(os.path.join(LOG_DIR, 'jkbms_can_log_*.csv'))
if not list_of_files:
    print("No JKBMS CAN logs found in the 'logs' directory.")
    exit(1)
    
latest_log = max(list_of_files, key=os.path.getctime)
filename_base = os.path.basename(latest_log).replace('.csv', '')
print(f"Processing Log: {latest_log}")

# ==========================================
# 2. PARSE CSV DATA
# ==========================================
time_s, pack_v, pack_a, soc = [], [], [], []
temp_max, temp_min = [], []
# Update to 25 to include index 24
cells = {i: [] for i in range(1, 25)}

start_time_obj = None

with open(latest_log, mode='r') as file:
    reader = csv.DictReader(file)
    for row in reader:
        try:
            t_obj = datetime.strptime(row["Timestamp"], '%H:%M:%S.%f')
            if start_time_obj is None: 
                start_time_obj = t_obj
            
            elapsed = (t_obj - start_time_obj).total_seconds()
            time_s.append(elapsed)
            
            pack_v.append(float(row["Pack_V"]))
            pack_a.append(float(row["Pack_A"]))
            soc.append(float(row["SOC_%"]))
            temp_max.append(float(row["Temp_Max_C"]))
            temp_min.append(float(row["Temp_Min_C"]))
            
            # Read all 24 individual cells
            for i in range(1, 25):
                # Ensure the CSV column exists; if not, treat as 0
                val = float(row.get(f"Cell_{i}", 0))
                cells[i].append(val if val > 0 else float('nan'))
                
        except (ValueError, KeyError) as e:
            continue

if not time_s:
    print("No valid data found in log.")
    exit(1)

# ==========================================
# 3. GENERATE PLOTS
# ==========================================
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), sharex=True)
fig.suptitle(f'JKBMS CAN Telemetry: {filename_base}', fontsize=16, fontweight='bold')

# --- Plot 1: Voltage and Current ---
color_v = '#1f77b4'
ax1.plot(time_s, pack_v, label='Pack Voltage (V)', color=color_v, linewidth=3)
ax1.set_ylabel('Pack Voltage (V)', color=color_v, fontweight='bold', fontsize=12)
ax1.tick_params(axis='y', labelcolor=color_v)
ax1.grid(True, linestyle='--')

ax1_a = ax1.twinx()
color_a = '#ff7f0e'
ax1_a.plot(time_s, pack_a, label='Pack Current (A)', color=color_a, linewidth=3, linestyle='-')
ax1_a.axhline(0, color='black', linewidth=1.5)
ax1_a.set_ylabel('Pack Current (A) [Negative=Charge]', color=color_a, fontweight='bold', fontsize=12)
ax1_a.tick_params(axis='y', labelcolor=color_a)

# Aggregate legends for Plot 1
lines_1, labels_1 = ax1.get_legend_handles_labels()
lines_1a, labels_1a = ax1_a.get_legend_handles_labels()
ax1.legend(lines_1 + lines_1a, labels_1 + labels_1a, loc='upper left')

# --- Plot 2: All Active Cells ---
cmap = plt.get_cmap('tab10')
active_cells = 0
# --- Update Plot 2 block in log_plot.py ---
# ... (inside the loop)
for i in range(1, 25): # Loop up to 24
    valid_data = [v for v in cells[i] if not math.isnan(v)]
    if valid_data:
        ax2.plot(time_s, cells[i], label=f'C{i}', linewidth=1.5)
        active_cells += 1

ax2.set_ylabel('Cell Voltages (mV)', fontweight='bold', fontsize=12)
ax2.grid(True, linestyle='--')

if active_cells > 0:
    # 3 columns for 24 batteries makes it much cleaner
    ax2.legend(loc='upper left', bbox_to_anchor=(1.01, 1.0), 
               fontsize='small', ncol=3, title="Cells")

# --- Plot 3: SOC and Temperature ---
color_soc = '#9467bd'
ax3.plot(time_s, soc, label='State of Charge (%)', color=color_soc, linewidth=3)
ax3.set_ylabel('SOC (%)', color=color_soc, fontweight='bold', fontsize=12)
ax3.tick_params(axis='y', labelcolor=color_soc)
ax3.set_xlabel('Elapsed Time (Seconds)', fontweight='bold', fontsize=12)
ax3.grid(True, linestyle='--')
ax3.set_ylim(-5, 105)

ax3_t = ax3.twinx()
ax3_t.plot(time_s, temp_max, label='Max Temp Sensor (°C)', color='#d62728', linewidth=2.5, linestyle='--')
ax3_t.plot(time_s, temp_min, label='Min Temp Sensor (°C)', color='#1f77b4', linewidth=2.5, linestyle='--')
ax3_t.set_ylabel('Temperature (°C)', color='#8c564b', fontweight='bold', fontsize=12)
ax3_t.tick_params(axis='y', labelcolor='#8c564b')

# Aggregate legends for Plot 3
lines_3, labels_3 = ax3.get_legend_handles_labels()
lines_3t, labels_3t = ax3_t.get_legend_handles_labels()
ax3.legend(lines_3 + lines_3t, labels_3 + labels_3t, loc='upper left')

# Use tight_layout with a rect padding to leave room for ax2's external legend
fig.tight_layout(rect=[0, 0, 0.88, 1])

# Save the plot
output_path = os.path.join(PLOT_DIR, f"{filename_base}_plot.png")
plt.savefig(output_path, dpi=200, bbox_inches='tight')
print(f"\nPlot saved successfully to: {output_path}")

plt.close(fig)