#!/usr/bin/env python3
import argparse
import socket
import struct
import time

import pygame

# Default Pico IP you gave
DEFAULT_PICO_IP = "172.20.10.6"
DEFAULT_PORT = 4242
DEFAULT_RATE_HZ = 50
DEFAULT_DEADZONE = 0.08

# Axis mapping defaults (often correct, but you may need to change after probing)
# We send:
#   lx, ly  = left stick (x right positive, y up positive)
#   rx, ry  = right stick (x right positive, y up positive)
#   lt, rt  = triggers (usually 0..1 or -1..1 depending on controller/OS)
LX_AXIS = 0
LY_AXIS = 1
RX_AXIS = 2
RY_AXIS = 3
LT_AXIS = 4
RT_AXIS = 5

# Packet format:
# seq, lx, ly, rx, ry, lt, rt, buttons_bitmask, hat_x, hat_y
PKT = struct.Struct("<IffffffIbb")


def deadzone(x: float, dz: float) -> float:
    return 0.0 if abs(x) < dz else x


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def get_axis_safe(js, idx: int) -> float:
    # Returns 0.0 if the axis index does not exist
    if idx < 0 or idx >= js.get_numaxes():
        return 0.0
    return float(js.get_axis(idx))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pico-ip", default=DEFAULT_PICO_IP)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE_HZ)
    ap.add_argument("--deadzone", type=float, default=DEFAULT_DEADZONE)
    ap.add_argument("--joystick", type=int, default=0, help="Which controller to use if multiple are connected")
    ap.add_argument("--probe", action="store_true", help="Print all axes/buttons/hats to find the right mapping")
    args = ap.parse_args()

    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    if count == 0:
        raise RuntimeError("No controller detected. Pair it to the laptop (Bluetooth) or plug it in (USB).")

    if args.joystick < 0 or args.joystick >= count:
        raise RuntimeError(f"Invalid --joystick {args.joystick}. Detected {count} controller(s).")

    js = pygame.joystick.Joystick(args.joystick)
    js.init()

    print("Controller:", js.get_name())
    print("Axes:", js.get_numaxes(), "Buttons:", js.get_numbuttons(), "Hats:", js.get_numhats())
    print("Sending UDP to", (args.pico_ip, args.port))
    print("Tip: run with --probe once to discover axis indices.\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.pico_ip, args.port)

    seq = 0
    period = 1.0 / max(args.rate, 1.0)
    last_probe_print = time.time()

    try:
        while True:
            t0 = time.time()

            # Needed so pygame updates state
            pygame.event.pump()

            # Read raw axes
            lx = get_axis_safe(js, LX_AXIS)
            ly = get_axis_safe(js, LY_AXIS)
            rx = get_axis_safe(js, RX_AXIS)
            ry = get_axis_safe(js, RY_AXIS)
            lt = get_axis_safe(js, LT_AXIS)
            rt = get_axis_safe(js, RT_AXIS)

            # Make "up" positive for both sticks (most controllers report up as negative)
            ly = -ly
            ry = -ry

            # Deadzone + clamp
            lx = clamp(deadzone(lx, args.deadzone), -1.0, 1.0)
            ly = clamp(deadzone(ly, args.deadzone), -1.0, 1.0)
            rx = clamp(deadzone(rx, args.deadzone), -1.0, 1.0)
            ry = clamp(deadzone(ry, args.deadzone), -1.0, 1.0)

            # Buttons bitmask (first 32)
            buttons = 0
            n_btn = min(js.get_numbuttons(), 32)
            for i in range(n_btn):
                if js.get_button(i):
                    buttons |= (1 << i)

            # D-pad is often a "hat", not buttons
            hat_x, hat_y = 0, 0
            if js.get_numhats() > 0:
                hx, hy = js.get_hat(0)  # -1,0,1
                hat_x, hat_y = int(hx), int(hy)

            # Optional probe print to discover mappings
            if args.probe and (time.time() - last_probe_print) > 0.25:
                last_probe_print = time.time()
                axes = [round(get_axis_safe(js, i), 3) for i in range(js.get_numaxes())]
                hats = [js.get_hat(i) for i in range(js.get_numhats())]
                print("AXES:", axes, "HATS:", hats, "buttons_mask:", hex(buttons))

            # Send packet
            pkt = PKT.pack(seq, lx, ly, rx, ry, lt, rt, buttons, hat_x, hat_y)
            sock.sendto(pkt, target)
            seq = (seq + 1) & 0xFFFFFFFF

            # Maintain rate
            dt = time.time() - t0
            if dt < period:
                time.sleep(period - dt)

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        js.quit()
        pygame.quit()


if __name__ == "__main__":
    main()