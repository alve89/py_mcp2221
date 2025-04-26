# io_actor.py
# Version: 2.0.0

import board
import digitalio
import time
import threading
from typing import Optional, Callable, Dict, Any

from .logging_config import logger, LogCategory
from .io_device import IODevice
from .debug_mixin import DebugMixin

class Actor(IODevice, DebugMixin):
    """Repräsentiert einen Actor (Aktor) mit GPIO-Steuerung"""

    def __init__(
        self, 
        pin: str, 
        inverted: bool = False, 
        reset_delay: float = 0.0,
        debug_config: Dict = {}
    ):
        """
        Initialisiert einen Actor

        :param pin: GPIO-Pin des Actors
        :param inverted: Ob der Zustand invertiert werden soll
        :param reset_delay: Verzögerung für automatische Rückstellung
        :param debug_config: Debug-Konfiguration (aus config.yaml)
        """
        IODevice.__init__(self, pin, inverted)
        self._init_debug_config(debug_config)

        # Pin-Konfiguration
        self._gpio_pin = getattr(board, self._pin)
        self._digital_pin = digitalio.DigitalInOut(self._gpio_pin)
        self._digital_pin.direction = digitalio.Direction.OUTPUT

        # Reset-Konfiguration
        self._reset_delay = reset_delay
        self._reset_thread: Optional[threading.Thread] = None
        self.on_reset: Optional[Callable[[], None]] = None

        # Initialer Zustand
        self.set(False)

    def set(self, state: bool):
        """
        Setzt den Zustand des Actors

        :param state: Neuer Zustand (True/False)
        """
        try:
            digital_state = self._apply_inversion(state)
            self._digital_pin.value = digital_state
            self._state = state

            if self.debug_actors:
                logger.debug(f"Pin {self._pin} → gesetzt auf {'ON' if state else 'OFF'} (digital: {digital_state})", 
                           LogCategory.ACTOR)

            if state and self._reset_delay > 0:
                self._start_reset_timer()
        except Exception as e:
            if self.debug_actors:
                logger.error(f"Fehler beim Setzen von Pin {self._pin}: {e}", LogCategory.ACTOR)

    def _start_reset_timer(self):
        """Startet den Reset-Timer für den Actor"""
        if self._reset_thread and self._reset_thread.is_alive():
            return

        def reset_callback():
            try:
                if self.debug_actors:
                    logger.debug(f"Pin {self._pin} → Auto-Reset startet in {self._reset_delay} Sekunden", LogCategory.ACTOR)
                time.sleep(self._reset_delay)
                if self.on_reset:
                    self.on_reset()
                else:
                    self.set(False)
                if self.debug_actors:
                    logger.info(f"Pin {self._pin} wurde automatisch zurückgesetzt", LogCategory.ACTOR)
            except Exception as e:
                if self.debug_actors:
                    logger.error(f"Fehler beim Auto-Reset von Pin {self._pin}: {e}", LogCategory.ACTOR)

        self._reset_thread = threading.Thread(target=reset_callback, daemon=True)
        self._reset_thread.start()

        if self.debug_actors:
            logger.debug(f"Pin {self._pin} → Reset-Timer gestartet: {self._reset_delay}s", LogCategory.ACTOR)