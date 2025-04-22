# mqtt_handler/base.py
# Version: 1.5.0

import paho.mqtt.client as mqtt
import threading
import time
from typing import Dict, Optional, Callable
from ..logging_config import logger
from ..mcp2221_patch import MCP2221Device
from ..mqtt_config import EntityTypeConfig

class MQTTBaseMixin:
    """Mixin-Klasse für grundlegende MQTT-Funktionalität"""
    
    def _setup_last_will(self):
        """Konfiguriert Last Will and Testament"""
        # LWT für Service-Status
        self.mqtt_client.will_set(
            f"{self.base_topic}/status",
            "offline",
            qos=1,
            retain=True
        )
        self.debug_process_msg("Service-Status LWT konfiguriert")
        
        # LWT für Board-Status
        self.mqtt_client.will_set(
            f"{self.base_topic}/board_status/state",
            "offline",
            qos=1,
            retain=True
        )
        self.debug_process_msg("Board-Status LWT konfiguriert")
        
    def _convert_internal_to_state(self, actor_id: str, internal_state: bool) -> str:
        """Konvertiert den internen Boolean-State in den entsprechenden MQTT-State"""
        actor_config = self.config['actors'].get(actor_id, {})
        entity_type = actor_config.get('entity_type', 'switch')
        return EntityTypeConfig.convert_to_mqtt_state(entity_type, internal_state)

    def _convert_command_to_internal(self, actor_id: str, command: str) -> bool:
        """Konvertiert ein MQTT-Command in den internen Boolean-State"""
        actor_config = self.config['actors'].get(actor_id, {})
        entity_type = actor_config.get('entity_type', 'switch')
        return EntityTypeConfig.convert_to_internal_state(entity_type, command)