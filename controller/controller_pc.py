#!/usr/bin/env python3
"""
controller_pc.py

Reads a game controller on a PC and streams control commands to a Pico 2 W
over Wi-Fi using UDP.

Works with:
- Controller connected to the PC over Bluetooth OR USB (wired).
- The PC and Pico must be on the same Wi-Fi network, OR the Pico can host its own AP.

Packet format (little-endian):
  <I f f I
  seq     : uint32  (sequence number)
  throttle: float32 (-1.0 .. 1.0)  forward/back
  turn    : float32 (-1.0 .. 1.0)  left/right
  buttons : uint32  (bitmask of up to 32 buttons)

Install dependency:
  python -m pip install pygame

Run example:
  python controller_pc.py --pico-ip 192.168.1.123 --port 4242
"""

import argparse
import socket
import struct
import time

import pygame


# -------------------- Tuning knobs --------------------

DEFAULT_PORT = 4242
DEFAULT_RATE_HZ = 50          # Send rate (packets per second)
DEFAULT_DEADZONE = 0.08       # Ignore tiny stick noise near zero

# Axis mapping defaults (common for many controllers, but may vary):
#  - "turn" is usually left stick X
#  - "throttle" is usually left stick Y (often inverted, hence the minus)
DEFAULT_AXIS_TURN = 0
DEFAULT_AXIS_THROTTLE = 1
INVERT_THROTTLE = True

# If you want right stick instead, try:
# DEFAULT_AXIS_TURN = 2 or 3 depending on controller


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def apply_deadzone(x: float, dz: float) -> float:
    """
    Deadzone: map small values to 0.
    Keeps sign the same. Does not rescale. Simple and predictable.
    """
    return 0.0 if abs(x) < dz else x


def pick_joystick(index: int | None) -> pygame.joystick.Joystick:
    """
    Initialize pygame joystick system and pick a controller.
    """
    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    if count == 0:
        raise RuntimeError("No controller detected by pygame. Plug it in or pair it to the PC first.")

    if index is None:
        index = 0
    if index < 0 or index >= count:
        raise RuntimeError(f"Joystick index {index} out of range. Detected {count} controller(s).")

    js = pygame.joystick.Joystick(index)
    js.init()

    print("Selected controller:")
    print("  Name:", js.get_name())
    print("  Axes:", js.get_numaxes(), " Buttons:", js.get_numbuttons(), " Hats:", js.get_numhats())
    print("If stick directions are wrong, adjust axis mapping in the script or use CLI flags.\n")

    return js


def build_buttons_bitmask(js: pygame.joystick.Joystick) -> int:
    """
    Convert first 32 buttons into a bitmask.
    Button indexing differs by controller/OS, but this gives you something consistent.
    """
    mask = 0
    n = min(js.get_numbuttons(), 32)
    for i in range(n):
        if js.get_button(i):
            mask |= (1 << i)
    return mask


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pico-ip", required=True, help="IP address of the Pico 2 W (printed by controller_pico.py)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"UDP port (default {DEFAULT_PORT})")
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE_HZ, help=f"Send rate in Hz (default {DEFAULT_RATE_HZ})")
    ap.add_argument("--deadzone", type=float, default=DEFAULT_DEADZONE, help=f"Analog deadzone (default {DEFAULT_DEADZONE})")
    ap.add_argument("--joystick", type=int, default=None, help="Which controller to use if multiple are connected (0, 1, 2, ...)")
    ap.add_argument("--axis-turn", type=int, default=DEFAULT_AXIS_TURN, help=f"Axis index for turn (default {DEFAULT_AXIS_TURN})")
    ap.add_argument("--axis-throttle", type=int, default=DEFAULT_AXIS_THROTTLE, help=f"Axis index for throttle (default {DEFAULT_AXIS_THROTTLE})")
    ap.add_argument("--no-invert-throttle", action="store_true", help="Disable throttle inversion")
    args = ap.parse_args()

    js = pick_joystick(args.joystick)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.pico_ip, args.port)

    invert_throttle = (not args.no_invert_throttle) and INVERT_THROTTLE

    seq = 0
    send_period = 1.0 / max(args.rate, 1.0)
    last_print = time.time()

    print("Streaming to Pico:")
    print("  Target:", target)
    print("  Rate:", args.rate, "Hz")
    print("  Deadzone:", args.deadzone)
    print("  Axis throttle:", args.axis_throttle, "(inverted)" if invert_throttle else "")
    print("  Axis turn:", args.axis_turn)
    print("\nPress Ctrl+C to stop.\n")

    try:
        while True:
            t0 = time.time()

            # Needed so pygame updates controller state.
            pygame.event.pump()

            # Read axes
            try:
                raw_turn = js.get_axis(args.axis_turn)
                raw_thr = js.get_axis(args.axis_throttle)
            except IndexError:
                raise RuntimeError("Axis index out of range. Use --axis-turn / --axis-throttle to pick valid axes.")

            if invert_throttle:
                raw_thr = -raw_thr

            # Apply deadzone and clamp
            turn = clamp(apply_deadzone(float(raw_turn), args.deadzone), -1.0, 1.0)
            throttle = clamp(apply_deadzone(float(raw_thr), args.deadzone), -1.0, 1.0)

            # Buttons bitmask
            buttons = build_buttons_bitmask(js)

            # Pack and send
            pkt = struct.pack("<IffI", seq, throttle, turn, buttons)
            sock.sendto(pkt, target)
            seq = (seq + 1) & 0xFFFFFFFF

            # Occasionally print status so you know it is alive
            now = time.time()
            if now - last_print > 1.0:
                last_print = now
                print(f"thr={throttle:+.2f}  turn={turn:+.2f}  buttons=0x{buttons:08X}  seq={seq}")

            # Sleep to maintain approximate send rate
            dt = time.time() - t0
            if dt < send_period:
                time.sleep(send_period - dt)

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        try:
            js.quit()
        except Exception:
            pass
        pygame.quit()


if __name__ == "__main__":
    main()