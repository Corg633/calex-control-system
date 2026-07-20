#!/bin/bash
# -------------------------------------------------------------------------
# AAEON BOXER-8653AI Dual CAN Setup Script
# can1 = Native Embedded Tegra Controller (SocketCAN / mttcan)
# can0 = PEAK-System USB Adapter (PCAN Network Interface)
# -------------------------------------------------------------------------

# Exit immediately if a command exits with a non-zero status
set -e

echo "=== Starting CAN Interface Initialization ==="

# -------------------------------------------------------------------------
# STEP 1: Initialize CAN1 (Embedded AAEON Interface)
# -------------------------------------------------------------------------
echo "[1/2] Initializing Embedded CAN1 (mttcan)..."

# Ensure native modules are loaded
sudo modprobe can
sudo modprobe can_raw
sudo modprobe mttcan

# Bring down the link if it was dirty from a previous crash
sudo ip link set can1 down 2>/dev/null || true

# Set bitrate to 250kbps (standard for JKBMS / Inverters)
# If using CAN-FD, add: dbitrate 2000000 fd on
sudo ip link set can1 type can bitrate 500000

# Activate interface
sudo ip link set can1 up
echo " -> can1 (Embedded) is now UP."

# -------------------------------------------------------------------------
# STEP 2: Initialize CAN0 (PEAK CAN USB)
# -------------------------------------------------------------------------
echo "[2/2] Initializing PEAK-System CAN0..."

# If you installed PEAK drivers in 'netdev' mode, load the module:
if lsmod | grep -q "pcan"; then
    echo " -> PCAN Kernel driver already loaded."
else
    sudo modprobe pcan || echo " -> Warning: pcan module not found, relying on native SocketCAN fallback."
fi

# Bring down the link if it was dirty
sudo ip link set can0 down 2>/dev/null || true

# Set bitrate to 250kbps for PEAK CAN0
sudo ip link set can0 type can bitrate 500000

# Activate interface
sudo ip link set can0 up
echo " -> can0 (PEAK USB) is now UP."

# -------------------------------------------------------------------------
# STEP 3: Verification Matrix
# -------------------------------------------------------------------------
echo "----------------------------------------"
echo "=== Final Network Status ==="
ip -br link show | grep can
echo "----------------------------------------"
echo "Setup complete. You can now use candump can0 or candump can1."