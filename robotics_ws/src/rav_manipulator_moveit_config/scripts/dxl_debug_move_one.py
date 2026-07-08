#!/usr/bin/env python3
import argparse
import sys
import time

from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler

PROTOCOL_VERSION = 2.0

ADDR_OPERATING_MODE = 11
ADDR_TORQUE_ENABLE = 64
ADDR_HARDWARE_ERROR_STATUS = 70
ADDR_PROFILE_ACCELERATION = 108
ADDR_PROFILE_VELOCITY = 112
ADDR_GOAL_POSITION = 116
ADDR_MOVING = 122
ADDR_PRESENT_PWM = 124
ADDR_PRESENT_CURRENT = 126
ADDR_PRESENT_VELOCITY = 128
ADDR_PRESENT_POSITION = 132

TORQUE_OFF = 0
TORQUE_ON = 1
POSITION_CONTROL_MODE = 3

DEFAULT_DEVICE = "/dev/serial/by-id/usb-CM-900_ROBOTIS_Virtual_COM_Port-if00"


def ok(packet, comm_result, dxl_error, label):
    if comm_result != COMM_SUCCESS:
        print(f"ERRO {label}: {packet.getTxRxResult(comm_result)}", file=sys.stderr)
        return False
    if dxl_error != 0:
        print(f"ERRO {label}: {packet.getRxPacketError(dxl_error)}", file=sys.stderr)
        return False
    return True


def r1(port, packet, dxl_id, addr, label):
    v, c, e = packet.read1ByteTxRx(port, dxl_id, addr)
    if not ok(packet, c, e, label):
        return None
    return v


def r2(port, packet, dxl_id, addr, label):
    v, c, e = packet.read2ByteTxRx(port, dxl_id, addr)
    if not ok(packet, c, e, label):
        return None
    return v


def r4(port, packet, dxl_id, addr, label):
    v, c, e = packet.read4ByteTxRx(port, dxl_id, addr)
    if not ok(packet, c, e, label):
        return None
    return v


def w1(port, packet, dxl_id, addr, value, label):
    c, e = packet.write1ByteTxRx(port, dxl_id, addr, value)
    return ok(packet, c, e, label)


def w4(port, packet, dxl_id, addr, value, label):
    c, e = packet.write4ByteTxRx(port, dxl_id, addr, value)
    return ok(packet, c, e, label)


def s16(v):
    return v - 65536 if v is not None and v > 32767 else v


def s32(v):
    return v - 4294967296 if v is not None and v > 2147483647 else v


parser = argparse.ArgumentParser()
parser.add_argument("--id", type=int, required=True, dest="dxl_id")
parser.add_argument("--delta", type=int, default=100)
parser.add_argument("--baud", type=int, default=1000000)
parser.add_argument("--device", default=DEFAULT_DEVICE)
parser.add_argument("--confirm", action="store_true")
args = parser.parse_args()

if not args.confirm:
    parser.error("Use --confirm.")

port = PortHandler(args.device)
packet = PacketHandler(PROTOCOL_VERSION)

if not port.openPort():
    print(f"ERRO: não abriu {args.device}", file=sys.stderr)
    sys.exit(1)

if not port.setBaudRate(args.baud):
    print(f"ERRO: não configurou baud {args.baud}", file=sys.stderr)
    port.closePort()
    sys.exit(1)

try:
    print(f"=== DEBUG MOVE XM540 | ID {args.dxl_id} | baud {args.baud} ===")

    mode = r1(port, packet, args.dxl_id, ADDR_OPERATING_MODE, "operating_mode")
    hwerr = r1(port, packet, args.dxl_id, ADDR_HARDWARE_ERROR_STATUS, "hardware_error")
    torque = r1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, "torque")
    pos0 = r4(port, packet, args.dxl_id, ADDR_PRESENT_POSITION, "present_position")
    goal0 = r4(port, packet, args.dxl_id, ADDR_GOAL_POSITION, "goal_position")

    print(f"antes: mode={mode} hwerr={hwerr} torque={torque} present={pos0} goal={goal0}")

    if mode != POSITION_CONTROL_MODE:
        print("ABORTADO: motor não está em Position Control Mode 3.")
        sys.exit(1)

    if hwerr != 0:
        print(f"ABORTADO: hardware_error_status={hwerr}")
        sys.exit(1)

    target = int(pos0) + int(args.delta)
    if target < 0 or target > 4095:
        print(f"ABORTADO: alvo fora do range: {target}")
        sys.exit(1)

    print(f"alvo: {pos0} -> {target}")

    # Ordem diferente do script anterior:
    # torque off -> configura perfil -> torque on -> escreve goal
    if not w1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_OFF, "torque off"):
        sys.exit(1)

    w4(port, packet, args.dxl_id, ADDR_PROFILE_ACCELERATION, 10, "profile acceleration")
    w4(port, packet, args.dxl_id, ADDR_PROFILE_VELOCITY, 30, "profile velocity")

    if not w1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ON, "torque on"):
        sys.exit(1)

    time.sleep(0.1)

    torque_after = r1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, "torque after on")
    print(f"torque após ligar: {torque_after}")

    if not w4(port, packet, args.dxl_id, ADDR_GOAL_POSITION, target, "goal position após torque on"):
        sys.exit(1)

    for _ in range(40):
        pos = r4(port, packet, args.dxl_id, ADDR_PRESENT_POSITION, "present_position")
        goal = r4(port, packet, args.dxl_id, ADDR_GOAL_POSITION, "goal_position")
        torque = r1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, "torque")
        moving = r1(port, packet, args.dxl_id, ADDR_MOVING, "moving")
        pwm = s16(r2(port, packet, args.dxl_id, ADDR_PRESENT_PWM, "pwm"))
        cur = s16(r2(port, packet, args.dxl_id, ADDR_PRESENT_CURRENT, "current"))
        vel = s32(r4(port, packet, args.dxl_id, ADDR_PRESENT_VELOCITY, "velocity"))

        print(
            f"torque={torque} moving={moving} "
            f"present={pos} goal={goal} error={int(pos)-target:+d} "
            f"vel={vel} current={cur} pwm={pwm}"
        )

        if abs(int(pos) - target) <= 5:
            print("CHEGOU NO ALVO.")
            break

        time.sleep(0.15)

finally:
    packet.write1ByteTxRx(port, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_OFF)
    port.closePort()
    print("Torque OFF. Motor liberado.")
