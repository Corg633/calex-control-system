import cantools
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CalexDBCParser:
    """Parses and manages Calex DBC file directly from the filesystem"""
    
    def __init__(self, dbc_path: str):
        """
        Initialize by loading the physical .dbc file path
        Args:
            dbc_path: Path to the .dbc file (e.g., 'CALEX_DCDC_Database_BCE-24V_V4.dbc')
        """
        try:
            # Use load_file instead of load_string to read from a file path
            self.db = cantools.database.load_file(dbc_path)
            logger.info(f"Successfully loaded {dbc_path}")
        except Exception as e:
            logger.error(f"Failed to load DBC at {dbc_path}: {e}")
            raise

    def pack_command(self, run: bool, direction: int, 
                    hs_voltage: float, ls_voltage: float, 
                    current_limit: float) -> bytes:
        """Uses DBC definitions to pack CommandMsg (ID 608)"""
        signals = {
            'CMD_RUN': 1 if run else 0,
            'CMD_DXN': direction,
            'CMD_HSV': hs_voltage,
            'CMD_LSV': ls_voltage,
            'CMD_LS_CURR': current_limit,
        }
        return self.db.encode_message('CommandMsg', signals)

    def pack_limits(self, hs_ovp: float, ls_ovp: float,
                   hs_uvp: float, ls_uvp: float) -> bytes:
        """Uses DBC definitions to pack LimitMsg (ID 609)"""
        signals = {
            'LIM_HS_OVP': hs_ovp,
            'LIM_LS_OVP': ls_ovp,
            'LIM_HS_UVP': hs_uvp,
            'LIM_LS_UVP': ls_uvp,
        }
        return self.db.encode_message('LimitMsg', signals)

    def decode_any(self, msg_id: int, data: bytes) -> Dict[str, Any]:
        """Automatically decodes ANY message defined in the DBC by its ID"""
        try:
            return self.db.decode_message(msg_id, data)
        except Exception as e:
            logger.error(f"Error decoding ID {hex(msg_id)}: {e}")
            return {}