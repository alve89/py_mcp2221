import digitalio
import board
from termcolor import colored
from typing import Optional
from mcp2221_io.new_core import get_logger

logger = get_logger()


class IODevice:
    _device_class = ""
    _digital_pin = None
    _gpio_pin = None
    _inverted = False
    _last_state = False
    _name: str = "DefaultIODeviceName"
    _pin = None
    _state: bool = False
    _state_raw: bool = False
    _type: str = None

    def __init__(self, pin: str, type: str, inverted: bool = False, name: str = "No Name Given", device_class: str = ""):
        self._device_class = device_class
        self._inverted = inverted 
        self._name: str = name
        self._pin = pin
        self._state: bool = False
        self._state_raw: bool = False
        self._type: str = type
        
        self._gpio_pin = getattr(board, self._pin)
        self._digital_pin = digitalio.DigitalInOut(self._gpio_pin)

        self._post_init()  # <- Hook wird automatisch aufgerufen


    @property
    def device_class(self) -> str:
        """Gibt die Device-Klasse der Entität zurück"""
        return self._device_class   

    @property
    def name(self) -> str:
        """Gibt den Namen der Entität zurück"""
        return self._name       

    @property
    def pin(self) -> str:
        """Gibt den Pin der Entität zurück"""
        return self._pin

    def _post_init(self):
        """Hook für Kindklassen, kann bei Bedarf überschrieben werden."""
        pass

    def print_state(self):
        # Hier wurde die Änderung vorgenommen: self.state statt self._state verwenden
        current_state = self.state
        color = 'green' if current_state else 'red'
        print(f"Status von {self._name}: " + colored(str(current_state), color))

    def shutdown(self) -> bool:
        self._digital_pin.deinit()
        
        # Klassen-Prüfung ohne direkte Imports
        from mcp2221_io.new_core import logger
        if self.__class__.__name__ == "IOActor":
            logger.info(colored(self.name, 'magenta') + " heruntergefahren.")
        elif self.__class__.__name__ == "IOSensor":
            logger.info(colored(self.name, 'blue') + " heruntergefahren.")
        else:
            print("Shutdown eines generischen IO-Geräts")

    @property
    def state(self) -> bool:
        """Gibt den logischen Zustand der Entität zurück"""
        return self._state

    @property
    def state_raw(self) -> bool:
        """Gibt den physischen Zustand der Entität zurück"""
        return self._state_raw

    @property
    def state_changed(self) -> bool:
        logger.debug(f"Status von {self.name}:")
        logger.debug(f"    - State: {self._state}")
        logger.debug(f"    - Last State: {self._last_state}")
        return True if not self._state == self._last_state else False

    def sync_state(self) -> None:
        """"Speichert den aktuellen physischen Status des Pins in die Variable '_state_raw'"""
        self._state_raw = self._digital_pin.value

        # Speichere den aktuellen logischen Wert als letzten Wert und überschreibe den aktuellen logischen Wert
        self._last_state = self._state
        self._state = not self._state_raw if self._inverted else self._state_raw

    @property
    def type(self) -> str:
        """Gibt den Typ der Entität zurück"""
        return self._type
