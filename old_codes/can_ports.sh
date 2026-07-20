# Safely get driver name
DRIVER=$(ethtool -i "$iface" 2>/dev/null | grep driver | awk '{print $2}')

if [ -z "$DRIVER" ]; then
    echo "  -> Driver: [None Detected/Virtual]"
else
    echo "  -> Driver: $DRIVER"
fi

# Identify hardware based on driver
if [[ "$DRIVER" == "pcan_usb" ]]; then
    echo "  -> Note: This is the PEAK USB Adapter."
elif [[ "$DRIVER" == "mttcan" ]] || [[ "$DRIVER" == "sja1000" ]] || [[ "$DRIVER" == "flexcan" ]]; then
    echo "  -> Note: This is likely the AAEON Embedded DB9 Port!"
else
    echo "  -> Note: Unknown driver or Virtual CAN."
fi

# Safely check status
if [ -n "$iface" ]; then
    STATUS=$(ip -details link show "$iface" 2>/dev/null | grep -o "UP\|DOWN" | head -1)
    if [ -z "$STATUS" ]; then
        echo "  -> Status: DOWN or Unknown"
    else
        echo "  -> Status: $STATUS"
    fi
fi
echo "-----------------------------------------"