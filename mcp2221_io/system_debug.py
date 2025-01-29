# system_debug.py
# Version: 1.0.0

from typing import Dict, Optional, Any
from mcp2221_io.logging_config import logger

class SystemDebugMixin:
    """Mixin-Klasse für erweitertes System Debugging"""
    
    def _init_system_debug_config(self, config: Dict):
        """Initialisiert die System-Debug-Konfiguration"""
        self.system_debug_config = config.get('debugging', {}).get('system', {})
        self.debug_process = self.system_debug_config.get('process', False)
        self.debug_entities = self.system_debug_config.get('entities', {})
        self.debug_actors = self.debug_entities.get('actors', False)
        self.debug_sensors = self.debug_entities.get('sensors', False)
    
    def debug_system_process(self, message: str, error: bool = False):
        """Debug-Ausgabe für System-Prozess-Informationen"""
        if self.debug_process:
            if error:
                logger.error(f"[System Process] {message}")
            else:
                logger.debug(f"[System Process] {message}")

    def debug_actor_state(self, actor_id: str, state: Any, additional_info: Optional[str] = None):
        """Debug-Ausgabe für Actor-Zustandsänderungen"""
        if self.debug_actors:
            info = f" ({additional_info})" if additional_info else ""
            logger.debug(f"[Actor State] {actor_id}: {state}{info}")

    def debug_sensor_state(self, sensor_id: str, state: Any, additional_info: Optional[str] = None):
        """Debug-Ausgabe für Sensor-Zustandsänderungen"""
        if self.debug_sensors:
            info = f" ({additional_info})" if additional_info else ""
            logger.debug(f"[Sensor State] {sensor_id}: {state}{info}")

    def debug_system_error(self, message: str, error: Optional[Exception] = None):
        """Debug-Ausgabe für System-Fehler"""
        if self.debug_process:
            if error:
                logger.error(f"[System Error] {message}: {str(error)}")
            else:
                logger.error(f"[System Error] {message}")

    def debug_actor_error(self, actor_id: str, message: str, error: Optional[Exception] = None):
        """Debug-Ausgabe für Actor-spezifische Fehler"""
        if self.debug_actors:
            if error:
                logger.error(f"[Actor Error] {actor_id}: {message}: {str(error)}")
            else:
                logger.error(f"[Actor Error] {actor_id}: {message}")

    def debug_sensor_error(self, sensor_id: str, message: str, error: Optional[Exception] = None):
        """Debug-Ausgabe für Sensor-spezifische Fehler"""
        if self.debug_sensors:
            if error:
                logger.error(f"[Sensor Error] {sensor_id}: {message}: {str(error)}")
            else:
                logger.error(f"[Sensor Error] {sensor_id}: {message}")

    def debug_config_load(self, component: str, config: Dict):
        """Debug-Ausgabe für Konfigurationsladungen"""
        if self.debug_process:
            logger.debug(f"[Config Load] {component}: {config}")

    def debug_startup(self, message: str):
        """Debug-Ausgabe für System-Startup-Informationen"""
        if self.debug_process:
            logger.debug(f"[System Startup] {message}")

    def debug_shutdown(self, message: str):
        """Debug-Ausgabe für System-Shutdown-Informationen"""
        if self.debug_process:
            logger.debug(f"[System Shutdown] {message}")

    def debug_gpio(self, message: str):
        """Debug-Ausgabe für GPIO-Operationen"""
        if self.system_debug_config.get('gpio', False):
            logger.debug(f"[GPIO] {message}")