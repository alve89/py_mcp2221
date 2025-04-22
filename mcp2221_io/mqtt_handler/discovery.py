# mqtt_handler/discovery.py
# Version: 1.5.0

import json
import os
from typing import Dict
from ..logging_config import logger
from ..mqtt_config import EntityTypeConfig

class MQTTDiscoveryMixin:
    """Mixin-Klasse für MQTT Discovery Funktionalität"""
    
    def publish_discoveries(self):
        """Veröffentlicht die Discovery-Konfigurationen"""
        if not self.connected.is_set():
            self.debug_error("MQTT nicht verbunden - Discovery nicht möglich")
            return
            
        try:
            self.debug_process_msg("Starte Home Assistant Auto Discovery")
            
            # Board Status Discovery
            self._publish_board_discovery()
            
            # Actor Discoveries
            for actor_id, actor_config in self.config['actors'].items():
                self._publish_actor_discovery(actor_id, actor_config)
                
            # Sensor Discoveries
            if 'sensors' in self.config:
                for sensor_id, sensor_config in self.config['sensors'].items():
                    self._publish_sensor_discovery(sensor_id, sensor_config)
                
            self.debug_process_msg("Home Assistant Auto Discovery abgeschlossen")
        except Exception as e:
            self.debug_error(f"Fehler bei Discovery: {e}", e)

    def _publish_board_discovery(self):
        """Veröffentlicht die Discovery-Konfiguration für das Board"""
        try:
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
            
            self.mqtt_client.publish(config_topic, json.dumps(payload), qos=1, retain=True)
            self.debug_process_msg("Board Discovery-Konfiguration veröffentlicht")
            self.debug_send_msg(config_topic, json.dumps(payload), qos=1, retained=True)
        except Exception as e:
            self.debug_error(f"Fehler bei Board-Discovery: {e}", e)

    def _publish_actor_discovery(self, actor_id: str, actor_config: Dict):
        """Veröffentlicht die Discovery-Konfiguration für einen Actor"""
        try:
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
            
            # Debug-Ausgabe generieren für vollständige Konfiguration
            self.debug_process_msg(f"Discovery-Konfiguration für {actor_id} ({entity_type})")
            
            # Veröffentlichen der Konfiguration
            self.mqtt_client.publish(
                config_topic,
                json.dumps(payload),
                qos=1,
                retain=True  # Retain auf True setzen für permanente Verfügbarkeit
            )
            self.debug_process_msg(f"Discovery-Konfiguration für Actor {actor_id} veröffentlicht")
            self.debug_send_msg(config_topic, json.dumps(payload), qos=1, retained=True)
        except Exception as e:
            self.debug_error(f"Fehler bei Actor-Discovery {actor_id}: {e}", e)
        
    def _publish_sensor_discovery(self, sensor_id: str, sensor_config: Dict):
        """Veröffentlicht die Discovery-Konfiguration für einen Sensor"""
        try:
            entity_type = sensor_config.get('entity_type', 'binary_sensor').lower()
            discovery_type = EntityTypeConfig.get_discovery_type(entity_type)
            discovery_config = EntityTypeConfig.get_discovery_config(entity_type)
            
            config_topic = f"{self.ha_discovery_prefix}/{discovery_type}/{self.device_id}/{sensor_id}/config"
            
            # Basis-Discovery-Konfiguration
            payload = {
                "name": sensor_config['description'],
                "unique_id": f"{self.device_id}_{sensor_id}",
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
                payload["state_topic"] = f"{self.base_topic}/{sensor_id}/state"
                
            # Weitere Discovery-Konfiguration
            payload.update({k: v for k, v in discovery_config.items() 
                          if k not in ['state_topic', 'command_topic']})
            
            # Spezifische Sensor-Konfiguration hinzufügen
            if 'device_class' in sensor_config:
                payload["device_class"] = sensor_config['device_class']
                
            self.mqtt_client.publish(
                config_topic,
                json.dumps(payload),
                qos=1,
                retain=True  # Retain auf True setzen für permanente Verfügbarkeit
            )
            self.debug_process_msg(f"Discovery-Konfiguration für Sensor {sensor_id} veröffentlicht")
            self.debug_send_msg(config_topic, json.dumps(payload), qos=1, retained=True)
        except Exception as e:
            self.debug_error(f"Fehler bei Sensor-Discovery {sensor_id}: {e}", e)