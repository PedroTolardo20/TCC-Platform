#!/usr/bin/env python3
import argparse
import sys
import time

from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler

PROTOCOL_VERSION = 2.0

ADDR_HARDWARE_ERROR_STATUS = 70
ADDR_TORQUE_ENABLE = 64
ADDR_GOAL_POSITION = 116
ADDR_PRESENT_PWM = 124
ADDR_PRESENT_CURRENT = 126
ADDR_PRESENT_POSITION = 132

TORQUE_OFF = 0
TORQUE_ON = 1

DEFAULT_DEVICE = "/dev/serial/by-id/usb-CM-900_ROBOTIS_Virtual_COM_Port-if00"
DEFAULT_BAUD = 57600


def check(comm_result, dxl_error, packet, label):
    if comm_result != COMM_SUCCESS:
        print(f"ERRO {label}: {packet.getTxRxResult(comm_result)}", file=sys.stderr)
        return False
    if dxl_error != 0:
        print(f"ERRO {label}: {packet.getRxPacketError(dxl_error)}", file=sys.stderr)
        return False
    return True


def read_1(port, packet, dxl_id, address, label):
    value, comm_result, dxl_error = packet.read1ByteTxRx(port, dxl_id, address)
    if not check(comm_result, dxl_error, packet, label):
        return None
    return value


def read_2(port, packet, dxl_id, address, label):
    value, comm_result, dxl_error = packet.read2ByteTxRx(port, dxl_id, address)
    if not check(comm_result, dxl_error, packet, label):
        return None
    return value


def read_4(port, packet, dxl_id, address, label):
    value, comm_result, dxl_error = packet.read4ByteTxRx(port, dxl_id, address)
    if not check(comm_result, dxl_error, packet, label):
        return None
    return value


def write_1(port, packet, dxl_id, address, value, label):
    comm_result, dxl_error = packet.write1ByteTxRx(port, dxl_id, address, value)
    return check(comm_result, dxl_error, packet, label)


def write_4(port, packet, dxl_id, address, value, label):
    comm_result, dxl_error = packet.write4ByteTxRx(port, dxl_id, address, value)
    return check(comm_result, dxl_error, packet, label)


def signed_16(value):
    return value - 65536 if value > 32767 else value


parser = argparse.ArgumentParser(
    description="Teste incremental e seguro para um único Dynamixel XM540."
)
parser.add_argument("--id", type=int, required=True, dest="dxl_id")
parser.add_argument("--delta", type=int, required=True,
                    help="Deslocamento em ticks, entre -100 e +100.")
parser.add_argument("--confirm", action="store_true")
parser.add_argument("--device", default=DEFAULT_DEVICE)
parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
parser.add_argument("--timeout", type=float, default=5.0)
args = parser.parse_args()

if not args.confirm:
    parser.error("Use --confirm para habilitar movimento.")
if not -100 <= args.delta <= 100:
    parser.error("Por segurança, --delta deve estar entre -100 e +100.")

port = PortHandler(args.device)
packet = PacketHandler(PROTOCOL_VERSION)

if not port.openPort():
    print(f"ERRO: não foi possível abrir {args.device}", file=sys.stderr)
    sys.exit(1)

if not port.setBaudRate(args.baud):
    print(f"ERRO: não foi possível configurar baud {args.baud}", file=sys.stderr)
    port.closePort()
    sys.exit(1)

try:
    print(f"=== XM540 JOG TEST | ID {args.dxl_id} | delta {args.delta:+d} ticks ===")

    initial = read_4(port, packet, args.dxl_id, ADDR_PRESENT_POSITION, "posição inicial")
    hardware_error = read_1(port, packet, args.dxl_id, ADDR_HARDWARE_ERROR_STATUS, "erro de hardware")

    if initial is None or hardware_error is None:
        sys.exit(1)

    if hardware_error != 0:
        print(f"ABORTADO: hardware_error_status={hardware_error}", file=sys.stderr)
        sys.exit(1)

    target = initial + args.delta
    if not 0 <= target <= 4095:
        print(f"ABORTADO: alvo {target} fora do intervalo 0–4095.", file=sys.stderr)
        sys.exit(1)

    print(f"Posição atual: {initial} ticks")
    print(f"Alvo seguro:   {target} ticks")
    print("Apenas o motor selecionado será acionado. Mantenha a junta livre.")

    if not write_1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_OFF, "Torque OFF"):
        sys.exit(1)

    if not write_4(port, packet, args.dxl_id, ADDR_GOAL_POSITION, target, "Goal Position"):
        sys.exit(1)

    if not write_1(port, packet, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ON, "Torque ON"):
        sys.exit(1)

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        position = read_4(port, packet, args.dxl_id, ADDR_PRESENT_POSITION, "posição")
        current_raw = read_2(port, packet, args.dxl_id, ADDR_PRESENT_CURRENT, "corrente")
        pwm_raw = read_2(port, packet, args.dxl_id, ADDR_PRESENT_PWM, "PWM")

        if position is None:
            break

        current = signed_16(current_raw) if current_raw is not None else "n/a"
        pwm = signed_16(pwm_raw) if pwm_raw is not None else "n/a"
        error = position - target

        print(f"present={position:4d} | target={target:4d} | error={error:+4d} | current={current} | pwm={pwm}")

        if abs(error) <= 3:
            print("MOVIMENTO CONCLUÍDO.")
            break

        time.sleep(0.15)
    else:
        print("AVISO: tempo esgotado; torque será desligado.")

finally:
    packet.write1ByteTxRx(port, args.dxl_id, ADDR_TORQUE_ENABLE, TORQUE_OFF)
    port.closePort()
    print("Torque OFF. Motor liberado.")
