
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

def create_dashboard():
    plt.ion()
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8))
    fig.tight_layout(pad=3.0)
    
    # Titles for our 3 metrics
    ax1.set_title("High Side Voltage (V)")
    ax2.set_title("Low Side Voltage (V)")
    ax3.set_title("Internal Temperature (°C)")
    
    return fig, [ax1, ax2, ax3]

# This is how you would update it in your loop
def update_dashboard(axes, data_history):
    for i, ax in enumerate(axes):
        ax.cla()
        ax.plot(data_history[i], color='tab:blue' if i<2 else 'tab:red')
        # Add a grid so it looks like an oscilloscope
        ax.grid(True, alpha=0.3) 
    
    display.display(plt.gcf())
    display.clear_output(wait=True)
#%%

#!/usr/bin/env python3
"""
Main Calex DC-DC Converter Controller
Handles 2 converters with ID conflict workaround
"""

import can
import time
import threading
import logging
from typing import Optional, Dict, List
from enum import Enum
import signal
import sys
from dataclasses import dataclass
from calex_dbc import CalexDBCParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Direction(Enum):
    BUCK = 0  # HS → LS
    BOOST = 1  # LS → HS

@dataclass
class CalexUnit:
    """Represents a Calex converter"""
    name: str
    enabled: bool = False
    last_command: Optional[dict] = None
    status: Dict = None
    
    def __post_init__(self):
        if self.status is None:
            self.status = {
                'ready': False,
                'running': False,
                'mode': 'UNKNOWN',
                'temperature': 0.0,
                'hs_voltage': 0.0,
                'ls_voltage': 0.0,
                'hs_current': 0.0,
                'ls_current': 0.0,
                'errors': [],
            }

class CalexController:
    """Main controller for Calex DC-DC converters"""
    
    def __init__(self, interface: str = 'can0', bitrate: int = 500000):
        """
        Initialize controller
        
        Args:
            interface: CAN interface name
            bitrate: CAN bus bitrate (500kbps for Calex)
        """
        self.interface = interface
        self.bitrate = bitrate
        
        # Initialize DBC parser
        self.dbc = CalexDBCParser()
        
        # Initialize Calex units
        self.units = {
            'calex1': CalexUnit(name="Calex #1"),
            'calex2': CalexUnit(name="Calex #2"),
        }
        
        # Control flags
        self.running = False
        self.monitor_thread = None
        
        # Initialize CAN bus
        self._init_can_bus()
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info(f"Calex Controller initialized on {interface}")
    
    def _init_can_bus(self):
        """Initialize CAN bus connection"""
        try:
            self.bus = can.interface.Bus(
                channel=self.interface,
                bustype='socketcan',
                bitrate=self.bitrate
            )
            logger.info(f"CAN bus connected: {self.interface} at {self.bitrate}bps")
        except Exception as e:
            logger.error(f"Failed to connect to CAN bus: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop_all()
        sys.exit(0)
    
    def send_command(self, run: bool, direction: Direction,
                    hs_voltage: float, ls_voltage: float,
                    current_limit: float) -> bool:
        """
        Send command to ALL Calex converters (same IDs)
        
        IMPORTANT: This controls BOTH converters simultaneously
        since they have identical CAN IDs
        """
        # Validate ranges against CAN Min/Max from DBC
        if not (12 <= ls_voltage <= 35):
            logger.error(f"LS Voltage {ls_voltage}V out of range (12-35V)")
            return False
        if not (24 <= hs_voltage <= 54):
            logger.error(f"HS Voltage {hs_voltage}V out of range (24-54V)")
            return False
        if not (0 <= current_limit <= 150):
            logger.error(f"Current {current_limit}A out of range (0-150A)")
            return False
        
        # Pack command using DBC
        data = self.dbc.pack_command(
            run=run,
            direction=direction.value,
            hs_voltage=hs_voltage,
            ls_voltage=ls_voltage,
            current_limit=current_limit
        )
        
        # Create and send CAN message
        msg = can.Message(
            arbitration_id=0x260,  # CommandMsg ID
            data=data,
            is_extended_id=False
        )
        
        try:
            self.bus.send(msg)
            
            # Store command for both units
            for unit in self.units.values():
                unit.last_command = {
                    'run': run,
                    'direction': direction,
                    'hs_voltage': hs_voltage,
                    'ls_voltage': ls_voltage,
                    'current_limit': current_limit,
                }
                if run:
                    unit.enabled = True
            
            mode = "RUN" if run else "STOP/RESET"
            dir_str = direction.name
            logger.info(f"Command sent to ALL converters: {mode}, {dir_str}, "
                       f"HSV={hs_voltage}V, LSV={ls_voltage}V, I={current_limit}A")
            return True
            
        except can.CanError as e:
            logger.error(f"CAN send error: {e}")
            return False
    
    def set_limits(self, hs_ovp: float = 56.0, ls_ovp: float = 35.0,
                  hs_uvp: float = 23.4, ls_uvp: float = 10.8) -> bool:
        """Set protection limits for ALL converters"""
        # Validate limits
        if not (24 <= hs_ovp <= 58):
            logger.error(f"HS OVP {hs_ovp}V out of range (24-58V)")
            return False
        if not (20 <= ls_ovp <= 40):
            logger.error(f"LS OVP {ls_ovp}V out of range (20-40V)")
            return False
        if not (22.5 <= hs_uvp <= 52):
            logger.error(f"HS UVP {hs_uvp}V out of range (22.5-52V)")
            return False
        if not (10 <= ls_uvp <= 40):
            logger.error(f"LS UVP {ls_uvp}V out of range (10-40V)")
            return False
        
        # Pack limits using DBC
        data = self.dbc.pack_limits(
            hs_ovp=hs_ovp,
            ls_ovp=ls_ovp,
            hs_uvp=hs_uvp,
            ls_uvp=ls_uvp
        )
        
        msg = can.Message(
            arbitration_id=0x261,  # LimitMsg ID
            data=data,
            is_extended_id=False
        )
        
        try:
            self.bus.send(msg)
            logger.info(f"Limits set for ALL converters: "
                       f"HS_OVP={hs_ovp}V, LS_OVP={ls_ovp}V, "
                       f"HS_UVP={hs_uvp}V, LS_UVP={ls_uvp}V")
            return True
        except can.CanError as e:
            logger.error(f"Error setting limits: {e}")
            return False
    
    def start_monitoring(self):
        """Start background thread for monitoring CAN messages"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("CAN monitoring started")
    
    def _monitor_loop(self):
        """Background thread to monitor CAN messages"""
        while self.running:
            try:
                # Receive message with timeout
                msg = self.bus.recv(timeout=0.1)
                
                if msg:
                    self._process_can_message(msg)
                    
            except can.CanError as e:
                logger.error(f"CAN receive error: {e}")
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                break
    
    def _process_can_message(self, msg: can.Message):
        """Process incoming CAN message"""
        # Status message 1 (0x268)
        if msg.arbitration_id == 0x268:
            status_data = self.dbc.decode_status(0x268, msg.data)
            if status_data:
                # Update all units (since we can't distinguish)
                for unit in self.units.values():
                    unit.status.update(status_data)
                
                logger.debug(f"Status1: HS={status_data.get('hs_voltage', 0):.2f}V, "
                            f"LS={status_data.get('ls_voltage', 0):.2f}V")
        
        # Status message 2 (0x269)
        elif msg.arbitration_id == 0x269:
            status_data = self.dbc.decode_status(0x269, msg.data)
            if status_data:
                # Update all units
                for unit in self.units.values():
                    unit.status.update(status_data)
                
                if status_data.get('errors'):
                    logger.warning(f"Converter errors: {status_data['errors']}")
    
    def startup_sequence(self, direction: Direction = Direction.BUCK,
                        hs_voltage: float = 48.0, ls_voltage: float = 24.0,
                        current_limit: float = 50.0) -> bool:
        """
        Complete startup sequence for ALL converters
        
        Sequence per Calex documentation:
        1. Send RUN=0 to reset errors
        2. Wait for READY status
        3. Send RUN=1 to start
        """
        logger.info("Starting Calex converter(s) startup sequence...")
        
        # Step 0: Check prerequisites
        logger.info("Step 0: Verify prerequisites:")
        logger.info("  - HS voltage > LS voltage")
        logger.info("  - ENABLE pins have 8-18V")
        logger.info("  - CAN termination correct")
        
        # Step 1: Set protection limits
        logger.info("Step 1: Setting protection limits...")
        if not self.set_limits():
            logger.error("Failed to set limits")
            return False
        
        # Step 2: Send reset command (RUN=0)
        logger.info("Step 2: Sending reset command (RUN=0)...")
        if not self.send_command(
            run=False,
            direction=direction,
            hs_voltage=hs_voltage,
            ls_voltage=ls_voltage,
            current_limit=current_limit
        ):
            logger.error("Failed to send reset command")
            return False
        
        # Wait for converter to process
        time.sleep(0.1)
        
        # Step 3: Monitor for status (converter should send if ENABLE is high)
        logger.info("Step 3: Listening for converter status...")
        
        # Listen for a few seconds
        status_received = False
        for i in range(10):
            try:
                msg = self.bus.recv(timeout=0.2)
                if msg and msg.arbitration_id in [0x268, 0x269]:
                    status_received = True
                    self._process_can_message(msg)
                    break
            except:
                pass
        
        if not status_received:
            logger.warning("No status messages received. Check ENABLE pin and connections.")
            # Continue anyway - converter might be ready
        
        # Step 4: Start converters (RUN=1)
        logger.info("Step 4: Starting converters (RUN=1)...")
        if not self.send_command(
            run=True,
            direction=direction,
            hs_voltage=hs_voltage,
            ls_voltage=ls_voltage,
            current_limit=current_limit
        ):
            logger.error("Failed to start converters")
            return False
        
        logger.info("✓ Startup sequence complete")
        logger.info("  Converters should now be running")
        logger.info("  Commands must be sent at least every 1 second")
        
        return True
    
    def periodic_update(self):
        """Send periodic keep-alive commands"""
        for unit_name, unit in self.units.items():
            if unit.enabled and unit.last_command:
                self.send_command(
                    run=True,  # Always RUN when periodic
                    direction=unit.last_command['direction'],
                    hs_voltage=unit.last_command['hs_voltage'],
                    ls_voltage=unit.last_command['ls_voltage'],
                    current_limit=unit.last_command['current_limit']
                )
                break  # Only need to send once since both get same command
    
    def print_status(self):
        """Print status of all converters"""
        print("\n" + "="*80)
        print(f"CALEX DC-DC CONVERTERS STATUS - {len(self.units)} unit(s)")
        print("="*80)
        print("NOTE: Both converters show same status due to identical CAN IDs")
        print("-"*80)
        
        for unit_name, unit in self.units.items():
            s = unit.status
            print(f"\n{unit.name}")
            print(f"  {'Enabled:':<15} {'✓' if unit.enabled else '✗'}")
            print(f"  {'Ready:':<15} {'✓' if s['ready'] else '✗'}")
            print(f"  {'Running:':<15} {'✓' if s['running'] else '✗'}")
            print(f"  {'Mode:':<15} {s['mode']}")
            print(f"  {'Temperature:':<15} {s['temperature']:.1f}°C")
            print(f"  {'HS Voltage:':<15} {s['hs_voltage']:.2f}V")
            print(f"  {'LS Voltage:':<15} {s['ls_voltage']:.2f}V")
            print(f"  {'HS Current:':<15} {s['hs_current']:.2f}A")
            print(f"  {'LS Current:':<15} {s['ls_current']:.2f}A")
            
            if s['errors']:
                print(f"  {'Errors:':<15} {', '.join(s['errors'])}")
            else:
                print(f"  {'Errors:':<15} None")
        
        print("\n" + "="*80)
    
    def stop_all(self):
        """Stop all converters and clean up"""
        logger.info("Stopping all converters...")
        
        # Send stop command
        if any(unit.enabled for unit in self.units.values()):
            self.send_command(
                run=False,
                direction=Direction.BUCK,  # Default direction
                hs_voltage=48.0,
                ls_voltage=24.0,
                current_limit=0.0
            )
        
        # Stop monitoring
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        
        # Close CAN bus
        if hasattr(self, 'bus'):
            self.bus.shutdown()
        
        logger.info("✓ All converters stopped")

def main():
    """Main function for testing"""
    
    print("="*60)
    print("Calex DC-DC Converter Controller")
    print("For BOXER-8653AI with Jetson Orin NX")
    print("="*60)
    
    try:
        # Initialize controller
        controller = CalexController(interface='can0', bitrate=500000)
        
        # Start monitoring
        controller.start_monitoring()
        
        # Run startup sequence
        print("\nStarting converters...")
        success = controller.startup_sequence(
            direction=Direction.BUCK,
            hs_voltage=48.0,
            ls_voltage=24.0,
            current_limit=30.0
        )
        
        if not success:
            print("\n✗ Startup failed. Check connections and try again.")
            controller.stop_all()
            return
        
        print("\n✓ Converters started successfully!")
        print("Press Ctrl+C to stop")
        
        # Main control loop
        loop_count = 0
        try:
            while True:
                # Send periodic commands (every 200ms)
                if loop_count % 2 == 0:  # Every 400ms
                    controller.periodic_update()
                
                # Print status every 5 seconds
                if loop_count % 25 == 0:
                    controller.print_status()
                
                time.sleep(0.2)  # 200ms cycle
                loop_count += 1
                
        except KeyboardInterrupt:
            print("\n\nStopping...")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
    
    finally:
        controller.stop_all()
        print("\n✓ Controller shutdown complete")

if __name__ == "__main__":
    main()
