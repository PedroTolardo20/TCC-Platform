#!/usr/bin/env python3
"""
Center or release one XM540 safely through the OpenCM USB bridge.

This script is intended for mechanical assembly only:
- center exactly one selected motor at 2048 ticks;
- install its horn/link in the CAD zero orientation;
- release torque when mechanical adjustment is needed.

It does NOT write Homing Offset.
It does NOT change ID, baud rate, Operating Mode or position limits.
It never touches motors other than the selected ID.

Examples:
  # Read-only status
  python3 dxl_center_one.py --id 1 --action status

  # Move only motor ID 1 to the center (2048 ticks)
  python3 dxl_center_one.py --id 1 --action center --confirm

  # Release only motor ID 1 after centering / mounting
  python3 dxl_center_one.py --id 1 --action release --confirm
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler


PROTOCOL_VERSION = 2.0

# XM540 control table (Protocol 2.0).
ADDR_OPERATING_MODE = 11
ADDR_TORQUE_ENABLE = 64
ADDR_PROFILE_ACCELERATION = 108
ADDR_PROFILE_VELOCITY = 112
ADDR_GOAL_POSITION = 116
ADDR_PRESENT_POSITION = 132
ADDR_PRESENT_VOLTAGE = 144
ADDR_PRESENT_TEMPERATURE = 146

POSITION_CONTROL_MODE = 3
TORQUE_OFF = 0
TORQUE_ON = 1

CENTER_TICK = 2048
PROFILE_ACCELERATION = 2
PROFILE_VELOCITY = 10  # approx. 2.29 rpm: intentionally slow for assembly


def checked_write_1(port, packet, dxl_id: int, address: int, value: int, label: str) -> bool:
    comm_result, dxl_error = packet.write1ByteTxRx(port, dxl_id, address, value)
    if comm_result != COMM_SUCCESS:
        print(f"ERROR {label}: {packet.getTxRxResult(comm_result)}", file=sys.stderr)
        return False
    if dxl_error != 0:
        print(f"ERROR {label}: {packet.getRxPacketError(dxl_error)}", file=sys.stderr)
        return False
    return True


def checked_write_4(port, packet, dxl_id: int, address: int, value: int, label: str) -> bool:
    comm_result, dxl_error = packet.write4ByteTxRx(port, dxl_id, address, value)
    if comm_result != COMM_SUCCESS:
        print(f"ERROR {label}: {packet.getTxRxResult(comm_result)}", file=sys.stderr)
        return False
    if dxl_error != 0:
        print(f"ERROR {label}: {packet.getRxPacketError(dxl_error)}", file=sys.stderr)
        return False
    return True


def read_1(port, packet, dxl_id: int, address: int):
    value, comm_result, dxl_error = packet.read1ByteTxRx(port, dxl_id, address)
    if comm_result != COMM_SUCCESS or dxl_error != 0:
        return None
    return value


def read_2(port, packet, dxl_id: int, address: int):
    value, comm_result, dxl_error = packet.read2ByteTxRx(port, dxl_id, address)
    if comm_result != COMM_SUCCESS or dxl_error != 0:
        return None
    return value


def read_4(port, packet, dxl_id: int, address: int):
    value, comm_result, dxl_error = packet.read4ByteTxRx(port, dxl_id, address)
    if comm_result != COMM_SUCCESS or dxl_error != 0:
        return None
    return value


def print_status(port, packet, dxl_id: int) -> bool:
    model, comm_result, dxl_error = packet.ping(port, dxl_id)
    if comm_result != COMM_SUCCESS:
        print(f"ERROR ping ID {dxl_id}: {packet.getTxRxResult(comm_result)}", file=sys.stderr)
        return False
    if dxl_error != 0:
        print(f"ERROR ping ID {dxl_id}: {packet.getRxPacketError(dxl_error)}", file=sys.stderr)
        return False

    mode = read_1(port, packet, dxl_id, ADDR_OPERATING_MODE)
    torque = read_1(port, packet, dxl_id, ADDR_TORQUE_ENABLE)
    position = read_4(port, packet, dxl_id, ADDR_PRESENT_POSITION)
    voltage_raw = read_2(port, packet, dxl_id, ADDR_PRESENT_VOLTAGE)
    temperature = read_1(port, packet, dxl_id, ADDR_PRESENT_TEMPERATURE)

    voltage = "n/a" if voltage_raw is None else f"{voltage_raw / 10.0:.1f} V"
    print(f"ID {dxl_id} reachable")
    print(f"  model:            {model}")
    print(f"  operating_mode:   {mode}")
    print(f"  torque_enable:    {torque}")
    print(f"  present_position: {position} ticks")
    print(f"  present_voltage:  {voltage}")
    print(f"  temperature:      {'n/a' if temperature is None else str(temperature) + ' C'}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--device",
        default="/dev/serial/by-id/usb-CM-900_ROBOTIS_Virtual_COM_Port-if00",
        help="OpenCM USB serial device.",
    )
    parser.add_argument("--baud", type=int, default=57600)
    parser.add_argument("--id", type=int, required=True, dest="dxl_id")
    parser.add_argument(
        "--action",
        choices=("status", "center", "release"),
        required=True,
        help="status is read-only; center/release write only to the selected ID.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for center and release because they write to the motor.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=35.0,
        help="Maximum wait in seconds after the center command.",
    )
    args = parser.parse_args()

    if not 0 <= args.dxl_id <= 252:
        parser.error("--id must be between 0 and 252.")

    if args.action != "status" and not args.confirm:
        parser.error("--confirm is required for center or release.")

    if not Path(args.device).exists():
        print(f"ERROR: serial device does not exist: {args.device}", file=sys.stderr)
        return 1

    port = PortHandler(args.device)
    packet = PacketHandler(PROTOCOL_VERSION)

    if not port.openPort():
        print(f"ERROR: could not open {args.device}", file=sys.stderr)
        return 1

    try:
        if not port.setBaudRate(args.baud):
            print(f"ERROR: could not set {args.baud} baud.", file=sys.stderr)
            return 1

        print("=== XM540 ASSEMBLY CALIBRATION ===")
        print(f"device={args.device}")
        print(f"ID={args.dxl_id} | action={args.action} | baud={args.baud}")
        print()

        if not print_status(port, packet, args.dxl_id):
            return 1

        if args.action == "status":
            print("\nRead-only status complete. No register was changed.")
            return 0

        if args.action == "release":
            if not checked_write_1(
                port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_OFF, "Torque OFF"
            ):
                return 1
            print("\nTorque OFF. The motor shaft is now free; support any mounted link.")
            return 0

        mode = read_1(port, packet, args.dxl_id, ADDR_OPERATING_MODE)
        if mode != POSITION_CONTROL_MODE:
            print(
                f"\nABORTED: ID {args.dxl_id} is in Operating Mode {mode}; "
                f"expected Position Control Mode {POSITION_CONTROL_MODE}.",
                file=sys.stderr,
            )
            print(
                "Change Operating Mode in DYNAMIXEL Wizard first; this script will not change it.",
                file=sys.stderr,
            )
            return 1

        before = read_4(port, packet, args.dxl_id, ADDR_PRESENT_POSITION)
        print(f"\nCenter command: {before} -> {CENTER_TICK} ticks")
        print("Only the selected motor will move. Keep its assembly clear.")

        # Write a known target with torque off, then enable torque.
        if not checked_write_1(
            port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_OFF, "Torque OFF"
        ):
            return 1
        if not checked_write_4(
            port,
            packet,
            args.dxl_id,
            ADDR_PROFILE_ACCELERATION,
            PROFILE_ACCELERATION,
            "Profile Acceleration",
        ):
            return 1
        if not checked_write_4(
            port,
            packet,
            args.dxl_id,
            ADDR_PROFILE_VELOCITY,
            PROFILE_VELOCITY,
            "Profile Velocity",
        ):
            return 1
        if not checked_write_4(
            port, packet, args.dxl_id, ADDR_GOAL_POSITION, CENTER_TICK, "Goal Position"
        ):
            return 1
        if not checked_write_1(
            port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ON, "Torque ON"
        ):
            return 1

        deadline = time.monotonic() + args.timeout
        last_position = None
        while time.monotonic() < deadline:
            position = read_4(port, packet, args.dxl_id, ADDR_PRESENT_POSITION)
            if position is None:
                print("ERROR: lost position feedback during centering.", file=sys.stderr)
                return 1

            error = int(position) - CENTER_TICK
            if position != last_position:
                print(f"  present={position:4d} ticks | error={error:+d}")
                last_position = position

            if abs(error) <= 5:
                print(
                    "\nCENTER REACHED. Keep torque ON while you align the horn/link."
                )
                print(
                    "After the mechanical alignment, run the same command with "
                    "--action release --confirm before tightening or adjusting anything."
                )
                return 0

            time.sleep(0.25)

        print(
            f"\nWARNING: timeout waiting for center. Last position={last_position}. "
            "Torque remains ON; inspect the motor and mechanical clearance.",
            file=sys.stderr,
        )
        return 2

    finally:
        port.closePort()


if __name__ == "__main__":
    raise SystemExit(main())
