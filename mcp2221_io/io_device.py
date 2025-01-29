# io_device.py
# Version: 1.6.3

from enum import Enum, auto
from typing import Optional, Callable

class IOMode(Enum):
    """Definiert die Betriebsmodi für IO-Geräte"""
    INPUT = auto()
    OUTPUT = auto()
    TOGGLE = auto()

class IODevice:
    """Basisklasse für alle IO-Geräte"""
    def __init__(self, pin: str, inverted: bool = False):
        """
        Initialisiert ein IO-Gerät

        :param pin: GPIO-Pin des Geräts
        :param inverted: Ob der Zustand invertiert werden soll
        """
        self._pin = pin
        self._inverted = inverted
        self._state: bool = False
        
    @property
    def pin(self) -> str:
        """Gibt den Pin des Geräts zurück"""
        return self._pin
    
    @property
    def state(self) -> bool:
        """Gibt den aktuellen Zustand des Geräts zurück"""
        return self._state
    
    def _apply_inversion(self, value: bool) -> bool:
        """
        Wendet Invertierung auf den Wert an
        
        :param value: Ursprünglicher Wert
        :return: Möglicherweise invertierter Wert
        """
        return not value if self._inverted else value