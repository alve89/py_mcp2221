# mqtt_handler/discovery.py
# Version: 1.0.0

import json
from typing import Dict
from ..logging_config import logger
from ..mqtt_config import EntityTypeConfig

class MQTTDiscoveryMixin:
    """Mixin-Klasse für MQTT Discovery Funktionalität"""
    
    def publish_discoveries(self):
        """Veröffentlicht die Discovery-Konfigurationen"""
        if not self.connected.is_set():
            logger.error("MQTT nicht verbunden - Discovery nicht möglich")
            return
            
        logger.debug("Starte Home Assistant Auto Discovery")
        
        # Board Status Discovery
        self._publish_board_discovery()
        
        # Actor Discoveries
        for actor_id, actor_config in self.config['actors'].items():
            self._publish_actor_discovery(actor_id, actor_config)

    def _publish_board_discovery(self):
        """Veröffentlicht die Discovery-Konfiguration für das Board"""
        config_topic = f"{self.ha_discovery_prefix}/binary_sensor/{self.device_id}/board_status/config"
        payload = {
            "name": f"{self.device_name} Board Status",
            "unique_id": f"{self.device_id}_board_status",
            "device": {
                "identifiers": [f"mcp2221_{self.device_id}"],
                "name": self.device_name,
                "model": "MCP2221 IO Controller",
                "manufacturer": "Custom",
                "sw_version": "1.0.0"
            },
            "state_topic": f"{self.base_topic}/board_status/state",
            "json_attributes_topic": f"{self.base_topic}/board_status/message",
            "payload_on": "online",
            "payload_off": "offline",
            "device_class": "connectivity",
            "availability": [{
                "topic": f"{self.base_topic}/status",
                "payload_available": "online",
                "payload_not_available": "offline"
            }]
        }
        
        self.mqtt_client.publish(config_topic, json.dumps(payload), qos=1, retain=False)

    def _publish_actor_discovery(self, actor_id: str, actor_config: Dict):
        """Veröffentlicht die Discovery-Konfiguration für einen Actor"""
        entity_type = actor_config.get('entity_type', 'switch').lower()
        discovery_type = EntityTypeConfig.get_discovery_type(entity_type)
        discovery_config = EntityTypeConfig.get_discovery_config(entity_type)
        
        config_topic = f"{self.ha_discovery_prefix}/{discovery_type}/{self.device_id}/{actor_id}/config"
        
        # Basis-Discovery-Konfiguration
        payload = {
            "name": actor_config['description'],
            "unique_id": f"{self.device_id}_{actor_id}",
            "device": {
                "identifiers": [f"mcp2221_{self.device_id}"],
                "name": self.device_name,
                "model": "MCP2221 IO Controller",
                "manufacturer": "Custom",
                "sw_version": "1.0.0"
            },
            "availability": [
                {
                    "topic": f"{self.base_topic}/status",
                    "payload_available": "online",
                    "payload_not_available": "offline"
                },
                {
                    "topic": f"{self.base_topic}/board_status/state",
                    "payload_available": "online",
                    "payload_not_available": "offline"
                }
            ]
        }
        
        # Entity-spezifische Discovery-Konfiguration
        if discovery_config.get('state_topic'):
            payload["state_topic"] = f"{self.base_topic}/{actor_id}/state"
        if discovery_config.get('command_topic'):
            payload["command_topic"] = f"{self.base_topic}/{actor_id}/set"
            
        # Weitere Discovery-Konfiguration
        payload.update({k: v for k, v in discovery_config.items() 
                       if k not in ['state_topic', 'command_topic']})
        
        self.mqtt_client.publish(
            config_topic,
            json.dumps(payload),
            qos=1,
            retain=False
        )