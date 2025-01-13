import os
import time
from enum import Enum

# Umgebungsvariable MUSS vor board/digitalio Import gesetzt werden
os.environ['BLINKA_MCP2221'] = '1'

import board
import digitalio

class IOMode(Enum):
    """Enumeration für die verschiedenen IO-Modi"""
    SENSOR = 1
    ACTOR = 2

class IODevice:
    """Basisklasse für IO-Geräte (Sensoren und Aktoren)"""
    def __init__(self, pin: str, inverted: bool = False, mode: IOMode = None):
        print(f"[DEBUG] Initialisiere IODevice für Pin {pin}, inverted={inverted}")  # Debug
        self.pin_name = pin
        self.inverted = inverted
        self.mode = mode
        
        try:
            self.pin = digitalio.DigitalInOut(getattr(board, pin))
            print(f"[DEBUG] GPIO {pin} erfolgreich initialisiert")  # Debug
        except Exception as e:
            print(f"[ERROR] Fehler bei GPIO-Initialisierung: {e}")  # Debug
            raise
        
        try:
            if mode == IOMode.SENSOR:
                self.pin.direction = digitalio.Direction.INPUT
                print(f"[DEBUG] Pin {pin} als INPUT konfiguriert")  # Debug
            elif mode == IOMode.ACTOR:
                self.pin.direction = digitalio.Direction.OUTPUT
                print(f"[DEBUG] Pin {pin} als OUTPUT konfiguriert")  # Debug
            else:
                raise ValueError("Mode muss SENSOR oder ACTOR sein")
        except Exception as e:
            print(f"[ERROR] Fehler bei Richtungskonfiguration: {e}")  # Debug
            raise

    def _convert_value(self, value: bool) -> bool:
        """Konvertiert einen Wert entsprechend der Inversionseinstellung"""
        result = not value if self.inverted else value
        print(f"[DEBUG] Wertkonvertierung: {value} -> {result} (inverted={self.inverted})")  # Debug
        return result

class Sensor(IODevice):
    """Klasse für Sensoren"""
    def __init__(self, pin: str, inverted: bool = False):
        print(f"[DEBUG] Erstelle Sensor an Pin {pin}")  # Debug
        super().__init__(pin, inverted, IOMode.SENSOR)

    def read(self) -> bool:
        """Liest den aktuellen Zustand des Sensors"""
        raw_value = self.pin.value
        converted_value = self._convert_value(raw_value)
        print(f"[DEBUG] Sensor {self.pin_name} liest: {raw_value} -> {converted_value}")  # Debug
        return converted_value

class Actor(IODevice):
    """Klasse für Aktoren"""
    def __init__(self, pin: str, inverted: bool = False):
        print(f"[DEBUG] Erstelle Actor an Pin {pin}")  # Debug
        super().__init__(pin, inverted, IOMode.ACTOR)
        self._state = False
        # Initialen Zustand setzen
        self.set(False)
        print(f"[DEBUG] Actor {pin} mit initialem Zustand False erstellt")  # Debug

    @property
    def state(self) -> bool:
        return self._state

    def set(self, value: bool):
        """Setzt den Zustand des Aktors"""
        print(f"[DEBUG] Actor {self.pin_name}: Setze Zustand auf {value}")  # Debug
        self._state = value
        physical_value = self._convert_value(value)
        print(f"[DEBUG] Actor {self.pin_name}: Setze physischen Pin auf {physical_value}")  # Debug
        try:
            self.pin.value = physical_value
            print(f"[DEBUG] Actor {self.pin_name}: Pin-Wert erfolgreich gesetzt")  # Debug
        except Exception as e:
            print(f"[ERROR] Fehler beim Setzen des Pin-Werts: {e}")  # Debug
            raise

    def toggle(self):
        """Wechselt den Zustand des Aktors"""
        print(f"[DEBUG] Actor {self.pin_name}: Toggle von {self._state}")  # Debug
        self.set(not self._state)