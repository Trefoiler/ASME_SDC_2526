import time
from machine import Pin

led = Pin("LED", Pin.OUT)

while True:
    led.toggle()
    print("blink")
    time.sleep(0.5)
