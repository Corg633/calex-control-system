import cantools
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CalexDBCParser:
    def __init__(self, dbc_path: str):
        """Load the ACTUAL file from the path provided"""
        try:
            # We MUST use load_file for a path string
            self.db = cantools.database.load_file(dbc_path)
            logger.info(f"Loaded DBC: {dbc_path}")
        except Exception as e:
            logger.error(f"DBC Load Error: {e}")
            raise

    def pack_command(self, run, direction, hs_v, ls_v, curr_lim) -> bytes:
        signals = {
            'CMD_RUN': 1 if run else 0,
            'CMD_DXN': direction,
            'CMD_HSV': hs_v,
            'CMD_LSV': ls_v,
            'CMD_LS_CURR': curr_lim
        }
        return self.db.encode_message('CommandMsg', signals)

    def decode_any(self, msg_id: int, data: bytes) -> Dict[str, Any]:
        return self.db.decode_message(msg_id, data)