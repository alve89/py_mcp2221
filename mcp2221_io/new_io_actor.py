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




class IOActor(IODevice):
    _state = False
    _auto_reset: float = 0.0
    _toggle_active = False
    _toggle_start_time = 0

    def _post_init(self):
        if self._hw == const.MCP2221:
            self._digital_pin.direction = digitalio.Direction.OUTPUT
            self._digital_pin.value = self._inverted
            self._hw_applied = True
        else:
            return False

        logger.debug("Aktor " + colored(self.name, 'magenta') +" wurde konfiguriert als OUTPUT")
        logger.debug("Pin-Status vor 'sync_state():'")
        logger.debug(f"     Raw-State: {self.state_raw}")
        logger.debug(f"     State: {self.state}")
        logger.debug(f"     Last-State: {self._last_state}")
        self.sync_state()
        logger.debug("Pin-Status nach 'sync_state():'")
        logger.debug(f"     Raw-State: {self.state_raw}")
        logger.debug(f"     State: {self.state}")
        logger.debug(f"     Last-State: {self._last_state}")

    def set_auto_reset(self, seconds: float):
        logger.debug("Auto-Reset für Aktor " + colored(self.name, 'magenta') + f" auf '{seconds}' Sekunden gesetzt.") 
        self._auto_reset = seconds

    def set_state(self, new_state: bool) -> None:
        """Setzt den Zustand des Aktors und den physischen Pin"""
        if self._hw == const.MCP2221:
            if self._digital_pin:                
                self._digital_pin.value = new_state
                logger.debug("Status (logisch) für Aktor " + colored(self.name, 'magenta') + f" auf '{not new_state}' gesetzt.")


    def shutdown(self) -> bool:
        self.turn_off()
        return super().shutdown()


    def turn_on(self):
        self._toggle_active = False  # Abbrechen von vorherigen Toggle-Operationen
        self.set_state(not self._inverted)
        logger.info(colored(self.name, 'magenta') + " eingeschaltet." )

    def turn_off(self):
        self._toggle_active = False  # Abbrechen von vorherigen Toggle-Operationen
        self.set_state(self._inverted)
        logger.info(colored(self.name, 'magenta') + " ausgeschaltet." )


    def toggle(self):
        """Startet einen nicht-blockierenden Toggle-Vorgang"""
        self.turn_on()
        self._toggle_active = True
        self._toggle_start_time = time.monotonic()

    
    def update(self):
        """Muss regelmäßig aufgerufen werden, um den Toggle-Status zu aktualisieren"""
        if self._toggle_active and time.monotonic() - self._toggle_start_time >= self._auto_reset:
            self.turn_off()
            logger.debug("Auto-Reset für Aktor " + colored(self.name, 'magenta') + f" ausgelöst, Aktor zurückgesetzt (neuer Status (logisch): '{self.state}').") 
            self._toggle_active = False
    
    @property
    def toggle_active(self):
        """Gibt zurück, ob ein Toggle-Vorgang aktiv ist"""
        return self._toggle_active