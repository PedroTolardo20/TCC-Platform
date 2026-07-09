#!/usr/bin/env python3
"""
Read-only DYNAMIXEL discovery for the RAV manipulator.

This script sends only Protocol 2.0 PING and READ instructions.
It never writes registers, never enables torque, and never commands movement.

Usage:
  python3 dxl_read_only_scan.py \
    --device /dev/serial/by-id/usb-CM-900_ROBOTIS_Virtual_COM_Port-if00 \
    --baud 57600 \
    --start-id 1 --end-id 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler
except ImportError as exc:
    raise SystemExit(
        "dynamixel_sdk is not installed.\n"
        "Install it with:\n"
        "  sudo apt update\n"
        "  sudo apt install ros-humble-dynamixel-sdk\n"
    ) from exc


PROTOCOL_VERSION = 2.0

# XM540, Protocol 2.0 control-table addresses.
ADDR_TORQUE_ENABLE = 64
ADDR_PRESENT_POSITION = 132
ADDR_PRESENT_VOLTAGE = 144
ADDR_PRESENT_TEMPERATURE = 146


def read_1byte(port_handler, packet_handler, dxl_id, address):
    value, comm_result, dxl_error = packet_handler.read1ByteTxRx(
        port_handler, dxl_id, address
    )
    if comm_result != COMM_SUCCESS or dxl_error != 0:
        return None
    return value


def read_2byte(port_handler, packet_handler, dxl_id, address):
    value, comm_result, dxl_error = packet_handler.read2ByteTxRx(
        port_handler, dxl_id, address
    )
    if comm_result != COMM_SUCCESS or dxl_error != 0:
        return None
    return value


def read_4byte(port_handler, packet_handler, dxl_id, address):
    value, comm_result, dxl_error = packet_handler.read4ByteTxRx(
        port_handler, dxl_id, address
    )
    if comm_result != COMM_SUCCESS or dxl_error != 0:
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Protocol 2.0 scan for DYNAMIXELs on the RAV bus."
    )
    parser.add_argument(
        "--device",
        default="/dev/serial/by-id/usb-CM-900_ROBOTIS_Virtual_COM_Port-if00",
        help="Linux serial device exposed by the OpenCM.",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=57600,
        help="USB serial baud rate used by the current OpenCM bridge firmware.",
    )
    parser.add_argument("--start-id", type=int, default=1)
    parser.add_argument("--end-id", type=int, default=20)
    args = parser.parse_args()

    if not (0 <= args.start_id <= 252 and 0 <= args.end_id <= 252):
        parser.error("IDs must be between 0 and 252.")
    if args.start_id > args.end_id:
        parser.error("--start-id cannot exceed --end-id.")

    device = Path(args.device)
    if not device.exists():
        print(f"ERROR: serial device does not exist: {device}", file=sys.stderr)
        return 1

    port_handler = PortHandler(str(device))
    packet_handler = PacketHandler(PROTOCOL_VERSION)

    print("=== RAV / OpenCM / DYNAMIXEL READ-ONLY SCAN ===")
    print(f"device:   {device}")
    print(f"baud:     {args.baud}")
    print(f"protocol: {PROTOCOL_VERSION}")
    print(f"IDs:      {args.start_id}..{args.end_id}")
    print("Writes:   none")
    print()

    if not port_handler.openPort():
        print(
            "ERROR: could not open serial device. "
            "Check the USB cable and whether your user belongs to group 'dialout'.",
            file=sys.stderr,
        )
        return 1

    try:
        if not port_handler.setBaudRate(args.baud):
            print(
                f"ERROR: could not set serial baud rate to {args.baud}.",
                file=sys.stderr,
            )
            return 1

        found = []

        for dxl_id in range(args.start_id, args.end_id + 1):
            model_number, comm_result, dxl_error = packet_handler.ping(
                port_handler, dxl_id
            )
            if comm_result != COMM_SUCCESS or dxl_error != 0:
                continue

            torque = read_1byte(port_handler, packet_handler, dxl_id, ADDR_TORQUE_ENABLE)
            position = read_4byte(port_handler, packet_handler, dxl_id, ADDR_PRESENT_POSITION)
            voltage_raw = read_2byte(port_handler, packet_handler, dxl_id, ADDR_PRESENT_VOLTAGE)
            temperature = read_1byte(port_handler, packet_handler, dxl_id, ADDR_PRESENT_TEMPERATURE)

            found.append(dxl_id)
            voltage_text = "n/a" if voltage_raw is None else f"{voltage_raw / 10.0:.1f} V"
            print(
                f"FOUND  id={dxl_id:3d} "
                f"model={model_number:5d} "
                f"torque={'n/a' if torque is None else torque} "
                f"position={'n/a' if position is None else position} "
                f"voltage={voltage_text} "
                f"temp={'n/a' if temperature is None else str(temperature) + ' C'}"
            )

        print()
        if found:
            print("Scan complete. Found IDs:", ", ".join(map(str, found)))
            print("No movement command was sent.")
            return 0

        print("No motor responded.")
        print(
            "Check the DYNAMIXEL baud rate configured in Wizard and whether the "
            "current OpenCM USB firmware is forwarding Protocol 2.0 packets."
        )
        return 2
    finally:
        port_handler.closePort()


if __name__ == "__main__":
    raise SystemExit(main())
