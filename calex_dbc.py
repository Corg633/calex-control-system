#!/usr/bin/env python3
"""
DBC file parser for Calex DC-DC converter
Loads and parses the DBC file for proper signal packing
"""

import cantools
import struct
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class CalexDBCParser:
    """Parses and manages Calex DBC file"""
    
    # Fixed message IDs from DBC
    MSG_IDS = {
        'COMMAND': 0x260,    # CommandMsg
        'LIMIT': 0x261,      # LimitMsg  
        'STATUS1': 0x268,    # StatusMsg_1
        'STATUS2': 0x269,    # StatusMsg_2
    }
    
    def __init__(self, dbc_content: Optional[str] = None):
        """Initialize DBC parser with provided content"""
        self.db = None
        self._load_dbc(dbc_content)
    
    def _load_dbc(self, dbc_content: Optional[str]):
        """Load DBC from string or create default"""
        if dbc_content:
            # Load from provided content
            self.db = cantools.db.load_string(dbc_content)
        else:
            # Create minimal DBC database
            self.db = cantools.db.Database()
            
            # Add nodes
            self.db.add_node(cantools.db.Node('CALEX_DCDC'))
            self.db.add_node(cantools.db.Node('CONTROL'))
            
            # Add messages
            self._create_messages()
    
    def _create_messages(self):
        """Create message definitions matching Calex DBC"""
        
        # Command Message (0x260)
        command_msg = cantools.db.Message(
            frame_id=0x260,
            name='CommandMsg',
            length=8,
            signals=[
                # CMD_RUN: bit 0
                cantools.db.Signal(
                    name='CMD_RUN',
                    start=0,
                    length=1,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=1,
                    offset=0,
                    minimum=0,
                    maximum=1,
                    unit='Flag',
                    receivers=['CALEX_DCDC']
                ),
                # CMD_DXN: bit 8
                cantools.db.Signal(
                    name='CMD_DXN', 
                    start=8,
                    length=1,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=1,
                    offset=0,
                    minimum=0,
                    maximum=1,
                    unit='Flag',
                    receivers=['CALEX_DCDC']
                ),
                # CMD_HSV: bits 23-38 (16 bits)
                cantools.db.Signal(
                    name='CMD_HSV',
                    start=23,
                    length=16,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=0.1,
                    offset=0,
                    minimum=0,
                    maximum=54,
                    unit='Volts',
                    receivers=['CALEX_DCDC']
                ),
                # CMD_LSV: bits 39-54 (16 bits)
                cantools.db.Signal(
                    name='CMD_LSV',
                    start=39,
                    length=16,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=0.1,
                    offset=0,
                    minimum=0,
                    maximum=35,
                    unit='Volts',
                    receivers=['CALEX_DCDC']
                ),
                # CMD_LS_CURR: bits 55-62 (8 bits)
                cantools.db.Signal(
                    name='CMD_LS_CURR',
                    start=55,
                    length=8,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=1,
                    offset=0,
                    minimum=0,
                    maximum=150,
                    unit='Amps',
                    receivers=['CALEX_DCDC']
                ),
            ]
        )
        
        # Limit Message (0x261)
        limit_msg = cantools.db.Message(
            frame_id=0x261,
            name='LimitMsg',
            length=8,
            signals=[
                # LIM_HS_OVP: bits 7-14 (8 bits)
                cantools.db.Signal(
                    name='LIM_HS_OVP',
                    start=7,
                    length=8,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=0.5,
                    offset=0,
                    minimum=0,
                    maximum=58,
                    unit='Volts',
                    receivers=['CALEX_DCDC']
                ),
                # LIM_LS_OVP: bits 15-22 (8 bits)
                cantools.db.Signal(
                    name='LIM_LS_OVP',
                    start=15,
                    length=8,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=0.25,
                    offset=0,
                    minimum=0,
                    maximum=40,
                    unit='Volts',
                    receivers=['CALEX_DCDC']
                ),
                # LIM_HS_UVP: bits 23-30 (8 bits)
                cantools.db.Signal(
                    name='LIM_HS_UVP',
                    start=23,
                    length=8,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=0.25,
                    offset=0,
                    minimum=0,
                    maximum=52,
                    unit='Volts',
                    receivers=['CALEX_DCDC']
                ),
                # LIM_LS_UVP: bits 31-38 (8 bits)
                cantools.db.Signal(
                    name='LIM_LS_UVP',
                    start=31,
                    length=8,
                    byte_order='big_endian',
                    is_signed=False,
                    scale=0.25,
                    offset=0,
                    minimum=0,
                    maximum=40,
                    unit='Volts',
                    receivers=['CALEX_DCDC']
                ),
            ]
        )
        
        self.db.messages.extend([command_msg, limit_msg])
    
    def pack_command(self, run: bool, direction: int, 
                    hs_voltage: float, ls_voltage: float, 
                    current_limit: float) -> bytes:
        """
        Pack command message using DBC definitions
        
        Args:
            run: 0=Stop/Reset, 1=Run
            direction: 0=Buck, 1=Boost
            hs_voltage: High side voltage (24-54V)
            ls_voltage: Low side voltage (12-35V)
            current_limit: Current limit (0-150A)
        
        Returns:
            bytes: Packed CAN message data
        """
        signals = {
            'CMD_RUN': 1 if run else 0,
            'CMD_DXN': direction,
            'CMD_HSV': hs_voltage,
            'CMD_LSV': ls_voltage,
            'CMD_LS_CURR': current_limit,
        }
        
        message = self.db.get_message_by_name('CommandMsg')
        data = message.encode(signals)
        
        return data
    
    def pack_limits(self, hs_ovp: float, ls_ovp: float,
                   hs_uvp: float, ls_uvp: float) -> bytes:
        """
        Pack limit message
        
        Args:
            hs_ovp: High side OVP (24-58V)
            ls_ovp: Low side OVP (20-40V)
            hs_uvp: High side UVP (22.5-52V)
            ls_uvp: Low side UVP (10-40V)
        
        Returns:
            bytes: Packed CAN message data
        """
        signals = {
            'LIM_HS_OVP': hs_ovp,
            'LIM_LS_OVP': ls_ovp,
            'LIM_HS_UVP': hs_uvp,
            'LIM_LS_UVP': ls_uvp,
        }
        
        message = self.db.get_message_by_name('LimitMsg')
        data = message.encode(signals)
        
        return data
    
    def decode_status(self, msg_id: int, data: bytes) -> Dict[str, Any]:
        """
        Decode status message
        
        Args:
            msg_id: CAN message ID
            data: CAN message data
        
        Returns:
            dict: Decoded signals
        """
        try:
            if msg_id == self.MSG_IDS['STATUS1']:
                # Manually parse Status1 (simplified)
                return self._decode_status1(data)
            elif msg_id == self.MSG_IDS['STATUS2']:
                # Manually parse Status2 (simplified)
                return self._decode_status2(data)
        except Exception as e:
            logger.error(f"Error decoding message {hex(msg_id)}: {e}")
        
        return {}
    
    def _decode_status1(self, data: bytes) -> Dict[str, Any]:
        """Decode StatusMsg_1 (0x268)"""
        if len(data) < 8:
            return {}
        
        # Motorola (big endian) byte order
        hs_voltage = struct.unpack('>H', data[0:2])[0] * 0.01
        ls_voltage = struct.unpack('>H', data[2:4])[0] * 0.01
        ls_current = struct.unpack('>h', data[4:6])[0] * 0.1
        hs_current = struct.unpack('>h', data[6:8])[0] * 0.1
        
        return {
            'hs_voltage': hs_voltage,
            'ls_voltage': ls_voltage,
            'ls_current': ls_current,
            'hs_current': hs_current,
        }
    
    def _decode_status2(self, data: bytes) -> Dict[str, Any]:
        """Decode StatusMsg_2 (0x269)"""
        if len(data) < 4:
            return {}
        
        # Parse mode and flags
        mode_byte = data[0]
        mode = mode_byte & 0x0F
        ready = bool(mode_byte & 0x10)
        running = bool(mode_byte & 0x20)
        
        # Temperature (byte 1, offset -40)
        temperature = data[1] - 40
        
        # Error flags (byte 2)
        error_byte = data[2]
        errors = []
        
        if error_byte & 0x01: errors.append("OTP")
        if error_byte & 0x02: errors.append("LS_OVP")
        if error_byte & 0x04: errors.append("LS_UVP")
        if error_byte & 0x08: errors.append("HS_OVP")
        if error_byte & 0x10: errors.append("HS_UVP")
        if error_byte & 0x20: errors.append("VDD_ERR")
        if error_byte & 0x40: errors.append("CAN_OOR")
        if error_byte & 0x80: errors.append("LS_OCP")
        
        if len(data) > 3:
            error_byte2 = data[3]
            if error_byte2 & 0x01: errors.append("HS_OCP")
            if error_byte2 & 0x02: errors.append("LSDSW")
            if error_byte2 & 0x04: errors.append("HSDSW")
        
        mode_names = {
            0x1: "INIT/READY",
            0x2: "BUCK",
            0x3: "BOOST",
            0x5: "ERROR"
        }
        
        return {
            'mode': mode_names.get(mode, f"UNKNOWN({mode})"),
            'ready': ready,
            'running': running,
            'temperature': temperature,
            'errors': errors,
        }
