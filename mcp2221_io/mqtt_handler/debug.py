# mqtt_handler/debug.py
# Version: 1.0.1

from mcp2221_io.logging_config import logger
from typing import Dict, Optional, Any

class MQTTDebugMixin:
    """Mixin-Klasse für erweitertes MQTT Debugging"""
    
    def _init_debug_config(self, config: Dict):
        """Initialisiert die Debug-Konfiguration"""
        logger.debug(f"MQTT Debug Konfiguration: {config.get('debugging', {}).get('mqtt', {})}")
        self.debug_config = config.get('debugging', {}).get('mqtt', {})
        self.debug_process = bool(self.debug_config.get('process', False))
        self.debug_send = bool(self.debug_config.get('send', False))
        self.debug_receive = bool(self.debug_config.get('receive', False))
        logger.debug(f"MQTT Debug Flags: process={self.debug_process}, send={self.debug_send}, receive={self.debug_receive}")
    
    def debug_process_msg(self, message: str, error: bool = False):
        """Debug-Ausgabe für Prozess-Informationen"""
        if self.debug_process:
            if error:
                logger.error(f"[MQTT Process] {message}")
            # else:
                # logger.debug(f"[MQTT Process] {message}")

    def debug_send_msg(self, topic: str, payload: Any, retained: bool = False, qos: int = 0):
        """Debug-Ausgabe für gesendete MQTT-Nachrichten"""
        if self.debug_send:
            retain_str = " (retained)" if retained else ""
            logger.debug(f"[MQTT Send] {topic} = {payload} (QoS: {qos}){retain_str}")

    def debug_receive_msg(self, topic: str, payload: str):
        """Debug-Ausgabe für empfangene MQTT-Nachrichten"""
        if self.debug_receive:
            logger.debug(f"[MQTT Receive] {topic} = {payload}")

    def debug_error(self, message: str, error: Optional[Exception] = None):
        """Debug-Ausgabe für MQTT-Fehler"""
        if self.debug_process:
            if error:
                logger.error(f"[MQTT Error] {message}: {str(error)}")
            else:
                logger.error(f"[MQTT Error] {message}")