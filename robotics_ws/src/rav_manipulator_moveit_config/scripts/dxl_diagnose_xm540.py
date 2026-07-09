#!/usr/bin/env python3
"""
Read-only diagnostic for one XM540 through OpenCM9.04 + OpenCM 485 EXP.

No register is written. No torque command is sent. No motor movement is commanded.

Example:
  python3 dxl_diagnose_xm540.py --id 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler

PROTOCOL_VERSION = 2.0

# XM540-W270-R, Protocol 2.0 control table
REGISTERS = [
    ("drive_mode", 10, 1, False),
    ("operating_mode", 11, 1, False),
    ("homing_offset", 20, 4, True),
    ("max_position_limit", 48, 4, False),
    ("min_position_limit", 52, 4, False),
    ("torque_enable", 64, 1, False),
    ("hardware_error_status", 70, 1, False),
    ("goal_pwm", 100, 2, True),
    ("goal_current", 102, 2, True),
    ("goal_velocity", 104, 4, True),
    ("profile_acceleration", 108, 4, False),
    ("profile_velocity", 112, 4, False),
    ("goal_position", 116, 4, False),
    ("moving", 122, 1, False),
    ("moving_status", 123, 1, False),
    ("present_pwm", 124, 2, True),
    ("present_current", 126, 2, True),
    ("present_velocity", 128, 4, True),
    ("present_position", 132, 4, False),
    ("velocity_trajectory", 136, 4, True),
    ("position_trajectory", 140, 4, False),
    ("present_voltage_raw", 144, 2, False),
    ("present_temperature", 146, 1, False),
]


def to_signed(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def read_register(port, packet, dxl_id: int, address: int, width: int):
    if width == 1:
        return packet.read1ByteTxRx(port, dxl_id, address)
    if width == 2:
        return packet.read2ByteTxRx(port, dxl_id, address)
    if width == 4:
        return packet.read4ByteTxRx(port, dxl_id, address)
    raise ValueError(f"unsupported width: {width}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument(
        "--device",
        default="/dev/serial/by-id/usb-CM-900_ROBOTIS_Virtual_COM_Port-if00",
    )
    parser.add_argument("--baud", type=int, default=57600)
    args = parser.parse_args()

    if not 0 <= args.id <= 252:
        parser.error("--id must be in range 0..252")

    if not Path(args.device).exists():
        print(f"ERROR: device does not exist: {args.device}", file=sys.stderr)
        return 1

    port = PortHandler(args.device)
    packet = PacketHandler(PROTOCOL_VERSION)

    if not port.openPort():
        print(f"ERROR: cannot open {args.device}", file=sys.stderr)
        return 1

    try:
        if not port.setBaudRate(args.baud):
            print(f"ERROR: cannot configure baud {args.baud}", file=sys.stderr)
            return 1

        model, comm_result, dxl_error = packet.ping(port, args.id)
        if comm_result != COMM_SUCCESS:
            print(f"ERROR ping: {packet.getTxRxResult(comm_result)}", file=sys.stderr)
            return 1
        if dxl_error:
            print(f"ERROR ping: {packet.getRxPacketError(dxl_error)}", file=sys.stderr)
            return 1

        print("=== XM540 READ-ONLY DIAGNOSTIC ===")
        print(f"ID: {args.id}")
        print(f"Model: {model}")
        print(f"Device: {args.device}")
        print(f"Baud: {args.baud}")
        print("Writes: none")
        print()

        values = {}
        for name, address, width, signed in REGISTERS:
            value, comm_result, dxl_error = read_register(
                port, packet, args.id, address, width
            )
            if comm_result != COMM_SUCCESS:
                print(f"{name:24s} ERROR {packet.getTxRxResult(comm_result)}")
                continue
            if dxl_error:
                print(f"{name:24s} ERROR {packet.getRxPacketError(dxl_error)}")
                continue

            if signed:
                value = to_signed(value, width * 8)

            values[name] = value
            print(f"{name:24s} {value}")

        if "present_voltage_raw" in values:
            print(
                f"\npresent_voltage            {values['present_voltage_raw'] / 10.0:.1f} V"
            )

        print("\nInterpretation hints:")
        print("- hardware_error_status should normally be 0.")
        print("- goal_position should equal the requested target (e.g. 2048).")
        print("- min_position_limit <= goal_position <= max_position_limit.")
        print("- moving=1 means the motor is executing a profile.")
        print("- present_current/pwm indicate whether the motor is trying to apply effort.")

        return 0
    finally:
        port.closePort()


if __name__ == "__main__":
    raise SystemExit(main())
