# logging_config.py
# Version: 2.0.0

import logging
import sys
import os
from enum import Enum
from typing import Optional, Dict, Any, Union

class LogLevel(Enum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    NONE = logging.CRITICAL + 10

class LogCategory:
    """Log-Kategorien für einheitliches Logging"""
    SYSTEM = "System"
    MQTT = "MQTT"
    ACTOR = "Actor"
    SENSOR = "Sensor"
    COVER = "Cover"
    GPIO = "GPIO"
    ERROR = "Error"

class LogFormatter(logging.Formatter):
    """Einheitlicher Formatter für verschiedene Log-Level"""
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        self.debug_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        self.info_fmt = '%(message)s'  # Vereinfachtes Format für INFO-Level
        super().__init__(self.debug_fmt)
        
    def format(self, record):
        # Im Debug-Modus immer ausführliches Format
        if self.debug_mode:
            self._style._fmt = self.debug_fmt
            return super().format(record)
        
        # Im Normal-Modus vereinfachtes Format für INFO
        if record.levelno == logging.INFO:
            self._style._fmt = self.info_fmt
        else:
            self._style._fmt = self.debug_fmt
            
        return super().format(record)

class Logger:
    """Zentralisierte Logger-Klasse für einheitliches Logging"""
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'Logger':
        """Singleton-Instanz zurückgeben"""
        if cls._instance is None:
            cls._instance = Logger()
        return cls._instance
    
    def __init__(self):
        """Logger initialisieren"""
        self.logger = logging.getLogger('mcp2221_io')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []  # Alle Handler entfernen
        
        # Debug-Modus aus Umgebungsvariable
        self.debug_mode = os.environ.get('MCP2221_DEBUG', '0') == '1'
        
        # Handler für Stdout
        self.console_handler = logging.StreamHandler(sys.stdout)
        self.console_handler.setLevel(logging.DEBUG)
        
        # Formatter basierend auf Debug-Modus
        self.formatter = LogFormatter(debug_mode=self.debug_mode)
        self.console_handler.setFormatter(self.formatter)
        
        # Filter für nicht-Debug-Modus
        if not self.debug_mode:
            class LogFilter(logging.Filter):
                def filter(self, record):
                    # Im Nicht-Debug-Modus bestimmte DEBUG-Nachrichten filtern
                    if record.levelno <= logging.DEBUG:
                        return False
                    return True
            
            # Filter nur im Nicht-Debug-Modus aktivieren
            # self.console_handler.addFilter(LogFilter())
        
        self.logger.addHandler(self.console_handler)
    
    def set_level(self, level: Union[str, int, LogLevel]):
        """Log-Level setzen"""
        if isinstance(level, str):
            level = LogLevel[level.upper()].value
        elif isinstance(level, LogLevel):
            level = level.value
            
        self.logger.setLevel(level)
        self.console_handler.setLevel(level)
    
    def debug(self, message: str, category: str = LogCategory.SYSTEM, entity_id: str = None):
        """Debug-Log mit Kategorie"""
        self._log(logging.DEBUG, message, category, entity_id)
    
    def info(self, message: str, category: str = LogCategory.SYSTEM, entity_id: str = None):
        """Info-Log mit Kategorie"""
        self._log(logging.INFO, message, category, entity_id)
    
    def warning(self, message: str, category: str = LogCategory.SYSTEM, entity_id: str = None):
        """Warning-Log mit Kategorie"""
        self._log(logging.WARNING, message, category, entity_id)
    
    def error(self, message: str, category: str = LogCategory.ERROR, entity_id: str = None, 
              exception: Exception = None):
        """Error-Log mit Kategorie und optionaler Exception"""
        if exception:
            self._log(logging.ERROR, f"{message}: {str(exception)}", category, entity_id)
        else:
            self._log(logging.ERROR, message, category, entity_id)
    
    def critical(self, message: str, category: str = LogCategory.ERROR, entity_id: str = None, 
                exception: Exception = None):
        """Critical-Log mit Kategorie und optionaler Exception"""
        if exception:
            self._log(logging.CRITICAL, f"{message}: {str(exception)}", category, entity_id)
        else:
            self._log(logging.CRITICAL, message, category, entity_id)
    
    def _log(self, level: int, message: str, category: str, entity_id: str = None):
        """Internes Logging mit Kategorie und Entity-ID"""
        prefix = f"[{category}]"
        if entity_id:
            prefix = f"{prefix} {entity_id}"
        self.logger.log(level, f"{prefix} {message}")
    
    def set_debug_mode(self, enabled: bool = True):
        """Debug-Modus aktivieren/deaktivieren"""
        self.debug_mode = enabled
        os.environ['MCP2221_DEBUG'] = '1' if enabled else '0'
        
        # Formatter aktualisieren
        self.formatter = LogFormatter(debug_mode=self.debug_mode)
        self.console_handler.setFormatter(self.formatter)
        
        # Debug-Ausgabe
        mode = "aktiviert" if enabled else "deaktiviert"
        self.info(f"Debug-Modus {mode}", LogCategory.SYSTEM)

class DebugMixin:
    """Basis-Mixin für einheitliches Debugging in allen Komponenten"""
    
    def _init_debug_config(self, config: Dict[str, Any]):
        """Debugging-Konfiguration initialisieren"""
        self._debug_config = config.get('debugging', {})
        
        # Debug-Modi für verschiedene Kategorien
        debug_system = self._debug_config.get('system', {})
        self._debug_process = debug_system.get('process', False)
        
        debug_entities = debug_system.get('entities', {})
        self._debug_actors = debug_entities.get('actors', False)
        self._debug_sensors = debug_entities.get('sensors', False)
        
        # MQTT-Debug-Konfiguration
        debug_mqtt = self._debug_config.get('mqtt', {})
        self._debug_mqtt_process = debug_mqtt.get('process', False)
        self._debug_mqtt_send = debug_mqtt.get('send', False)
        self._debug_mqtt_receive = debug_mqtt.get('receive', False)
        
        # GPIO-Debug-Konfiguration
        self._debug_gpio = self._debug_config.get('gpio', False)
        
        # Debug-Modus aus Umgebungsvariable
        self._global_debug_mode = os.environ.get('MCP2221_DEBUG', '0') == '1'
    
    def debug_system(self, message: str, entity_id: Optional[str] = None):
        """System-Debug-Ausgabe"""
        if self._debug_process or self._global_debug_mode:
            Logger.get_instance().debug(message, LogCategory.SYSTEM, entity_id)
    
    def debug_actor(self, actor_id: str, message: str, state: Any = None):
        """Actor-Debug-Ausgabe"""
        if (hasattr(self, '_debug_actors') and self._debug_actors) or self._global_debug_mode:
            msg = message
            if state is not None:
                msg = f"{message} (State: {state})"
            Logger.get_instance().debug(msg, LogCategory.ACTOR, actor_id)
    
    def debug_sensor(self, sensor_id: str, message: str, state: Any = None):
        """Sensor-Debug-Ausgabe"""
        if (hasattr(self, '_debug_sensors') and self._debug_sensors) or self._global_debug_mode:
            msg = message
            if state is not None:
                msg = f"{message} (State: {state})"
            Logger.get_instance().debug(msg, LogCategory.SENSOR, sensor_id)
    
    def debug_cover(self, cover_id: str, message: str, state: Any = None):
        """Cover-Debug-Ausgabe"""
        if (hasattr(self, '_debug_actors') and self._debug_actors) or self._global_debug_mode:
            msg = message
            if state is not None:
                msg = f"{message} (State: {state})"
            Logger.get_instance().debug(msg, LogCategory.COVER, cover_id)
    
    def debug_mqtt_process(self, message: str):
        """MQTT-Process-Debug-Ausgabe"""
        if (hasattr(self, '_debug_mqtt_process') and self._debug_mqtt_process) or self._global_debug_mode:
            Logger.get_instance().debug(message, LogCategory.MQTT)
    
    def debug_mqtt_send(self, topic: str, payload: str, **kwargs):
        """MQTT-Send-Debug-Ausgabe"""
        if (hasattr(self, '_debug_mqtt_send') and self._debug_mqtt_send) or self._global_debug_mode:
            retained = kwargs.get('retained', False)
            qos = kwargs.get('qos', 0)
            
            # Details-String zusammenbauen
            details = []
            if retained:
                details.append("RETAINED")
            if qos > 0:
                details.append(f"QoS={qos}")
            
            details_str = f" [{' '.join(details)}]" if details else ""
            Logger.get_instance().debug(f"Topic={topic} Payload={payload}{details_str}", LogCategory.MQTT)
    
    def debug_mqtt_receive(self, topic: str, payload: str):
        """MQTT-Receive-Debug-Ausgabe"""
        if (hasattr(self, '_debug_mqtt_receive') and self._debug_mqtt_receive) or self._global_debug_mode:
            Logger.get_instance().debug(f"Topic={topic} Payload={payload}", LogCategory.MQTT)
    
    def debug_gpio(self, message: str, pin: Optional[str] = None):
        """GPIO-Debug-Ausgabe"""
        if (hasattr(self, '_debug_gpio') and self._debug_gpio) or self._global_debug_mode:
            entity_id = pin if pin else None
            Logger.get_instance().debug(message, LogCategory.GPIO, entity_id)
    
    def log_error(self, message: str, entity_id: Optional[str] = None, exception: Exception = None):
        """Error-Log-Ausgabe"""
        Logger.get_instance().error(message, LogCategory.ERROR, entity_id, exception)

# Globale Logger-Instanz
logger = Logger.get_instance()

# Kompatibilitätsfunktionen für bestehenden Code
def direct_print(message: str):
    """Direkte Print-Ausgabe ohne Logger (für Boot-Nachrichten)"""
    print(message)

def set_debug_mode(enabled: bool = False):
    """Debug-Modus einstellen"""
    logger.set_debug_mode(enabled)
    return logger

def set_logging_level_from_config(config: Dict[str, Any], cli_debug_mode: bool = False):
    """Log-Level aus Konfiguration setzen"""
    level_str = config.get("debugging", {}).get("level", "DEBUG").upper()
    
    # Mapping für String -> LogLevel
    level_map = {
        "DEBUG": LogLevel.DEBUG,
        "INFO": LogLevel.INFO,
        "WARNING": LogLevel.WARNING,
        "ERROR": LogLevel.ERROR,
        "NONE": LogLevel.NONE
    }
    
    level = level_map.get(level_str, LogLevel.DEBUG)
    logger.set_level(level)
    
    # Debug-Modus aus Konfiguration
    debug_mode = config.get("debugging", {}).get("mqtt", {}).get("process", False) or cli_debug_mode
    set_debug_mode(debug_mode)