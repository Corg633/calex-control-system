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
            # FIX: load_file reads the file from disk. 
            # load_string was failing because it expects the text content of the file.
            self.db = cantools.database.load_file(dbc_path)
            logger.info(f"Successfully loaded DBC: {dbc_path}")
        except Exception as e:
            logger.error(f"Failed to load DBC at {dbc_path}: {e}")
            raise

    def pack_command(self, run: bool, direction: int, 
                    hs_voltage: float, ls_voltage: float, 
                    current_limit: float) -> bytes:
        """Packs CommandMsg (ID 0x260) using original DBC definitions"""
        signals = {
            'CMD_RUN': 1 if run else 0,
            'CMD_DXN': direction,
            'CMD_HSV': hs_voltage,
            'CMD_LSV': ls_voltage,
            'CMD_LS_CURR': current_limit,
        }
        # Automatically handles Big Endian packing and 0.1 scaling from the DBC
        return self.db.encode_message('CommandMsg', signals)

    def decode_any(self, msg_id: int, data: bytes) -> Dict[str, Any]:
        """Decodes any message ID (0x268, 0x269, etc.) using DBC definitions"""
        try:
            return self.db.decode_message(msg_id, data)
        except Exception as e:
            logger.error(f"Error decoding ID {hex(msg_id)}: {e}")
            return {}