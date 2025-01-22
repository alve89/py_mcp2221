#!/usr/bin/env python3

import mcp2221_patch
mcp2221_patch.patch_blinka()

import board
import digitalio
import time
import signal
import sys

def signal_handler(sig, frame):
    print('\nProgramm wird beendet...')
    if led.direction == digitalio.Direction.OUTPUT:
        led.value = False
    sys.exit(0)

# Registriere den Signal Handler für Ctrl+C
signal.signal(signal.SIGINT, signal_handler)

# LED auf G1 konfigurieren
led = digitalio.DigitalInOut(board.G1)
led.direction = digitalio.Direction.OUTPUT

print("Starte Blink-Test auf G1 (Strg+C zum Beenden)")
print("LED sollte im Sekundentakt blinken...")

try:
    while True:
        led.value = True
        print("LED an")
        time.sleep(1)
        led.value = False
        print("LED aus")
        time.sleep(1)
except Exception as e:
    print(f"Fehler: {e}")
finally:
    # Stelle sicher, dass LED aus ist
    led.value = False