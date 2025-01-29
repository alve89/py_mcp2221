# io_sensor.py
# Version: 1.6.5

import board
import digitalio
import threading
import time
from typing import Optional, Callable, Dict
from mcp2221_io.logging_config import logger
from mcp2221_io.io_device import IODevice, IOMode
from mcp2221_io.system_debug import SystemDebugMixin

class Sensor(IODevice, SystemDebugMixin):
    """Repräsentiert einen Sensor mit GPIO-Überwachung"""
    def __init__(
        self, 
        pin: str, 
        inverted: bool = False, 
        poll_interval: float = 0.1,
        debug_config: Dict = {}
    ):
        """
        Initialisiert einen Sensor

        :param pin: GPIO-Pin des Sensors
        :param inverted: Ob der Zustand invertiert werden soll
        :param poll_interval: Abtastintervall in Sekunden
        :param debug_config: Debug-Konfiguration
        """
        IODevice.__init__(self, pin, inverted)
        self._init_system_debug_config(debug_config)
        
        # Pin-Konfiguration
        self._gpio_pin = getattr(board, self._pin)
        self._digital_pin = digitalio.DigitalInOut(self._gpio_pin)
        self._digital_pin.direction = digitalio.Direction.INPUT
        
        # Polling-Konfiguration
        self._poll_interval = poll_interval
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_polling = threading.Event()
        
        # State-Change-Callback
        self._state_changed_callback: Optional[Callable[[bool], None]] = None
    
    def start_polling(self):
        """Startet das Polling für den Sensor"""
        if self._poll_thread and self._poll_thread.is_alive():
            return
        
        self._stop_polling.clear()
        self._poll_thread = threading.Thread(target=self._poll_state, daemon=True)
        self._poll_thread.start()
        self.debug_system_process(f"Polling für Sensor {self._pin} gestartet")
    
    def stop_polling(self):
        """Stoppt das Polling für den Sensor"""
        if self._poll_thread and self._poll_thread.is_alive():
            self._stop_polling.set()
            self._poll_thread.join(timeout=1.0)
            self.debug_system_process(f"Polling für Sensor {self._pin} gestoppt")
    
    def _poll_state(self):
        """Kontinuierliche Überwachung des Sensor-Zustands"""
        last_state = None
        while not self._stop_polling.is_set():
            try:
                # Hole aktuellen Zustand
                current_digital_state = self._digital_pin.value
                
                # Debug-Logging für den Raw-Zustand
                self.debug_sensor_state(self._pin, "raw_digital_state", str(current_digital_state))
                
                # Wende Invertierung an
                current_state = not current_digital_state if self._inverted else current_digital_state
                
                # Debug-Logging für den invertierten Zustand
                self.debug_sensor_state(self._pin, "inverted_state", str(current_state))
                
                # Auf State-Change prüfen
                if last_state is None or current_state != last_state:
                    self.debug_sensor_state(self._pin, "state_change", str(current_state))
                    self._state = current_state
                    
                    # Callback aufrufen wenn konfiguriert
                    if self._state_changed_callback:
                        try:
                            self._state_changed_callback(current_state)
                        except Exception as e:
                            self.debug_sensor_error(self._pin, "Fehler im State-Changed-Callback", e)
                    
                    last_state = current_state
                
                # Warte für nächstes Polling
                time.sleep(self._poll_interval)
                
            except Exception as e:
                self.debug_sensor_error(self._pin, "Fehler beim Polling", e)
                # Kurze Pause bei Fehler um Ressourcen zu schonen
                time.sleep(1.0)
    
    def set_state_changed_callback(self, callback: Optional[Callable[[bool], None]]):
        """
        Setzt den Callback für State-Änderungen

        :param callback: Callable mit dem neuen Zustand als Parameter
        """
        self._state_changed_callback = callback