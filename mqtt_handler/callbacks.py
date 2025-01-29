# mqtt_handler/callbacks.py
# Version: 1.0.0

from typing import Callable
from ..logging_config import logger
from ..mqtt_config import EntityTypeConfig

class MQTTCallbacksMixin:
    """Mixin-Klasse für MQTT Callbacks"""

    def _on_connect(self, client, userdata, flags, rc):
        """Callback für erfolgreiche MQTT-Verbindung"""
        if rc == 0:
            logger.debug("MQTT Verbindung erfolgreich")
            self.connected.set()
            
            self._restore_states()
            self.mqtt_client.publish(f"{self.base_topic}/status", "online", qos=1, retain=True)
            
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
                
                logger.debug(f"Abonniere Topics für {actor_id}")
            
            if topics:
                self.mqtt_client.subscribe(topics)

    def _on_disconnect(self, client, userdata, rc):
        """Callback für MQTT-Verbindungstrennung"""
        logger.debug(f"MQTT Verbindung getrennt mit Code {rc}")
        self.connected.clear()
        self.publish_debug_message(f"MQTT Verbindung getrennt mit Code {rc}")
        # Ensure board status is set to offline on disconnect
        self.mqtt_client.publish(
            f"{self.base_topic}/board_status/state",
            "offline",
            qos=1,
            retain=True
        )

    def _on_message(self, client, userdata, message):
        """Callback für eingehende MQTT-Nachrichten"""
        try:
            topic = message.topic
            payload = message.payload.decode()
            logger.debug(f"MQTT Nachricht empfangen: {topic} = {payload}")
            
            topic_parts = topic.split('/')
            if len(topic_parts) == 3 and topic_parts[2] == 'set':
                actor_id = topic_parts[1]
                if actor_id in self.command_callbacks:
                    if self._board_status:
                        logger.debug(f"Führe Callback für {actor_id} aus mit Wert {payload}")
                        self.command_callbacks[actor_id](actor_id, payload)
                    else:
                        msg = f"Board nicht verfügbar - Kommando für {actor_id} wird ignoriert"
                        logger.warning(msg)
                        self.publish_debug_message(msg)
                else:
                    logger.warning(f"Kein Callback für {actor_id} registriert")
        except Exception as e:
            error_msg = f"Fehler bei der Nachrichtenverarbeitung: {e}"
            logger.error(error_msg)
            self.publish_debug_message(error_msg)

    def _on_publish(self, client, userdata, mid):
        """Callback für erfolgreiche MQTT-Publizierung"""
        logger.debug(f"MQTT Nachricht {mid} erfolgreich veröffentlicht")

    def register_command_callback(self, actor_id: str, callback: Callable[[str, str], None]):
        """Registriert einen Callback für Commands"""
        logger.debug(f"Registriere Command Callback für {actor_id}")
        self.command_callbacks[actor_id] = callback