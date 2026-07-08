#!/usr/bin/env python3
import argparse
import sys
import time
from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler

PROTOCOL_VERSION = 2.0

ADDR_TORQUE_ENABLE = 64
ADDR_HARDWARE_ERROR_STATUS = 70
ADDR_PROFILE_ACCELERATION = 108
ADDR_PROFILE_VELOCITY = 112
ADDR_GOAL_POSITION = 116
ADDR_MOVING = 122
ADDR_PRESENT_POSITION = 132

TORQUE_OFF = 0
TORQUE_ON = 1
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

parser = argparse.ArgumentParser()
parser.add_argument("--id", type=int, required=True, dest="dxl_id")
parser.add_argument("--target", type=int, required=True)
parser.add_argument("--baud", type=int, default=1000000)
parser.add_argument("--velocity", type=int, default=8)
parser.add_argument("--acceleration", type=int, default=3)
parser.add_argument("--confirm", action="store_true")
parser.add_argument("--device", default=DEFAULT_DEVICE)
args = parser.parse_args()

if not args.confirm:
    parser.error("Use --confirm.")

if not 0 <= args.target <= 4095:
    parser.error("--target deve estar entre 0 e 4095.")

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
    print(f"=== MOVE TO TICK XM540 | ID {args.dxl_id} | target {args.target} ===")

    hwerr = r1(port, packet, args.dxl_id, ADDR_HARDWARE_ERROR_STATUS, "hardware_error")
    pos0 = r4(port, packet, args.dxl_id, ADDR_PRESENT_POSITION, "present_position")

    if hwerr != 0:
        print(f"ABORTADO: hardware_error_status={hwerr}")
        sys.exit(1)

    print(f"Posição inicial: {pos0}")
    print(f"Alvo:            {args.target}")
    print(f"Velocidade:      {args.velocity}")
    time.sleep(1.0)

    w1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_OFF, "torque off")
    w4(port, packet, args.dxl_id, ADDR_PROFILE_ACCELERATION, args.acceleration, "profile acceleration")
    w4(port, packet, args.dxl_id, ADDR_PROFILE_VELOCITY, args.velocity, "profile velocity")
    w1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ON, "torque on")
    time.sleep(0.2)
    w4(port, packet, args.dxl_id, ADDR_GOAL_POSITION, args.target, "goal position")

    for _ in range(100):
        pos = r4(port, packet, args.dxl_id, ADDR_PRESENT_POSITION, "present_position")
        moving = r1(port, packet, args.dxl_id, ADDR_MOVING, "moving")
        print(f"present={pos:4d} | target={args.target:4d} | error={pos-args.target:+4d} | moving={moving}")

        if abs(pos - args.target) <= 5:
            print("CHEGOU NO ALVO.")
            break

        time.sleep(0.2)

finally:
    packet.write1ByteTxRx(port, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_OFF)
    port.closePort()
    print("Torque OFF. Motor liberado.")
