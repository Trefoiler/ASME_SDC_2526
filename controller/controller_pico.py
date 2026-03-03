"""
controller_pico.py

Receives control commands over Wi-Fi UDP from controller_pc.py.

Two Wi-Fi modes:
1) STA (station): Pico joins an existing Wi-Fi network (router or phone hotspot).
2) AP  (access point): Pico creates its own Wi-Fi network; the laptop connects to it.

Pick ONE by setting WIFI_MODE below.

When running, the Pico prints its IP address (172.20.10.6). Use that IP in controller_pc.py.

Packet format (little-endian), matches controller_pc.py:
  <I f f I
  seq      uint32
  throttle float32  (-1..1)
  turn     float32  (-1..1)
  buttons  uint32   bitmask

What you must customize:
- apply_controls(throttle, turn, buttons): hook this into your motor control.
"""

import network
import socket
import struct
import time


# -------------------- Wi-Fi configuration --------------------

WIFI_MODE = "STA"     # "STA" or "AP"

# If WIFI_MODE == "STA":
STA_SSID = "Owen’s iPhone"
STA_PASS = "12345678"

# If WIFI_MODE == "AP":
AP_SSID = "PICO_ROBOT"
AP_PASS = "pico12345"   # Must be at least 8 chars for WPA2 on many stacks

UDP_PORT = 4242


# -------------------- Control safety settings --------------------

# If we stop receiving packets for this many milliseconds, command zero output.
DEADMAN_TIMEOUT_MS = 250

# Optional: print status every so often
PRINT_EVERY_MS = 1000


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def connect_wifi() -> str:
    """
    Bring up Wi-Fi and return the Pico's IP address as a string.
    """
    if WIFI_MODE.upper() == "AP":
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        # authmode=3 is WPA2-PSK in many MicroPython ports
        ap.config(essid=AP_SSID, password=AP_PASS, authmode=3)
        time.sleep(0.5)
        ip = ap.ifconfig()[0]
        print("Pico AP active.")
        print("  SSID:", AP_SSID)
        print("  PASS:", AP_PASS)
        print("  Pico IP:", ip)
        print("Connect your laptop to this Wi-Fi, then run controller_pc.py using this IP.\n")
        return ip

    # Default: Station mode
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(STA_SSID, STA_PASS)

    print("Connecting to Wi-Fi...")
    t_start = time.ticks_ms()
    while not wlan.isconnected():
        time.sleep(0.1)
        if time.ticks_diff(time.ticks_ms(), t_start) > 15000:
            raise RuntimeError("Wi-Fi connect timeout. Check SSID/PASS or move closer to hotspot/router.")

    ip = wlan.ifconfig()[0]
    print("Wi-Fi connected.")
    print("  SSID:", STA_SSID)
    print("  Pico IP:", ip)
    print("Run controller_pc.py with --pico-ip", ip, "\n")
    return ip


def apply_controls(throttle: float, turn: float, buttons: int) -> None:
    """
    TODO: Replace this with your motor control code.

    Example idea for differential drive:
      left  = throttle + turn
      right = throttle - turn

    Then clamp to [-1, 1] and send to motor driver.
    """
    # Example placeholder:
    left = clamp(throttle + turn, -1.0, 1.0)
    right = clamp(throttle - turn, -1.0, 1.0)

    # Replace these prints with PWM / motor driver calls.
    # For now, do nothing or occasional debug prints handled in main loop.
    _ = (left, right, buttons)


def main() -> None:
    connect_wifi()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.settimeout(0.05)

    print("Listening for UDP packets on port", UDP_PORT)

    last_rx_ms = time.ticks_ms()
    last_print_ms = time.ticks_ms()

    # Last-known command values
    throttle = 0.0
    turn = 0.0
    buttons = 0
    seq = 0

    while True:
        # Try to receive a packet
        try:
            data, addr = sock.recvfrom(64)
            # Expect exactly 16 bytes, but tolerate larger packets
            if len(data) >= 16:
                seq, throttle, turn, buttons = struct.unpack("<IffI", data[:16])
                throttle = clamp(float(throttle), -1.0, 1.0)
                turn = clamp(float(turn), -1.0, 1.0)
                last_rx_ms = time.ticks_ms()
        except OSError:
            # Timeout, no packet this cycle
            pass

        # Deadman safety: stop if packets are stale
        age_ms = time.ticks_diff(time.ticks_ms(), last_rx_ms)
        if age_ms > DEADMAN_TIMEOUT_MS:
            throttle = 0.0
            turn = 0.0
            buttons = 0

        # Apply to robot
        apply_controls(throttle, turn, buttons)

        # Debug print occasionally
        now_ms = time.ticks_ms()
        if time.ticks_diff(now_ms, last_print_ms) >= PRINT_EVERY_MS:
            last_print_ms = now_ms
            print("seq=%d thr=%+.2f turn=%+.2f buttons=0x%08X age=%dms" %
                  (seq, throttle, turn, buttons, age_ms))


# Run
main()