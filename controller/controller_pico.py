import network
import socket
import struct
import time

STA_SSID = "Owen’s iPhone"   # keep the curly apostrophe exactly
STA_PASS = "12345678"
UDP_PORT = 4242

# Stop the robot if we do not receive packets for this long
DEADMAN_MS = 250

# Same packet format as the PC script
PKT = struct.Struct("<IffffffIbb")


def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(STA_SSID, STA_PASS)

    t0 = time.ticks_ms()
    while not wlan.isconnected():
        time.sleep(0.1)
        if time.ticks_diff(time.ticks_ms(), t0) > 15000:
            raise RuntimeError("Wi-Fi connect timeout. Check SSID/PASS and hotspot settings.")

    ip = wlan.ifconfig()[0]
    print("Connected. Pico IP:", ip)
    return ip


def main():
    wifi_connect()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.settimeout(0.05)

    print("Listening UDP on port", UDP_PORT)

    last_rx = time.ticks_ms()
    last_print = time.ticks_ms()

    # Latest controls
    seq = 0
    lx = ly = rx = ry = lt = rt = 0.0
    buttons = 0
    hat_x = hat_y = 0

    while True:
        # Receive latest packet if available
        try:
            data, _addr = sock.recvfrom(64)
            if len(data) >= PKT.size:
                seq, lx, ly, rx, ry, lt, rt, buttons, hat_x, hat_y = PKT.unpack(data[:PKT.size])
                last_rx = time.ticks_ms()
        except OSError:
            pass

        # Deadman: zero outputs if link is stale
        age = time.ticks_diff(time.ticks_ms(), last_rx)
        if age > DEADMAN_MS:
            lx = ly = rx = ry = lt = rt = 0.0
            buttons = 0
            hat_x = hat_y = 0

        # TODO: replace this with your motor code
        # Example: use left stick as x/y command
        # x = lx (right positive), y = ly (up positive)

        # Print a concise status once per second
        if time.ticks_diff(time.ticks_ms(), last_print) > 1000:
            last_print = time.ticks_ms()
            print(
                "seq=%d lx=%+.2f ly=%+.2f rx=%+.2f ry=%+.2f lt=%+.2f rt=%+.2f buttons=0x%08X hat=(%d,%d) age=%dms"
                % (seq, lx, ly, rx, ry, lt, rt, buttons, hat_x, hat_y, age)
            )


main()