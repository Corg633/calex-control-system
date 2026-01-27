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

import can
import time
import logging
from calex_dbc import CalexDBCParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Parser
parser = CalexDBCParser('CALEX_DCDC_Database_BCE-24V_V4.dbc')

def main_control_loop():
    try:
        # Fixed: interface and channel arguments to remove DeprecationWarning
        with can.interface.Bus(channel='can0', interface='socketcan') as bus:
            logger.info("Control Loop Started. Monitoring for CAN_OOR...")

            # Step 1: Send Safety Limits (ID 0x261) 
            lim_data = parser.pack_limits(hs_ovp=55.0, ls_ovp=30.0, hs_uvp=24.0, ls_uvp=10.0)
            bus.send(can.Message(arbitration_id=0x261, data=lim_data, is_extended_id=False))

            while True:
                # Step 2: Send Command (ID 0x260) 
                cmd_data = parser.pack_command(run=True, direction=0, 
                                             hs_voltage=48.0, ls_voltage=13.5, 
                                             current_limit=50)
                bus.send(can.Message(arbitration_id=0x260, data=cmd_data, is_extended_id=False))

                # Step 3: Monitor Status (ID 0x269) 
                msg = bus.recv(timeout=0.1)
                if msg and msg.arbitration_id == 0x269:
                    status = parser.decode_any(0x269, msg.data)
                    
                    # Check for Out of Range flag [cite: 4]
                    if status.get('DCDC_ERROR_6_CAN_OOR') == 1:
                        logger.warning("⚠️ CALEX REJECTED COMMAND: Out of Range")
                    
                    # Display Temperature with DBC -40 offset 
                    logger.info(f"Temp: {status.get('DCDC_TEMPERATURE')}°C | Ready: {status.get('DCDC_READY')}")

                time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("Shutdown.")
    except Exception as e:
        logger.error(f"Unexpected error in control loop: {e}")

if __name__ == "__main__":
    main_control_loop()
# %%
