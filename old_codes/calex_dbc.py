import cantools
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CalexDBCParser:
    """Parses Calex DBC file directly from the filesystem"""
    
    def __init__(self, dbc_path: str):
        try:
            # Use load_file to read the physical .dbc on disk 
            self.db = cantools.database.load_file(dbc_path)
            logger.info(f"Loaded DBC: {dbc_path}")
        except Exception as e:
            logger.error(f"DBC Load Error: {e}")
            raise

    def pack_command(self, run: bool, direction: int, 
                    hs_voltage: float, ls_voltage: float, 
                    current_limit: float) -> bytes:
        """Packs CommandMsg (0x260) with 0.1 scaling for volts """
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
        """
        Packs LimitMsg (0x261). 
        Scales: HS_OVP(0.5), LS_OVP(0.25), HS_UVP(0.25), LS_UVP(0.25) 
        """
        signals = {
            'LIM_HS_OVP': hs_ovp,
            'LIM_LS_OVP': ls_ovp,
            'LIM_HS_UVP': hs_uvp,
            'LIM_LS_UVP': ls_uvp,
        }
        return self.db.encode_message('LimitMsg', signals)

    def decode_any(self, msg_id: int, data: bytes) -> Dict[str, Any]:
        """Decodes any message ID (616, 617, etc.) using DBC rules """
        try:
            return self.db.decode_message(msg_id, data)
        except Exception as e:
            logger.error(f"Decode Error for ID {hex(msg_id)}: {e}")
            return {}