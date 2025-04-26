# io_device.py

from enum import Enum, auto
from typing import Optional, Callable

class IOMode(Enum):
    """Definiert die Betriebsmodi für IO-Geräte"""
    INPUT = auto()
    OUTPUT = auto()
    TOGGLE = auto()

class IODevice:
    def __init__(self, pin: str, inverted: bool = False):
        """
        Initialisiert ein IO-Gerät

        :param pin: GPIO-Pin des Geräts
        :param inverted: Ob der Zustand invertiert werden soll
        """
        self._pin = pin
        self._inverted = inverted
        self._state: bool = False
        self._state_raw: bool = False

    @property
    def pin(self) -> str:
        """Gibt den Pin des Geräts zurück"""
        return self._pin

    @property
    def state(self) -> bool:
        """Gibt den logischen Zustand des Geräts zurück"""
        return not self._state if self._inverted else self._state 
    
    @property
    def state_raw(self) -> bool:
        """Gibt den physischen Zustand des Geräts zurück"""
        return self._state_raw