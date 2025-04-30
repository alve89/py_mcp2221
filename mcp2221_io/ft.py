#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FT232H LED Blink Beispiel
-------------------------
Dieses Skript lässt eine LED blinken, die an einem GPIO-Pin
des FT232H-Breakout-Moduls angeschlossen ist.
"""

import time
from pyftdi.gpio import GpioController

# Konfiguration
LED_PIN = 0  # Der GPIO-Pin, an dem die LED angeschlossen ist (D0/ADBUS0)
BLINK_DELAY = 0.5  # Verzögerung in Sekunden zwischen ein/aus

def main():
    # Initialisierung des GPIO-Controllers
    gpio = GpioController()
    
    try:
        # Öffne das erste gefundene FT232H-Gerät
        gpio.open_from_url('ftdi://ftdi:232h/1')
        
        # Setze den LED-Pin als Ausgang
        gpio.set_direction(1 << LED_PIN, 1 << LED_PIN)
        
        print("LED-Blink-Programm gestartet. Drücken Sie Strg+C zum Beenden.")
        
        # Hauptschleife zum Blinken der LED
        while True:
            # LED einschalten
            gpio.set_output(1 << LED_PIN, 1 << LED_PIN)
            print("LED AN")
            time.sleep(BLINK_DELAY)
            
            # LED ausschalten
            gpio.set_output(1 << LED_PIN, 0)
            print("LED AUS")
            time.sleep(BLINK_DELAY)
            
    except KeyboardInterrupt:
        print("\nProgramm beendet.")
    finally:
        # Aufräumen und Ressourcen freigeben
        gpio.close()

if __name__ == "__main__":
    main()