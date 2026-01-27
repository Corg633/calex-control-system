# %%
import sys
import cantools
import matplotlib.pyplot as plt
import can

print(f"Current Python: {sys.version}")
print(f"Cantools: {cantools.__version__}")
print(f"Matplotlib: {plt.get_backend()}")
# %%


#%%
import matplotlib.pyplot as plt

# Test Data
voltages = [47.5, 48.0, 48.2, 47.9, 48.1]
plt.plot(voltages)
plt.title("Calex High Side Voltage Test")
plt.ylabel("Volts")
plt.show()

#%%
import matplotlib.pyplot as plt
from IPython import display

# Setup 3x2 Dashboard (Voltage, Current, Temp for HS and LS)
plt.ion()
fig, axs = plt.subplots(3, 2, figsize=(14, 10))
fig.suptitle('Calex Real-Time Telemetry', fontsize=16)

# Column 0: High Side | Column 1: Low Side
(ax_v_hs, ax_v_ls) = axs[0]
(ax_i_hs, ax_i_ls) = axs[1]
(ax_t_hs, ax_t_ls) = axs[2]

def update_monitor(history):
    """
    history: a dictionary containing lists of the last 50 data points
    e.g., history = {'v_hs': [], 'i_hs': [], 't_hs': [], ...}
    """
    # Plot Voltages
    ax_v_hs.set_ylabel("Volts (V)")
    ax_v_hs.plot(history['v_hs'], color='blue', label="High Side V")
    
    ax_v_ls.plot(history['v_ls'], color='cyan', label="Low Side V")

    # Plot Currents
    ax_i_hs.set_ylabel("Amps (A)")
    ax_i_hs.plot(history['i_hs'], color='green', label="High Side I")
    
    ax_i_ls.plot(history['i_ls'], color='orange', label="Low Side I")

    # Plot Temperatures
    ax_t_hs.set_ylabel("Temp (°C)")
    ax_t_hs.plot(history['t_hs'], color='red', label="HS Internal Temp")
    
    ax_t_ls.plot(history['t_ls'], color='darkred', label="LS Internal Temp")

    # Formatting
    for ax in axs.flat:
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right', fontsize='small')
    
    display.display(plt.gcf())
    display.clear_output(wait=True)
#%%

# %%
import can
import time
from calex_dbc import CalexDBCParser

# 1. Initialize the Parser with your DBC file
parser = CalexDBCParser('CALEX_DCDC_Database_BCE-24V_V4.dbc')

def main_control_loop():
    try:
        # Connect to the hardware interface
        with can.interface.Bus('can0', bustype='socketcan') as bus:
            print("Control Loop Started. Monitoring for CAN_OOR...")

            # --- STEP 1: Send Safety Limits (ID 609) ---
            # Using specs from DBC: HS OVP 58V, LS OVP 40V, etc. [cite: 2]
            lim_data = parser.pack_limits(hs_ovp=55.0, ls_ovp=30.0, hs_uvp=24.0, ls_uvp=10.0)
            bus.send(can.Message(arbitration_id=0x261, data=lim_data, is_extended_id=False))

            while True:
                # --- STEP 2: Send Command (ID 608) ---
                # Set targets: 48V High Side, 13.5V Low Side [cite: 2]
                cmd_data = parser.pack_command(run=True, direction=0, 
                                             hs_voltage=48.0, ls_voltage=13.5, 
                                             current_limit=50)
                bus.send(can.Message(arbitration_id=0x260, data=cmd_data, is_extended_id=False))

                # --- STEP 3: Safety Check (ID 617) ---
                msg = bus.recv(timeout=0.1)
                if msg and msg.arbitration_id == 0x269: # StatusMsg_2
                    status = parser.decode_any(0x269, msg.data)
                    
                    # Monitoring DCDC_ERROR_6_CAN_OOR 
                    if status.get('DCDC_ERROR_6_CAN_OOR') == 1:
                        print("⚠️ ALERT: Calex reports Out of Range Command! Check voltage targets.")
                    
                    if status.get('errors'): # If any other error flags are active
                        print(f"Hardware Flags: {status['errors']}")

                time.sleep(0.5) # Send commands at 2Hz

    except KeyboardInterrupt:
        print("Stopping Controller...")

if __name__ == "__main__":
    main_control_loop()

# %%
