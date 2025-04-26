# io_sensor.py
# Version: 2.0.0

import digitalio
import time
from typing import Optional, Callable, Dict, Any, Tuple

from .io_device import IODevice
from .debug_mixin import DebugMixin
from .logging_config import logger, LogCategory

class Sensor(IODevice, DebugMixin):
    """Repräsentiert einen Sensor mit GPIO-Eingang"""
    
    def __init__(
        self, 
        pin: str, 
        inverted: bool = False, 
        poll_interval: float = 0.1, 
        debug_config: Dict = None,
        name: str = None
    ):
        """
        Initialisiert einen Sensor
        
        :param pin: GPIO-Pin des Sensors
        :param inverted: Ob der Zustand invertiert werden soll
        :param poll_interval: Abtastintervall in Sekunden
        :param debug_config: Debug-Konfiguration
        :param name: Optionaler Name/ID für den Sensor
        """
        import board
        IODevice.__init__(self, pin, inverted)
        self._init_debug_config(debug_config or {})
        
        # Konfiguration
        self._poll_interval = poll_interval
        self._debounce_time = 0.05
        self._stable_readings = 3
        
        # Zustand
        self._state = False
        self._last_raw = None
        self._stable_count = 0
        self._last_debounce = time.monotonic()
        self._state_changed_callback = None
        
        # GPIO-Konfiguration
        self._pin_id = pin
        self._sensor_name = name or pin  # Verwende den Namen, falls angegeben, sonst Pin
        self._gpio_pin = getattr(board, pin)
        self._digital_pin = digitalio.DigitalInOut(self._gpio_pin)
        self._digital_pin.direction = digitalio.Direction.INPUT

    def set_debounce_time(self, seconds: float):
        """
        Setzt die Entprellzeit für den Sensor
        
        :param seconds: Entprellzeit in Sekunden
        """
        self._debounce_time = seconds
        self.debug_sensor_state(self._pin_id, "config", f"Debounce-Zeit auf {seconds}s gesetzt")

    def set_stable_readings(self, count: int):
        """
        Setzt die Anzahl stabiler Lesungen für Zustandsänderungen
        
        :param count: Anzahl der benötigten stabilen Lesungen
        """
        self._stable_readings = count
        self.debug_sensor_state(self._pin_id, "config", f"Stabile Lesungen auf {count} gesetzt")

    def set_state_changed_callback(self, callback: Callable[[bool], None]):
        """
        Setzt den Callback für Zustandsänderungen
        
        :param callback: Funktion, die bei Zustandsänderung aufgerufen wird
        """
        self._state_changed_callback = callback
        self.debug_sensor_state(self._pin_id, "callback", "State-Changed-Callback registriert")

    def get_raw_state(self) -> Optional[bool]:
        """
        Gibt den aktuellen Rohwert des Sensors zurück (ohne Invertierung oder Debouncing)
        
        :return: Rohwert (True/False) oder None bei Fehler
        """
        try:
            return self._digital_pin.value
        except Exception as e:
            self.debug_sensor_error(self._pin_id, "Fehler beim Lesen des Rohzustands", e)
            return None

    def test_pin_reading(self) -> Dict[str, Any]:
        """
        Führt einen Test der Pin-Lesung durch und gibt Diagnoseinformationen zurück
        
        :return: Dictionary mit Diagnoseinformationen
        """
        try:
            raw_value = self._digital_pin.value
            read_state = not raw_value if self._inverted else raw_value
            result = {
                "pin": self._pin_id,
                "name": self._sensor_name,
                "success": True,
                "raw_value": raw_value,
                "inverted": self._inverted,
                "read_state": read_state,
                "current_state": self._state,
                "stable_count": self._stable_count,
                "debounce_time": self._debounce_time,
                "stable_readings": self._stable_readings,
                "error": None,
            }
            self.debug_sensor_state(self._sensor_name, "test", f"Pin-Test: Raw={raw_value}, State={read_state}")
            
            # Detaillierte Diagnose-Ausgabe für bessere Fehlersuche mit Sensor-Name und Pin
            logger.info(f"{self._sensor_name} (Pin: {self._pin_id}): Raw={raw_value}, Inverted={self._inverted}, "
                       f"Read={read_state}, Current={self._state}, Stable={self._stable_count}/{self._stable_readings}", 
                       LogCategory.SENSOR)
            
            return result
        except Exception as e:
            self.debug_sensor_error(self._sensor_name, "Fehler beim Pin-Test", e)
            return {
                "pin": self._pin_id,
                "name": self._sensor_name,
                "success": False,
                "error": str(e)
            }

    

    def sync_poll_once(self) -> Tuple[Optional[bool], bool]:
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
                    self._sensor_name, 
                    "poll", 
                    f"Raw={raw_str}, State={state_str}, Stabil={self._stable_count}/{self._stable_readings}"
                )
                
            return raw_value, processed_state
        except Exception as e:
            self.debug_sensor_error(self._sensor_name, "Fehler beim Polling", e)
            # Bei Fehler den letzten bekannten Zustand beibehalten
            return None, self._state

    def _check_and_update_state(self, raw_value: bool) -> bool:
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
            self.debug_sensor_state(self._sensor_name, "init", f"Erste Lesung: {read_state}")
            logger.info(f"{self._sensor_name} - Erste Lesung: Raw={raw_value}, Read={read_state}", LogCategory.SENSOR)
        elif read_state != self._last_raw:
            # Zustandsänderung - Debounce-Timer zurücksetzen
            self._last_debounce = now
            self._last_raw = read_state
            self._stable_count = 1
            self.debug_sensor_state(self._sensor_name, "change", f"Zustandsänderung: {self._state} -> {read_state}")
            logger.info(f"{self._sensor_name} - Zustandsänderung erkannt: {self._state} -> {read_state}, Debounce-Timer zurückgesetzt", LogCategory.SENSOR)
        elif now - self._last_debounce >= self._debounce_time:
            # Zustand ist stabil für Debounce-Zeit - Zähler erhöhen
            self._stable_count += 1
            
            if self.debug_sensors:
                self.debug_sensor_state(
                    self._sensor_name, 
                    "stable", 
                    f"Stabile Lesung {self._stable_count}/{self._stable_readings}"
                )
            
            # Zusätzliches INFO-Logging, wenn wir uns dem Schwellenwert nähern
            if self._stable_count >= self._stable_readings - 1:
                logger.info(f"{self._sensor_name} - Fast stabile Lesung: {self._stable_count}/{self._stable_readings}, "
                           f"Aktueller Zustand={self._state}, Neuer Zustand={read_state}", LogCategory.SENSOR)

        # Wenn genügend stabile Lesungen und der Zustand sich geändert hat
        if self._stable_count >= self._stable_readings and read_state != self._state:
            old_state = self._state
            self._state = read_state
            
            if self.debug_sensors:
                self.debug_sensor_state(
                    self._sensor_name, 
                    "state_changed", 
                    f"Zustandsänderung bestätigt: {old_state} -> {self._state}"
                )
            
            # Explizites Logging bei Zustandsänderung
            logger.info(f"{self._sensor_name} - Zustandsänderung BESTÄTIGT: {old_state} -> {self._state} "
                       f"nach {self._stable_count} stabilen Lesungen", LogCategory.SENSOR)
                
            # Callback aufrufen, wenn vorhanden
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(self._state)
                    self.debug_sensor_state(self._sensor_name, "callback", "State-Changed-Callback ausgeführt")
                    logger.info(f"{self._sensor_name} - State-Changed-Callback ausgeführt mit Wert {self._state}", LogCategory.SENSOR)
                except Exception as e:
                    self.debug_sensor_error(self._sensor_name, "Fehler im State-Changed-Callback", e)
                    logger.error(f"{self._sensor_name} - Fehler im State-Changed-Callback: {e}", LogCategory.SENSOR)

        return self._state

    def force_update(self) -> bool:
        """
        Erzwingt eine sofortige Aktualisierung des Sensor-Zustands ohne Debouncing.
        Dies kann hilfreich sein, um den Zustand ohne Verzögerung zu aktualisieren,
        z.B. bei Systemstart oder Reset.
        
        :return: Der aktuelle Zustand nach dem Update
        """
        try:
            raw_value = self._digital_pin.value
            read_state = not raw_value if self._inverted else raw_value
            old_state = self._state
            
            # Zustand direkt aktualisieren ohne Debouncing
            self._state = read_state
            self._last_raw = read_state
            self._stable_count = self._stable_readings  # Als stabil markieren
            
            logger.info(f"{self._sensor_name} - Erzwungene Aktualisierung: Raw={raw_value}, "
                       f"Zustand von {old_state} auf {self._state} gesetzt", LogCategory.SENSOR)
            
            # Callback aufrufen, wenn vorhanden und sich der Zustand geändert hat
            if self._state_changed_callback and old_state != self._state:
                try:
                    self._state_changed_callback(self._state)
                    logger.info(f"{self._sensor_name} - State-Changed-Callback nach erzwungener Aktualisierung ausgeführt", LogCategory.SENSOR)
                except Exception as e:
                    logger.error(f"{self._sensor_name} - Fehler im State-Changed-Callback bei erzwungener Aktualisierung: {e}", LogCategory.SENSOR)
            
            return self._state
        except Exception as e:
            logger.error(f"{self._sensor_name} - Fehler bei erzwungener Aktualisierung: {e}", LogCategory.SENSOR)
            return self._state