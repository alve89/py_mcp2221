# mqtt_handler/callbacks.py
# Version: 1.1.0

from typing import Callable
from ..logging_config import logger
from ..mqtt_config import EntityTypeConfig

class MQTTCallbacksMixin:
    """Mixin-Klasse für MQTT Callbacks"""

    def _on_connect(self, client, userdata, flags, rc):
        """Callback für erfolgreiche MQTT-Verbindung"""
        if rc == 0:
            self.debug_process_msg("MQTT Verbindung erfolgreich")
            self.connected.set()
            
            self._restore_states()
            self.mqtt_client.publish(f"{self.base_topic}/status", "online", qos=1, retain=True)
            self.debug_send_msg(f"{self.base_topic}/status", "online", retained=True, qos=1)
            
            # Subscribe to topics
            topics = []
            for actor_id, actor_config in self.config['actors'].items():
                entity_type = actor_config.get('entity_type', 'switch')
                discovery_config = EntityTypeConfig.get_discovery_config(entity_type)
                
                # Command Topic für alle Entities
                if discovery_config.get('command_topic'):
                    command_topic = f"{self.base_topic}/{actor_id}/set"
                    topics.append((command_topic, 1))
                
                # State Topic nur für Entities mit State
                if discovery_config.get('state_topic'):
                    state_topic = f"{self.base_topic}/{actor_id}/state"
                    topics.append((state_topic, 1))
                
                self.debug_process_msg(f"Abonniere Topics für {actor_id}")
            
            if topics:
                self.mqtt_client.subscribe(topics)
                for topic, qos in topics:
                    self.debug_process_msg(f"Topic abonniert: {topic} (QoS: {qos})")

    def _on_disconnect(self, client, userdata, rc):
        """Callback für MQTT-Verbindungstrennung"""
        self.debug_process_msg(f"MQTT Verbindung getrennt mit Code {rc}")
        self.connected.clear()
        self.publish_debug_message(f"MQTT Verbindung getrennt mit Code {rc}")
        
        # Ensure board status is set to offline on disconnect
        offline_topic = f"{self.base_topic}/board_status/state"
        self.mqtt_client.publish(offline_topic, "offline", qos=1, retain=True)
        self.debug_send_msg(offline_topic, "offline", retained=True, qos=1)

    def _on_message(self, client, userdata, message):
        """Callback für eingehende MQTT-Nachrichten"""
        try:
            topic = message.topic
            payload = message.payload.decode()
            self.debug_receive_msg(topic, payload)
            
            topic_parts = topic.split('/')
            if len(topic_parts) == 3 and topic_parts[2] == 'set':
                actor_id = topic_parts[1]
                if actor_id in self.command_callbacks:
                    if self._board_status:
                        self.debug_process_msg(f"Führe Callback für {actor_id} aus mit Wert {payload}")
                        self.command_callbacks[actor_id](actor_id, payload)
                    else:
                        error_msg = f"Board nicht verfügbar - Kommando für {actor_id} wird ignoriert"
                        self.debug_error(error_msg)
                        self.publish_debug_message(error_msg)
                else:
                    self.debug_error(f"Kein Callback für {actor_id} registriert")
        except Exception as e:
            error_msg = f"Fehler bei der Nachrichtenverarbeitung: {e}"
            self.debug_error(error_msg, e)
            self.publish_debug_message(error_msg)

    def _on_publish(self, client, userdata, mid):
        """Callback für erfolgreiche MQTT-Publizierung"""
        self.debug_process_msg(f"MQTT Nachricht {mid} erfolgreich veröffentlicht")

    def register_command_callback(self, actor_id: str, callback: Callable[[str, str], None]):
        """Registriert einen Callback für Commands"""
        self.debug_process_msg(f"Registriere Command Callback für {actor_id}")
        self.command_callbacks[actor_id] = callback