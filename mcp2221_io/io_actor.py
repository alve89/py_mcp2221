# io_actor.py
# Version: 1.6.4

import board
import digitalio
import time
import threading
from typing import Optional, Callable, Dict
from mcp2221_io.logging_config import logger
from mcp2221_io.io_device import IODevice, IOMode
from mcp2221_io.system_debug import SystemDebugMixin

class Actor(IODevice, SystemDebugMixin):
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
        :param debug_config: Debug-Konfiguration
        """
        IODevice.__init__(self, pin, inverted)
        self._init_system_debug_config(debug_config)
        
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
            
            self.debug_actor_state(self._pin, "set_state", f"State: {state}, Digital: {digital_state}")
            
            # Reset-Mechanismus
            if state and self._reset_delay > 0:
                self._start_reset_timer()
        except Exception as e:
            self.debug_actor_error(self._pin, "Fehler beim Setzen des Actors", e)
    
    def _start_reset_timer(self):
        """Startet den Reset-Timer für den Actor"""
        if self._reset_thread and self._reset_thread.is_alive():
            return
        
        def reset_callback():
            try:
                time.sleep(self._reset_delay)
                self.debug_actor_state(self._pin, "auto_reset", f"Reset nach {self._reset_delay}s")
                
                # Optionaler Callback für spezifische Reset-Logik
                if self.on_reset:
                    self.on_reset()
                else:
                    # Standardmäßig auf False zurücksetzen
                    self.set(False)
            except Exception as e:
                self.debug_actor_error(self._pin, "Fehler beim Reset", e)
        
        self._reset_thread = threading.Thread(target=reset_callback, daemon=True)
        self._reset_thread.start()
        self.debug_actor_state(self._pin, "reset_timer", f"Reset-Timer gestartet: {self._reset_delay}s")