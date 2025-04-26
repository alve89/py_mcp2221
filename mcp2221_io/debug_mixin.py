# debug_mixin.py
# Version: 1.0.0

from typing import Dict, Optional, Any, List, Tuple
import os
from .logging_config import logger, LogCategory

class DebugMixin:
    """Universelle Mixin-Klasse für Debug-Funktionalität in allen Komponenten"""
    
    def _init_debug_config(self, config: Dict[str, Any]):
        """Initialisiert die Debug-Konfiguration aus dem config-Dict"""
        self.debug_config = config.get('debugging', {})
        
        # System-Debug-Konfiguration
        self.system_debug_config = self.debug_config.get('system', {})
        self.debug_process = self.system_debug_config.get('process', False)
        
        # Entities Debug (Actors, Sensors)
        self.debug_entities = self.system_debug_config.get('entities', {})
        self.debug_actors = self.debug_entities.get('actors', False)
        self.debug_sensors = self.debug_entities.get('sensors', False)
        
        # MQTT-Debug-Konfiguration
        self.mqtt_debug_config = self.debug_config.get('mqtt', {})
        self.debug_mqtt_process = self.mqtt_debug_config.get('process', False)
        self.debug_mqtt_send = self.mqtt_debug_config.get('send', False)
        self.debug_mqtt_receive = self.mqtt_debug_config.get('receive', False)
        
        # GPIO-Debug
        self.debug_gpio = self.debug_config.get('gpio', False)
        
        # Debug-Modus aus Umgebungsvariable
        self.debug_mode = os.environ.get('MCP2221_DEBUG', '0') == '1'
    
    # =========== SYSTEM DEBUG ===========
    
    def debug_system_process(self, message: str, error: bool = False):
        """Debug-Ausgabe für System-Prozess-Informationen"""
        if hasattr(self, 'debug_process') and self.debug_process:
            if error:
                logger.error(message, LogCategory.SYSTEM)
            else:
                logger.debug(message, LogCategory.SYSTEM)
    
    def debug_startup(self, message: str):
        """Debug-Ausgabe für System-Startup-Informationen"""
        if hasattr(self, 'debug_process') and self.debug_process:
            logger.debug(f"Startup: {message}", LogCategory.SYSTEM)
    
    def debug_shutdown(self, message: str):
        """Debug-Ausgabe für System-Shutdown-Informationen"""
        if hasattr(self, 'debug_process') and self.debug_process:
            logger.debug(f"Shutdown: {message}", LogCategory.SYSTEM)
    
    def debug_config_load(self, component: str, config: Dict):
        """Debug-Ausgabe für Konfigurationsladungen"""
        if hasattr(self, 'debug_process') and self.debug_process:
            logger.debug(f"Config Load: {component}", LogCategory.SYSTEM)
    
    def debug_system_error(self, message: str, error: Optional[Exception] = None):
        """Debug-Ausgabe für System-Fehler"""
        if hasattr(self, 'debug_process') and self.debug_process:
            logger.error(message, LogCategory.SYSTEM, exception=error)
    
    # =========== ACTOR DEBUG ===========
    
    def debug_actor_state(self, actor_id: str, state: Any, additional_info: Optional[str] = None):
        """Debug-Ausgabe für Actor-Zustandsänderungen"""
        if hasattr(self, 'debug_actors') and self.debug_actors:
            info = f" ({additional_info})" if additional_info else ""
            logger.debug(f"{state}{info}", LogCategory.ACTOR, actor_id)
    
    def debug_actor_error(self, actor_id: str, message: str, error: Optional[Exception] = None):
        """Debug-Ausgabe für Actor-spezifische Fehler"""
        if hasattr(self, 'debug_actors') and self.debug_actors:
            logger.error(message, LogCategory.ACTOR, actor_id, error)
    
    # =========== SENSOR DEBUG ===========
    
    def debug_sensor_state(self, sensor_id: str, state: Any, additional_info: Optional[str] = None):
        """Debug-Ausgabe für Sensor-Zustandsänderungen"""
        if hasattr(self, 'debug_sensors') and self.debug_sensors:
            info = f" ({additional_info})" if additional_info else ""
            logger.debug(f"{state}{info}", LogCategory.SENSOR, sensor_id)
    
    def debug_sensor_error(self, sensor_id: str, message: str, error: Optional[Exception] = None):
        """Debug-Ausgabe für Sensor-spezifische Fehler"""
        if hasattr(self, 'debug_sensors') and self.debug_sensors:
            logger.error(message, LogCategory.SENSOR, sensor_id, error)
    
    # =========== COVER DEBUG ===========
    
    def debug_cover_state(self, cover_id: str, state: Any, additional_info: Optional[str] = None):
        """Debug-Ausgabe für Cover-Zustandsänderungen"""
        if hasattr(self, 'debug_actors') and self.debug_actors:
            info = f" ({additional_info})" if additional_info else ""
            logger.debug(f"{state}{info}", LogCategory.COVER, cover_id)
    
    def debug_cover_error(self, cover_id: str, message: str, error: Optional[Exception] = None):
        """Debug-Ausgabe für Cover-spezifische Fehler"""
        if hasattr(self, 'debug_actors') and self.debug_actors:
            logger.error(message, LogCategory.COVER, cover_id, error)
    
    # =========== GPIO DEBUG ===========
    
    def debug_gpio(self, message: str, pin: Optional[str] = None):
        """Debug-Ausgabe für GPIO-Operationen"""
        if hasattr(self, 'debug_gpio') and self.debug_gpio:
            if pin:
                logger.debug(message, LogCategory.GPIO, pin)
            else:
                logger.debug(message, LogCategory.GPIO)
    
    # =========== MQTT DEBUG ===========
    
    def debug_mqtt_process(self, message: str):
        """Debug-Ausgabe für MQTT-Prozess-Informationen"""
        if hasattr(self, 'debug_mqtt_process') and self.debug_mqtt_process:
            logger.debug(message, LogCategory.MQTT)
    
    def debug_mqtt_send(self, topic: str, payload: str, retained: bool = False, qos: int = 0):
        """Debug-Ausgabe für gesendete MQTT-Nachrichten"""
        if hasattr(self, 'debug_mqtt_send') and self.debug_mqtt_send:
            # Details-String zusammenbauen
            details = []
            if retained:
                details.append("RETAINED")
            if qos > 0:
                details.append(f"QoS={qos}")
            
            details_str = f" [{' '.join(details)}]" if details else ""
            logger.debug(f"SEND Topic={topic} Payload={payload}{details_str}", LogCategory.MQTT)
    
    def debug_mqtt_receive(self, topic: str, payload: str):
        """Debug-Ausgabe für empfangene MQTT-Nachrichten"""
        if hasattr(self, 'debug_mqtt_receive') and self.debug_mqtt_receive:
            logger.debug(f"RECV Topic={topic} Payload={payload}", LogCategory.MQTT)
    
    def debug_mqtt_error(self, message: str, exception: Optional[Exception] = None):
        """Debug-Ausgabe für MQTT-Fehler"""
        logger.error(message, LogCategory.MQTT, exception=exception)