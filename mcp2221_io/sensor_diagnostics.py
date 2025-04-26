#!/usr/bin/env python3
# sensor_diagnostics.py
# Überwacht kontinuierlich die Sensorzustände und meldet sie

import time
import sys
import os
import logging
from datetime import datetime

# Füge das Projektverzeichnis zum Suchpfad hinzu
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.append(project_dir)

from mcp2221_io.logging_config import logger, LogCategory
import board
import digitalio

def main():
    print("=== Garage Door Sensor Diagnostics ===")
    print("Überwache Sensorzustände in Echtzeit. Drücke STRG+C zum Beenden.")
    
    # Konfiguriere Pins
    open_pin = digitalio.DigitalInOut(board.G2)
    open_pin.direction = digitalio.Direction.INPUT
    
    closed_pin = digitalio.DigitalInOut(board.G3)
    closed_pin.direction = digitalio.Direction.INPUT
    
    try:
        while True:
            open_value = open_pin.value
            closed_value = closed_pin.value
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Status ausgeben
            status_line = f"[{timestamp}] SENSOR STATUS: open={open_value}, closed={closed_value} | "
            
            # Zustandslogik anwenden
            if open_value and not closed_value:
                status_line += "ZUSTAND: OFFEN"
            elif not open_value and closed_value:
                status_line += "ZUSTAND: GESCHLOSSEN"
            elif not open_value and not closed_value:
                status_line += "ZUSTAND: IN BEWEGUNG"
            elif open_value and closed_value:
                status_line += "ZUSTAND: UNGÜLTIG (beide Sensoren aktiv)"
            
            print(status_line)
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nDiagnostik beendet.")
    finally:
        # Pins aufräumen
        open_pin.deinit()
        closed_pin.deinit()

if __name__ == "__main__":
    main()
