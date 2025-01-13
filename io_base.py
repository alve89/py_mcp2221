import os
import time
import threading
from enum import Enum

# Umgebungsvariablen nur setzen wenn nicht bereits gesetzt
if 'BLINKA_MCP2221' not in os.environ:
    os.environ['BLINKA_MCP2221'] = '1'
if 'BLINKA_MCP2221_RESET_DELAY' not in os.environ:
    os.environ['BLINKA_MCP2221_RESET_DELAY'] = '-1'

import board
import digitalio

class IOMode(Enum):
    """Enumeration für die verschiedenen IO-Modi"""
    SENSOR = 1
    ACTOR = 2

class IODevice:
    """Basisklasse für IO-Geräte (Sensoren und Aktoren)"""
    def __init__(self, pin: str, inverted: bool = False, mode: IOMode = None):
        print(f"[DEBUG] Initialisiere IODevice für Pin {pin}, inverted={inverted}")
        self.pin_name = pin
        self.inverted = inverted
        self.mode = mode
        
        try:
            self.pin = digitalio.DigitalInOut(getattr(board, pin))
            print(f"[DEBUG] GPIO {pin} erfolgreich initialisiert")
        except Exception as e:
            print(f"[ERROR] Fehler bei GPIO-Initialisierung: {e}")
            raise
        
        try:
            if mode == IOMode.SENSOR:
                self.pin.direction = digitalio.Direction.INPUT
                print(f"[DEBUG] Pin {pin} als INPUT konfiguriert")
            elif mode == IOMode.ACTOR:
                self.pin.direction = digitalio.Direction.OUTPUT
                print(f"[DEBUG] Pin {pin} als OUTPUT konfiguriert")
            else:
                raise ValueError("Mode muss SENSOR oder ACTOR sein")
        except Exception as e:
            print(f"[ERROR] Fehler bei Richtungskonfiguration: {e}")
            raise

    def _convert_value(self, value: bool) -> bool:
        """Konvertiert einen Wert entsprechend der Inversionseinstellung"""
        result = not value if self.inverted else value
        print(f"[DEBUG] Wertkonvertierung: {value} -> {result} (inverted={self.inverted})")
        return result

class Sensor(IODevice):
    """Klasse für Sensoren"""
    def __init__(self, pin: str, inverted: bool = False):
        print(f"[DEBUG] Erstelle Sensor an Pin {pin}")
        super().__init__(pin, inverted, IOMode.SENSOR)

    def read(self) -> bool:
        """Liest den aktuellen Zustand des Sensors"""
        raw_value = self.pin.value
        converted_value = self._convert_value(raw_value)
        print(f"[DEBUG] Sensor {self.pin_name} liest: {raw_value} -> {converted_value}")
        return converted_value

class Actor(IODevice):
    """Klasse für Aktoren"""
    def __init__(self, pin: str, inverted: bool = False, reset_delay: float = 0):
        print(f"[DEBUG] Erstelle Actor an Pin {pin}")
        super().__init__(pin, inverted, IOMode.ACTOR)
        self._state = False
        self._reset_delay = reset_delay
        self._reset_timer = None
        self._is_resetting = False  # Flag für Reset-Zustand
        # Initialen Zustand setzen
        self.set(False)
        print(f"[DEBUG] Actor {pin} mit initialem Zustand False erstellt")

    @property
    def state(self) -> bool:
        return self._state

    def set(self, value: bool):
        """Setzt den Zustand des Aktors"""
        print(f"[DEBUG] Actor {self.pin_name}: Setze Zustand auf {value}")
        self._state = value
        physical_value = self._convert_value(value)
        print(f"[DEBUG] Actor {self.pin_name}: Setze physischen Pin auf {physical_value}")
        try:
            self.pin.value = physical_value
            print(f"[DEBUG] Actor {self.pin_name}: Pin-Wert erfolgreich gesetzt")
        except Exception as e:
            print(f"[ERROR] Fehler beim Setzen des Pin-Werts: {e}")
            raise

    def _reset_action(self):
        """Interne Methode für den Reset-Vorgang"""
        print(f"[DEBUG] Actor {self.pin_name}: Führe Reset aus")
        self._is_resetting = True
        self.toggle()  # Führt den Reset durch
        self._is_resetting = False
        self._reset_timer = None

    def toggle(self):
        """Wechselt den Zustand des Aktors und setzt ggf. einen Reset-Timer"""
        print(f"[DEBUG] Actor {self.pin_name}: Toggle von {self._state}")
        
        # Toggle the state
        self.set(not self._state)
        
        # Wenn dies kein Reset-Vorgang ist und reset_delay konfiguriert ist,
        # plane einen Reset
        if not self._is_resetting and self._reset_delay > 0:
            # Cancel any existing reset timer
            if self._reset_timer and self._reset_timer.is_alive():
                self._reset_timer.cancel()
            
            print(f"[DEBUG] Actor {self.pin_name}: Plane Reset in {self._reset_delay} Sekunden")
            self._reset_timer = threading.Timer(self._reset_delay, self._reset_action)
            self._reset_timer.daemon = True
            self._reset_timer.start()