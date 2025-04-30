import mcp2221_io.const as const

import time
from termcolor import colored
# import digitalio
from typing import Optional
from mcp2221_io.new_core import get_logger
from mcp2221_io.new_io_device import IODevice

# Hardware-spezifische Importe
if const.HW == const.MCP2221:
    import digitalio
    import board
elif const.HW == const.FT232H:
    # Hier könnten FT232H-spezifische Importe erfolgen
    # z.B. import adafruit_blinka
    pass


logger = get_logger()


class IOSensor(IODevice):
    # Konfiguration
    _poll_interval = 0.1
    _debounce_time = 0.05
    _stable_readings = 1
    
    # Zustand
    _state = False
    _last_raw = None
    _stable_count = 0
    _last_debounce = time.monotonic()

    def _post_init(self):
        if self._hw == const.MCP2221:
            self._digital_pin.direction = digitalio.Direction.INPUT
            self._hw_applied = True
        else:
            return False

        logger.debug(f"Sensor " + colored(self.name, 'blue') +" wurde konfiguriert als INPUT")
        logger.debug("Pin-Status vor 'sync_state():'")
        logger.debug(f"     Raw-State: {self.state_raw}")
        logger.debug(f"     State: {self.state}")
        logger.debug(f"     Last-State: {self._last_state}")
        self.sync_state()
        logger.debug("Pin-Status nach 'sync_state():'")
        logger.debug(f"     Raw-State: {self.state_raw}")
        logger.debug(f"     State: {self.state}")
        logger.debug(f"     Last-State: {self._last_state}")

    def set_debounce_time(self, new_time: float):
        """"Setzt Entprell-Zeit des Sensors"""
        self._debounce_time = new_time

    def set_stable_readings(self, new_number: int):  # Typ von float zu int geändert
        """"Setzt die Anzahl der benötigten Stable-Readings des Sensors"""
        self._stable_readings = new_number

    def set_poll_interval(self, new_interval: float):
        """"Setzt das Poll-Intervall des Sensors"""
        self._poll_interval = new_interval
        
    @property
    def poll_interval(self):
        """"Gibt das Poll-Intervall des Sensors zurück"""
        return self._poll_interval
    
    @property
    def debounce_time(self):
        """"Gibt die Entprell-Zeit des Sensors zurück"""
        return self._debounce_time
    
    @property
    def stable_readings(self):
        """"Gibt die Anzahl der Abfragen zurück, die ein stabiles Ergebnis liefern, die nötig sind, damit der Sensor einen State-Change meldet"""
        return self._stable_readings