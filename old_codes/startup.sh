#!/bin/bash
# startup.sh - Setup and start Calex controller

echo "Calex DC-DC Converter Setup"
echo "==========================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root or with sudo"
    exit 1
fi

# Setup CAN interface
echo "1. Setting up CAN interface..."
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Check if can0 is up
if ip link show can0 | grep -q "state UP"; then
    echo "✓ CAN interface can0 is UP"
else
    echo "✗ CAN interface can0 is not UP"
    exit 1
fi

# Create virtual environment if needed
echo "2. Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Created virtual environment"
fi

# Activate and install requirements
source venv/bin/activate
pip install -r requirements.txt

echo "✓ Environment setup complete"
echo ""
echo "To start the controller:"
echo "1. source venv/bin/activate"
echo "2. python calex_controller.py"
echo ""
echo "Or run as systemd service:"
echo "sudo systemctl start calex-control"
