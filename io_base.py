# io_base.py
# Version: 1.5.2

import os
import time
import threading
from enum import Enum
from .logging_config import logger

import board
import digitalio

class IOMode(Enum):
    """Enumeration für die verschiedenen IO-Modi"""
    SENSOR = 1
    ACTOR = 2

class IODevice:
    """Basisklasse für IO-Geräte (Sensoren und Aktoren)"""
    def __init__(self, pin: str, inverted: bool = False, mode: IOMode = None):
        logger.debug(f"Initialisiere IODevice für Pin {pin}, inverted={inverted}")
        self.pin_name = pin
        self.inverted = inverted
        self.mode = mode
        
        try:
            self.pin = digitalio.DigitalInOut(getattr(board, pin))
            logger.debug(f"GPIO {pin} erfolgreich initialisiert")
        except Exception as e:
            logger.error(f"Fehler bei GPIO-Initialisierung: {e}")
            raise
        
        try:
            if mode == IOMode.SENSOR:
                self.pin.direction = digitalio.Direction.INPUT
                logger.debug(f"Pin {pin} als INPUT konfiguriert")
            elif mode == IOMode.ACTOR:
                self.pin.direction = digitalio.Direction.OUTPUT
                logger.debug(f"Pin {pin} als OUTPUT konfiguriert")
            else:
                raise ValueError("Mode muss SENSOR oder ACTOR sein")
        except Exception as e:
            logger.error(f"Fehler bei Richtungskonfiguration: {e}")
            raise

    def _convert_value(self, value: bool) -> bool:
        """Konvertiert einen Wert entsprechend der Inversionseinstellung"""
        result = not value if self.inverted else value
        logger.debug(f"Wertkonvertierung: {value} -> {result} (inverted={self.inverted})")
        return result

class Sensor(IODevice):
    """Klasse für Sensoren"""
    def __init__(self, pin: str, inverted: bool = False):
        logger.debug(f"Erstelle Sensor an Pin {pin}")
        super().__init__(pin, inverted, IOMode.SENSOR)

    def read(self) -> bool:
        """Liest den aktuellen Zustand des Sensors"""
        raw_value = self.pin.value
        converted_value = self._convert_value(raw_value)
        logger.debug(f"Sensor {self.pin_name} liest: {raw_value} -> {converted_value}")
        return converted_value

class Actor(IODevice):
    """Klasse für Aktoren"""
    def __init__(self, pin: str, inverted: bool = False, reset_delay: float = 0):
        logger.debug(f"Erstelle Actor an Pin {pin}")
        super().__init__(pin, inverted, IOMode.ACTOR)
        self._state = False
        self._reset_delay = reset_delay
        self._reset_timer = None
        self._is_resetting = False  # Flag für Reset-Zustand
        # Initialen Zustand setzen
        self.set(False)
        logger.debug(f"Actor {pin} mit initialem Zustand False erstellt, reset_delay={reset_delay}")

    @property
    def state(self) -> bool:
        return self._state

    def set(self, value: bool):
        """Setzt den Zustand des Aktors"""
        logger.debug(f"Actor {self.pin_name}: Setze logischen Zustand auf {value} (reset_delay={self._reset_delay}, is_resetting={self._is_resetting})")
        self._state = value
        physical_value = self._convert_value(value)
        logger.debug(f"Actor {self.pin_name}: Setze physischen Pin von {self.pin.value} auf {physical_value}")
        try:
            self.pin.value = physical_value
            logger.debug(f"Actor {self.pin_name}: Pin-Wert wurde auf {physical_value} gesetzt")
            
            # Prüfung für Reset-Timer
            logger.debug(f"Actor {self.pin_name}: Prüfe Reset-Timer (value={value}, is_resetting={self._is_resetting}, reset_delay={self._reset_delay})")
            if value and not self._is_resetting and self._reset_delay > 0:
                # Reset-Timer für den Fall, dass der Wert auf True gesetzt wird
                # Bestehenden Timer abbrechen falls vorhanden
                if self._reset_timer and self._reset_timer.is_alive():
                    logger.debug(f"Actor {self.pin_name}: Breche bestehenden Reset-Timer ab")
                    self._reset_timer.cancel()
                
                logger.debug(f"Actor {self.pin_name}: Starte neuen Reset-Timer für {self._reset_delay} Sekunden")
                self._reset_timer = threading.Timer(self._reset_delay, self._reset_action)
                self._reset_timer.daemon = True
                self._reset_timer.start()
            elif not value:
                # Bei Ausschalten eventuell laufenden Timer abbrechen
                if self._reset_timer and self._reset_timer.is_alive():
                    logger.debug(f"Actor {self.pin_name}: Breche geplanten Reset ab wegen value=False")
                    self._reset_timer.cancel()
                    self._reset_timer = None
                
        except Exception as e:
            logger.error(f"Fehler beim Setzen des Pin-Werts: {e}")
            raise

    def _reset_action(self):
        """Interne Methode für den Reset-Vorgang"""
        logger.debug(f"Actor {self.pin_name}: Führe Reset aus")
        self._is_resetting = True
        
        # Physischen Zustand setzen
        physical_value = self._convert_value(False)
        self.pin.value = physical_value
        self._state = False
        logger.debug(f"Actor {self.pin_name}: Reset durchgeführt, Pin = {physical_value}, State = False")
        
        # Reset-Handler aufrufen wenn vorhanden
        if hasattr(self, 'on_reset') and callable(self.on_reset):
            logger.debug(f"Actor {self.pin_name}: Rufe Reset-Handler auf")
            self.on_reset()
            
        self._is_resetting = False
        self._reset_timer = None

    def toggle(self):
        """Wechselt den Zustand des Aktors"""
        logger.debug(f"Actor {self.pin_name}: Toggle von {self._state}")
        self.set(not self._state)