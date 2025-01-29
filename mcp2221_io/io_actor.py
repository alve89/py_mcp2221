# io_actor.py
# Version: 1.6.3

import board
import digitalio
import time
import threading
from typing import Optional, Callable
from .logging_config import logger
from .io_device import IODevice, IOMode

class Actor(IODevice):
    """Repräsentiert einen Actor (Aktor) mit GPIO-Steuerung"""
    def __init__(
        self, 
        pin: str, 
        inverted: bool = False, 
        reset_delay: float = 0.0
    ):
        """
        Initialisiert einen Actor

        :param pin: GPIO-Pin des Actors
        :param inverted: Ob der Zustand invertiert werden soll
        :param reset_delay: Verzögerung für automatische Rückstellung
        """
        super().__init__(pin, inverted)
        
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
            # Wende Invertierung an und setze Pin
            digital_state = self._apply_inversion(state)
            self._digital_pin.value = digital_state
            self._state = state
            
            logger.debug(f"Actor {self._pin} auf {state} gesetzt (Digital: {digital_state})")
            
            # Reset-Mechanismus
            if state and self._reset_delay > 0:
                self._start_reset_timer()
        except Exception as e:
            logger.error(f"Fehler beim Setzen des Actors {self._pin}: {e}")
    
    def _start_reset_timer(self):
        """Startet den Reset-Timer für den Actor"""
        if self._reset_thread and self._reset_thread.is_alive():
            return
        
        def reset_callback():
            try:
                time.sleep(self._reset_delay)
                logger.debug(f"Auto-Reset für Actor {self._pin} nach {self._reset_delay}s")
                
                # Optionaler Callback für spezifische Reset-Logik
                if self.on_reset:
                    self.on_reset()
                else:
                    # Standardmäßig auf False zurücksetzen
                    self.set(False)
            except Exception as e:
                logger.error(f"Fehler beim Reset von Actor {self._pin}: {e}")
        
        self._reset_thread = threading.Thread(target=reset_callback, daemon=True)
        self._reset_thread.start()