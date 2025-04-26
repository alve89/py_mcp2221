# debug_cover.py
# Version: 1.0.0

"""
Diagnose-Skript für Cover-Probleme. Lesen Sie die Sensoren direkt aus
und simulieren Sie die Cover-Zustandslogik mit verschiedenen Konfigurationsoptionen.
"""

import sys
import os
import time
import board
import digitalio
from datetime import datetime

def diagnose_cover_sensors():
    """
    Liest die Garagentor-Sensoren direkt aus und zeigt die Rohwerte und
    simulierte Berechnungen mit verschiedenen Invertierungsoptionen an.
    """
    print("=== Garagentor-Sensor-Diagnose ===")
    print("Direkte Sensor-Lesung ohne Zwischenschichten")
    print("Drücken Sie STRG+C, um zu beenden.\n")
    
    try:
        # Direkte PIN-Konfiguration
        open_pin = digitalio.DigitalInOut(board.G2)
        open_pin.direction = digitalio.Direction.INPUT
        
        closed_pin = digitalio.DigitalInOut(board.G3)
        closed_pin.direction = digitalio.Direction.INPUT
        
        print("Sensor-Mapping:")
        print(f"- 'garage_open' : GPIO-Pin G2")
        print(f"- 'garage_closed': GPIO-Pin G3")
        print("\nLegende:")
        print("- RAW: Die direkt aus den Pins gelesenen Werte")
        print("- STD: Standardlogik (open=TRUE, closed=FALSE) → OPEN")
        print("- INV1: Mit invertiertem open-Sensor")
        print("- INV2: Mit invertiertem closed-Sensor")
        print("- INV12: Mit beiden Sensoren invertiert")
        print("\nStarte Diagnose...")
        
        while True:
            # Direktes Auslesen der Pins
            raw_open = open_pin.value
            raw_closed = closed_pin.value
            
            # Timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Standard-Logik (keine Invertierung)
            state_std = get_cover_state(raw_open, raw_closed, False, False)
            
            # Verschiedene Invertierungskombinationen
            state_inv1 = get_cover_state(raw_open, raw_closed, True, False)  # open invertiert
            state_inv2 = get_cover_state(raw_open, raw_closed, False, True)  # closed invertiert
            state_inv12 = get_cover_state(raw_open, raw_closed, True, True)  # beide invertiert
            
            # Ausgabe
            print(f"[{timestamp}] RAW: open={raw_open}, closed={raw_closed}")
            print(f"  Zustandsberechnung:")
            print(f"  - STD   (open={raw_open}, closed={raw_closed}): {state_std}")
            print(f"  - INV1  (open={not raw_open}, closed={raw_closed}): {state_inv1}")
            print(f"  - INV2  (open={raw_open}, closed={not raw_closed}): {state_inv2}")
            print(f"  - INV12 (open={not raw_open}, closed={not raw_closed}): {state_inv12}")
            print("=" * 60)
            
            # Warte 1 Sekunde
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nDiagnose beendet.")
    finally:
        # Pins aufräumen
        try:
            open_pin.deinit()
            closed_pin.deinit()
        except:
            pass

def get_cover_state(sensor_open, sensor_closed, invert_open, invert_closed):
    """
    Berechnet den Cover-Zustand basierend auf den Sensorwerten und Invertierungsoptionen.
    
    :param sensor_open: Zustand des "offen"-Sensors
    :param sensor_closed: Zustand des "geschlossen"-Sensors
    :param invert_open: Ob der "offen"-Sensor invertiert werden soll
    :param invert_closed: Ob der "geschlossen"-Sensor invertiert werden soll
    :return: Der berechnete Zustand des Covers
    """
    # Invertierung anwenden, wenn konfiguriert
    if invert_open:
        sensor_open = not sensor_open
    if invert_closed:
        sensor_closed = not sensor_closed
    
    # Zustandslogik
    if sensor_open and not sensor_closed:
        return "OPEN"
    elif not sensor_open and sensor_closed:
        return "CLOSED"
    elif not sensor_open and not sensor_closed:
        return "IN_BEWEGUNG"
    else:
        return "UNGÜLTIG"

if __name__ == "__main__":
    diagnose_cover_sensors()