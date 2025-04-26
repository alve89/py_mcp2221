# garage_door_test.py
# Version: 1.0.0

import time
import sys
import os
import logging

# Füge das Projektverzeichnis zum Suchpfad hinzu
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.append(project_dir)

from mcp2221_io import Sensor, Actor, Cover, CoverState, LogCategory, logger

# Konfiguriere Logging
logger.set_level(logging.DEBUG)

def test_garage_door_logic():
    """Testet die Logik der Garagentor-Steuerung mit simulierten Sensoren"""
    print("=== Garage Door Logic Test ===")
    
    # Erstelle einen Actor für das Tor
    actor = Actor("G1", inverted=True)
    
    # Erstelle die Sensoren
    sensor_open = Sensor("G2", inverted=False, name="garage_open")
    sensor_closed = Sensor("G3", inverted=False, name="garage_closed")
    
    # Erstelle das Cover
    cover = Cover(
        actor=actor,
        sensor_open_id="garage_open",
        sensor_closed_id="garage_closed",
        inverted=False
    )
    
    # Füge Callback hinzu, um Zustandsänderungen zu tracken
    def on_cover_state_changed(state):
        print(f"\n🔔 Cover-Zustand geändert: {state}")
        print(f"  - Sensor offen: {cover.sensor_open_state}")
        print(f"  - Sensor geschlossen: {cover.sensor_closed_state}")
    
    cover.set_state_changed_callback(on_cover_state_changed)
    
    # Teste verschiedene Sensorzustände
    test_cases = [
        # Tor geschlossen
        {"open": False, "closed": True, "expected": CoverState.CLOSED},
        # Tor öffnet sich
        {"open": False, "closed": False, "expected": CoverState.OPENING},
        # Tor offen
        {"open": True, "closed": False, "expected": CoverState.OPEN},
        # Tor schließt sich
        {"open": False, "closed": False, "expected": CoverState.CLOSING},
        # Tor wieder geschlossen
        {"open": False, "closed": True, "expected": CoverState.CLOSED},
        # Ungültiger Zustand (beide Sensoren aktiv)
        {"open": True, "closed": True, "expected": None},
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\n=== Test Case {i+1} ===")
        print(f"Setze Sensorzustände: open={test_case['open']}, closed={test_case['closed']}")
        print(f"Erwarteter Zustand: {test_case['expected']}")
        
        old_state = cover.state
        cover.update_sensor_states(test_case['open'], test_case['closed'])
        
        print(f"Aktueller Zustand: {cover.state}")
        if test_case['expected'] and cover.state != test_case['expected']:
            print(f"❌ FEHLER: Erwarteter Zustand {test_case['expected']} ist nicht gleich dem aktuellen Zustand {cover.state}")
        elif not test_case['expected']: # Bei ungültigen Zuständen sollte sich nichts ändern
            if old_state == cover.state:
                print(f"✅ OK: Zustand wurde bei ungültigem Sensorstatus nicht geändert: {cover.state}")
            else:
                print(f"❌ FEHLER: Zustand hat sich bei ungültigem Sensorstatus geändert: {old_state} -> {cover.state}")
        else:
            print(f"✅ OK: Zustand entspricht der Erwartung: {cover.state}")
        
        # Kurze Pause für bessere Lesbarkeit
        time.sleep(0.5)

def create_sensor_diagnostics_script():
    """Erstellt ein Skript, das regelmäßig die Sensorwerte ausgibt"""
    script_content = """#!/usr/bin/env python3
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
        print("\\nDiagnostik beendet.")
    finally:
        # Pins aufräumen
        open_pin.deinit()
        closed_pin.deinit()

if __name__ == "__main__":
    main()
"""
    
    # Schreibe die Datei
    script_path = os.path.join(project_dir, "mcp2221_io", "sensor_diagnostics.py")
    with open(script_path, "w") as f:
        f.write(script_content)
    
    # Mache die Datei ausführbar
    os.chmod(script_path, 0o755)
    
    print(f"Diagnostik-Skript erstellt: {script_path}")
    print("Führe es aus mit: python3 -m mcp2221_io.sensor_diagnostics")

if __name__ == "__main__":
    print("Führe Garagentor-Tests aus...")
    
    # Logik-Test
    test_garage_door_logic()
    
    # Erstelle Diagnose-Skript
    create_sensor_diagnostics_script()
    
    print("\nTests abgeschlossen. Ein Diagnose-Skript wurde erstellt.")
    print("Es kann mit 'python3 -m mcp2221_io.sensor_diagnostics' ausgeführt werden.")