# virtual_sensor.py
# Version: 1.0.0

from typing import Optional, Callable, Dict, Any
from .io_device import IODevice
from .system_debug import SystemDebugMixin
from .logging_config import logger

class VirtualSensor(IODevice, SystemDebugMixin):
    """
    Ein rein virtueller Sensor zur Simulation von Zustandsänderungen,
    ohne physikalischen Zugriff auf GPIO.
    """
    def __init__(self, name: str, inverted: bool = False, debug_config: Dict = {}):
        super().__init__(pin=name, inverted=inverted)
        self._init_system_debug_config(debug_config)
        self._state_changed_callback: Optional[Callable[[bool], None]] = None
        self._state: bool = False
        self._name = name

    def set_state(self, new_state: bool):
        """
        Setzt den virtuellen Zustand des Sensors.
        """
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            logger.debug(f"[VirtualSensor] {self._name}: {old_state} -> {new_state}")
            self.debug_sensor_state(self._name, "state_changed", f"{old_state} -> {new_state}")
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(self._state)
                except Exception as e:
                    self.debug_sensor_error(self._name, "Fehler im State-Changed-Callback", e)

    def get_state(self) -> bool:
        """Gibt den aktuellen Zustand zurück (nicht invertiert)."""
        return self._state

    def set_state_changed_callback(self, callback: Optional[Callable[[bool], None]]):
        self._state_changed_callback = callback
        logger.debug(f"[VirtualSensor] {self._name} Callback registriert")
        self.debug_sensor_state(self._name, "callback_registered")

    def test_virtual_input(self) -> Dict[str, Any]:
        """
        Liefert einen Diagnose-Datensatz wie beim echten Sensor.
        """
        return {
            "sensor": self._name,
            "type": "virtual",
            "inverted": self._inverted,
            "state": self._state,
            "mqtt_ready": self._state_changed_callback is not None
        }
    def stop_polling(self):
        """Kompatible Dummy-Methode für virtuelle Sensoren."""
        self.debug_sensor_state(self._name, "virtual_stop_polling", "Kein physischer Sensor – keine Aktion.")
