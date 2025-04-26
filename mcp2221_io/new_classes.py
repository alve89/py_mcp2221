# mcp2221_io/new_classes.py

import os
import time
import yaml
import digitalio
import board
import logging
import json
from termcolor import colored
from typing import Dict, List, Optional, Any

# Singleton-Instanzen
config = None
logger = None

def get_config():
    """Gibt die globale Config-Instanz zurück oder erstellt sie, wenn sie nicht existiert."""
    global config
    if config is None:
        # Korrigierter Konfigurationspfad
        current_dir = os.path.dirname(os.path.abspath(__file__))  # /usr/local/bin/mcp2221_io/
        config_path = os.path.join(current_dir, "..", "config.yaml")  # Ein Verzeichnis nach oben
        config = Config(config_path)
    return config

def get_logger():
    """Gibt die globale Logger-Instanz zurück oder erstellt sie, wenn sie nicht existiert."""
    global logger
    if logger is None:
        # Standard-Logging-Level aus Config
        debug_level = config.get_value("logging.level", "WARNING")
        logger = Logger(debug_level).get_logger()
    return logger

class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self) -> bool:
        """Lädt die Konfiguration aus der YAML-Datei."""
        try:
            with open(self.config_path, 'r') as file:
                self.config = yaml.safe_load(file)
            print(f"Konfiguration aus {self.config_path} erfolgreich geladen.")
            return True
        except Exception as e:
            print(f"Fehler beim Laden der Konfiguration: {e}")
            return False
    
    def get_value(self, path: str, default: Any = None) -> Any:
        """Greift auf einen verschachtelten Wert mit Punktnotation zu.
        Beispiel: get_nested_value("debugging.mqtt.process")
        """
        keys = path.split(".")
        current = self.config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def get_config(self):
        return self.config
    
    # Diese Methoden ermöglichen den direkten Zugriff wie auf ein Dictionary
    def __getitem__(self, key):
        """Ermöglicht den direkten Zugriff auf die Konfiguration mit config['key']"""
        return self.config[key]
    
    def __contains__(self, key):
        """Ermöglicht die Verwendung von 'key in config'"""
        return key in self.config
    
    def __iter__(self):
        """Ermöglicht die Iteration über die Konfiguration"""
        return iter(self.config)
    
    def keys(self):
        """Gibt die Schlüssel der Konfiguration zurück"""
        return self.config.keys()
    
    def items(self):
        """Gibt die Schlüssel-Wert-Paare der Konfiguration zurück"""
        return self.config.items()
config = get_config()

class Logger:
    def __init__(self, level: str = "WARNING"):
        # String zu logging-Level konvertieren
        log_level = getattr(logging, level)
            
        # Logger konfigurieren
        self.logger = logging.getLogger("MCP2221")
        self.logger.setLevel(log_level)
        
        # Vorhandene Handler entfernen, um Doppelausgaben zu vermeiden
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Handler erstellen
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # Formatierung hinzufügen
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        
        # Handler zum Logger hinzufügen
        self.logger.addHandler(console_handler)

        self.logger.info("Logging initialisiert und konfiguriert.")
        
    def get_logger(self):
        return self.logger
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
        
        # Prüfen, ob die aktuelle Instanz ein IOActor ist
        if isinstance(self, IOActor):
            logger.info(colored(self.name, 'magenta') + " heruntergefahren." )
        elif isinstance(self, IOSensor):
            logger.info(colored(self.name, 'blue') + " heruntergefahren." )
        else:
            print("Shutdown eines generischen IO-Geräts")

    @property
    def state(self) -> bool:
        """Gibt den logischen Zustand der Entität zurück"""
        self._last_state = self._state
        self._state = not self._state_raw if self._inverted else self._state_raw
        return self._state

    @property
    def state_raw(self) -> bool:
        """Gibt den physischen Zustand der Entität zurück"""
        return self._state_raw

    @property
    def state_changed(self) -> bool:
        return True if not self._state == self._last_state else False

    def sync_state(self) -> bool:
        self._state_raw = self._digital_pin.value

    @property
    def type(self) -> str:
        """Gibt den Typ der Entität zurück"""
        return self._type

class IOActor(IODevice):
    _state = False
    _auto_reset: float = 0.0
    _toggle_active = False
    _toggle_start_time = 0

    def _post_init(self):
        self._digital_pin.direction = digitalio.Direction.OUTPUT
        self._digital_pin.value = self._inverted
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
        if self._digital_pin:
            logger.debug("Status (logisch) für Aktor " + colored(self.name, 'magenta') + f" auf '{not new_state}' gesetzt.") 
            self._digital_pin.value = new_state
            self.sync_state()

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
        self._digital_pin.direction = digitalio.Direction.INPUT
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

class IOController:
    """Controller zur Verwaltung von IO-Geräten basierend auf YAML-Konfiguration."""
    
    def __init__(self):
        logger.info("IOController wird initialisiert.")
        self.actors = {}  # Speichert alle Aktoren nach Namen
        self.sensors = {}  # Speichert alle Sensoren nach Namen
        self.running = False        
        
    def setup_entities(self) -> bool:
        """Erstellt alle Geräte basierend auf der geladenen Konfiguration."""
        try:
            logger.info("Entitäten werden erstellt.")

            # Sensoren erstellen
            if 'sensors' in config:
                for sensor_id, sensor_config in config['sensors'].items():
                    if sensor_config.get('entity_type') == 'binary_sensor':
                        logger.debug(f"Entität {sensor_id} ist ein Sensor vom Typ {sensor_config.get('entity_type')}")
                        self._create_binary_sensor(sensor_id, sensor_config)
            
            # Aktoren erstellen
            if 'actors' in config:
                for actor_id, actor_config in config['actors'].items():
                    if actor_config.get('entity_type') == 'switch':
                        logger.debug(f"Entität {actor_id} ist ein Sensor vom Typ {actor_config.get('entity_type')}")
                        self._create_switch(actor_id, actor_config)
            
            logger.info(f"Geräte erfolgreich eingerichtet: {len(self.sensors)} Sensoren, {len(self.actors)} Aktoren")
            return True
        except Exception as e:
            print(f"Fehler beim Einrichten der Geräte: {e}")
            return False
    
    def _create_binary_sensor(self, sensor_id: str, config: Dict[str, Any]) -> None:
        """Erstellt einen binären Sensor basierend auf der Konfiguration."""
        sensor = IOSensor(
            pin=config['pin'],
            type=config['entity_type'],
            inverted=config.get('inverted', False),
            name=sensor_id,
            device_class=config.get('device_class', '')
        )
        
        # Zusätzliche Konfigurationen anwenden
        if 'poll_interval' in config:
            sensor.set_poll_interval(float(config['poll_interval']))
        if 'debounce_time' in config:
            sensor.set_debounce_time(float(config['debounce_time']))
        if 'stable_readings' in config:
            sensor.set_stable_readings(int(config['stable_readings']))
        
        self.sensors[sensor_id] = sensor
        logger.info(f"Sensor '{sensor_id}' erstellt (Pin: {config['pin']})")
    
    def _create_switch(self, actor_id: str, config: Dict[str, Any]) -> None:
        """Erstellt einen Schalter basierend auf der Konfiguration."""
        actor = IOActor(
            pin=config['pin'],
            type=config['entity_type'],
            inverted=config.get('inverted', False),
            name=actor_id,
            device_class=config.get('device_class', '')
        )
        
        # Automatische Rückstellung konfigurieren
        if config.get('auto_reset', False) and 'reset_delay' in config:
            actor.set_auto_reset(float(config['reset_delay']))
        
        # Initialen Zustand setzen
        if config.get('startup_state') == 'on':
            actor.turn_on()
        else:
            actor.turn_off()
            
        self.actors[actor_id] = actor
        logger.info(f"Aktor '{actor_id}' erstellt (Pin: {config['pin']})")
    
    def start(self) -> bool:
        """Startet den Controller und initialisiert alle Geräte."""
        # if not self.load_config():
        #     return False
        
        if not self.setup_entities():
            return False
        
        self.running = True
        logger.info("IOController erfolgreich gestartet.")
        return True
    
    def stop(self) -> None:
        """Stoppt den Controller und gibt alle Ressourcen frei."""
        self.running = False
        # Alle Aktoren herunterfahren
        for actor_id, actor in self.actors.items():
            actor.shutdown()
        
        # Alle Sensoren herunterfahren
        for sensor_id, sensor in self.sensors.items():
            sensor.shutdown()
        
        logger.info("IOController gestoppt.")
    
    # Rest der Methoden bleibt unverändert...
    def update(self) -> None:
        """Aktualisiert alle Geräte - sollte in einer Schleife aufgerufen werden."""
        if not self.running:
            return
        
        self.check_state_change()

        # Aktoren aktualisieren
        for actor in self.actors.values():
            actor.update()
        
        # Sensoren aktualisieren
        for sensor in self.sensors.values():
            sensor.sync_state()
    
    def check_state_change(self):
        # Aktoren auf geänderten Status prüfen
        for actor_id, actor in self.actors.items():
            if actor.state_changed:
                # MQTT-Nachricht
                logger.info(f"Aktor {actor_id} hat seinen Wert geändert, aktueller Wert: {actor.state}")
        
        # Sensoren auf geänderten Status prüfen
        for sensor_id, sensor in self.sensors.items():
            if sensor.state_changed:
                # MQTT-Nachricht
                logger.info(f"Sensor {sensor_id} hat seinen Wert geändert, aktueller Wert: {sensor.state}")


    def get_actor(self, actor_id: str) -> Optional[IOActor]:
        """Gibt den Aktor mit der angegebenen ID zurück."""
        return self.actors.get(actor_id)
    
    def get_sensor(self, sensor_id: str) -> Optional[IOSensor]:
        """Gibt den Sensor mit der angegebenen ID zurück."""
        return self.sensors.get(sensor_id)
    
    def print_all_states(self) -> None:
        """Gibt den Status aller Geräte aus."""
        print("\n--- Aktueller Gerätestatus ---")
        for sensor_id, sensor in self.sensors.items():
            sensor.print_state()
        
        for actor_id, actor in self.actors.items():
            actor.print_state()
            if isinstance(actor, IOActor) and hasattr(actor, 'toggle_active'):
                print(f"  Toggle aktiv: {actor.toggle_active}")
        print("-----------------------------\n")


