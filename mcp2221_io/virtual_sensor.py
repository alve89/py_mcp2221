# virtual_sensor.py
# Version: 2.0.0

from typing import Optional, Callable, Dict, Any
from .io_device import IODevice
from .debug_mixin import DebugMixin
from .logging_config import logger, LogCategory

class VirtualSensor(IODevice, DebugMixin):
    """
    Ein rein virtueller Sensor zur Simulation von Zustandsänderungen,
    ohne physikalischen Zugriff auf GPIO.
    """
    def __init__(self, name: str, inverted: bool = False, debug_config: Dict = {}):
        """
        Initialisiert einen virtuellen Sensor
        
        :param name: Name/ID des Sensors
        :param inverted: Ob der Zustand invertiert werden soll
        :param debug_config: Debug-Konfiguration
        """
        IODevice.__init__(self, pin=name, inverted=inverted)
        self._init_debug_config(debug_config)
        self._state_changed_callback: Optional[Callable[[bool], None]] = None
        self._state: bool = False
        self._name = name

    def set_state(self, new_state: bool):
        """
        Setzt den virtuellen Zustand des Sensors.
        
        :param new_state: Neuer Zustand (True/False)
        """
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            logger.debug(f"{self._name}: {old_state} -> {new_state}", LogCategory.SENSOR)
            self.debug_sensor_state(self._name, "state_changed", f"{old_state} -> {new_state}")
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(self._state)
                except Exception as e:
                    self.debug_sensor_error(self._name, "Fehler im State-Changed-Callback", e)

    def get_state(self) -> bool:
        """
        Gibt den aktuellen Zustand zurück (nicht invertiert).
        
        :return: Aktueller Zustand
        """
        return self._state

    def set_state_changed_callback(self, callback: Optional[Callable[[bool], None]]):
        """
        Setzt den Callback für Zustandsänderungen
        
        :param callback: Funktion, die bei Zustandsänderung aufgerufen wird
        """
        self._state_changed_callback = callback
        logger.debug(f"{self._name} Callback registriert", LogCategory.SENSOR)
        self.debug_sensor_state(self._name, "callback_registered")

    def test_virtual_input(self) -> Dict[str, Any]:
        """
        Liefert einen Diagnose-Datensatz wie beim echten Sensor.
        
        :return: Dictionary mit Diagnoseinformationen
        """
        return {
            "sensor": self._name,
            "type": "virtual",
            "inverted": self._inverted,
            "state": self._state,
            "mqtt_ready": self._state_changed_callback is not None
        }
    
    def test_pin_reading(self) -> Dict[str, Any]:
        """
        Simuliert einen Pin-Lesetest für Kompatibilität mit echten Sensoren
        
        :return: Dictionary mit Diagnoseinformationen
        """
        return {
            "pin": self._name,
            "success": True,
            "raw_value": self._state,
            "inverted": self._inverted,
            "read_state": self._state,
            "current_state": self._state,
            "stable_count": 1,
            "debounce_time": 0,
            "stable_readings": 1,
            "error": None,
            "type": "virtual"
        }
        
    def force_update(self) -> bool:
        """
        Simuliert ein Force-Update für Kompatibilität mit echten Sensoren.
        Bei virtuellen Sensoren ist dies nur ein Passthrough des aktuellen Zustands.
        
        :return: Aktueller Zustand
        """
        logger.info(f"{self._name} - Virtuelles Force-Update angefordert, aktueller Zustand: {self._state}", LogCategory.SENSOR)
        return self._state
        
    def stop_polling(self):
        """
        Kompatible Dummy-Methode für virtuelle Sensoren.
        """
        self.debug_sensor_state(self._name, "virtual_stop_polling", "Kein physischer Sensor – keine Aktion.")