# io_sensor.py
# Version: 1.3.0

import digitalio
from .io_device import IODevice
from .system_debug import SystemDebugMixin
import time

class Sensor(IODevice, SystemDebugMixin):
    def __init__(self, pin, inverted=False, poll_interval=0.1, debug_config=None):
        import board
        super().__init__(pin, inverted)
        self._poll_interval = poll_interval
        self._debounce_time = 0.05
        self._stable_readings = 3
        self._state = False
        self._last_raw = None
        self._stable_count = 0
        self._last_debounce = time.monotonic()
        self._state_changed_callback = None
        self._pin_id = pin
        self._gpio_pin = getattr(board, pin)
        self._digital_pin = digitalio.DigitalInOut(self._gpio_pin)
        self._digital_pin.direction = digitalio.Direction.INPUT
        self._init_system_debug_config(debug_config or {})
        # Stellen wir sicher, dass debug_sensors explizit definiert ist
        self.debug_sensors = debug_config.get("system", {}).get("entities", {}).get("sensors", False)

    def set_debounce_time(self, seconds):
        self._debounce_time = seconds
        self.debug_sensor_state(self._pin_id, "config", f"Debounce-Zeit auf {seconds}s gesetzt")

    def set_stable_readings(self, count):
        self._stable_readings = count
        self.debug_sensor_state(self._pin_id, "config", f"Stabile Lesungen auf {count} gesetzt")

    def set_state_changed_callback(self, callback):
        self._state_changed_callback = callback
        self.debug_sensor_state(self._pin_id, "callback", "State-Changed-Callback registriert")

    def get_raw_state(self):
        """Gibt den aktuellen Rohwert des Sensors zurück (ohne Invertierung oder Debouncing)"""
        try:
            return self._digital_pin.value
        except Exception as e:
            self.debug_sensor_error(self._pin_id, "Fehler beim Lesen des Rohzustands", e)
            return None

    def test_pin_reading(self):
        """Führt einen Test der Pin-Lesung durch und gibt Diagnoseinformationen zurück"""
        try:
            raw_value = self._digital_pin.value
            read_state = not raw_value if self._inverted else raw_value
            result = {
                "pin": self._pin_id,
                "success": True,
                "raw_value": raw_value,
                "inverted": self._inverted,
                "read_state": read_state,
                "current_state": self._state,
                "history": [],
                "stable_count": self._stable_count,
                "error": None,
            }
            self.debug_sensor_state(self._pin_id, "test", f"Pin-Test: Raw={raw_value}, State={read_state}")
            return result
        except Exception as e:
            self.debug_sensor_error(self._pin_id, "Fehler beim Pin-Test", e)
            return {
                "pin": self._pin_id,
                "success": False,
                "error": str(e)
            }

    def sync_poll_once(self):
        """
        Führt eine einzelne Abfrage des Sensors durch.
        
        :return: (raw_value, state) Tuple aus Rohwert und verarbeitetem Zustand
        """
        try:
            raw_value = self._digital_pin.value
            processed_state = self._check_and_update_state(raw_value)
            
            # Verbesserte Debug-Ausgabe
            if self.debug_sensors:
                state_str = "ON" if processed_state else "OFF"
                raw_str = "HIGH" if raw_value else "LOW"
                self.debug_sensor_state(
                    self._pin_id, 
                    "poll", 
                    f"Raw={raw_str}, State={state_str}, Stabil={self._stable_count}/{self._stable_readings}"
                )
                
            return raw_value, processed_state
        except Exception as e:
            self.debug_sensor_error(self._pin_id, "Fehler beim Polling", e)
            # Bei Fehler den letzten bekannten Zustand beibehalten
            return None, self._state

    def _check_and_update_state(self, raw_value):
        """
        Überprüft und aktualisiert den Zustand basierend auf dem Rohwert.
        
        Implementiert Debouncing und stabile Lesungen.
        
        :param raw_value: Der Rohwert vom Pin
        :return: Der aktuelle Zustand (möglicherweise aktualisiert)
        """
        # Konvertiere den Rohwert unter Berücksichtigung der Invertierung
        read_state = not raw_value if self._inverted else raw_value
        now = time.monotonic()

        if self._last_raw is None:
            # Erste Lesung
            self._last_debounce = now
            self._last_raw = read_state
            self._stable_count = 1
            self.debug_sensor_state(self._pin_id, "init", f"Erste Lesung: {read_state}")
        elif read_state != self._last_raw:
            # Zustandsänderung - Debounce-Timer zurücksetzen
            self._last_debounce = now
            self._last_raw = read_state
            self._stable_count = 1
            self.debug_sensor_state(self._pin_id, "change", f"Zustandsänderung: {self._state} -> {read_state}")
        elif now - self._last_debounce >= self._debounce_time:
            # Zustand ist stabil für Debounce-Zeit - Zähler erhöhen
            self._stable_count += 1
            
            if self.debug_sensors:
                self.debug_sensor_state(
                    self._pin_id, 
                    "stable", 
                    f"Stabile Lesung {self._stable_count}/{self._stable_readings}"
                )

        # Wenn genügend stabile Lesungen und der Zustand sich geändert hat
        if self._stable_count >= self._stable_readings and read_state != self._state:
            old_state = self._state
            self._state = read_state
            
            if self.debug_sensors:
                self.debug_sensor_state(
                    self._pin_id, 
                    "state_changed", 
                    f"Zustandsänderung bestätigt: {old_state} -> {self._state}"
                )
                
            # Callback aufrufen, wenn vorhanden
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(self._state)
                    self.debug_sensor_state(self._pin_id, "callback", "State-Changed-Callback ausgeführt")
                except Exception as e:
                    self.debug_sensor_error(self._pin_id, "Fehler im State-Changed-Callback", e)

        return self._state