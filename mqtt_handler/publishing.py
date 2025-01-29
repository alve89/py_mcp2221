# mqtt_handler/publishing.py
# Version: 1.0.0

import paho.mqtt.client as mqtt
from ..logging_config import logger

class MQTTPublishingMixin:
    """Mixin-Klasse für MQTT Publishing Funktionalität"""
    
    def publish_state(self, actor_id: str, state: bool):
        """Veröffentlicht den State eines Actors"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Status für {actor_id} kann nicht gesendet werden"
            logger.warning(msg)
            self.publish_debug_message(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verfügbar - Status für {actor_id} kann nicht gesendet werden"
            logger.warning(msg)
            self.publish_debug_message(msg)
            return
            
        state_str = self._convert_internal_to_state(actor_id, state)
        topic = f"{self.base_topic}/{actor_id}/state"
        logger.debug(f"Publiziere State {state_str} für {actor_id}")
        try:
            result = self.mqtt_client.publish(topic, state_str, qos=1, retain=True)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"State für {actor_id} erfolgreich publiziert")
            else:
                msg = f"Fehler beim Publizieren des States für {actor_id}: {result.rc}"
                logger.warning(msg)
                self.publish_debug_message(msg)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des States: {e}"
            logger.error(error_msg)
            self.publish_debug_message(error_msg)

    def publish_command(self, actor_id: str, command: str):
        """Veröffentlicht ein Command für einen Actor"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Kommando für {actor_id} kann nicht gesendet werden"
            logger.warning(msg)
            self.publish_debug_message(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verbunden - Kommando für {actor_id} kann nicht gesendet werden"
            logger.warning(msg)
            self.publish_debug_message(msg)
            return
            
        topic = f"{self.base_topic}/{actor_id}/set"
        logger.debug(f"Publiziere Kommando {command} für {actor_id}")
        try:
            result = self.mqtt_client.publish(topic, command, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Kommando für {actor_id} erfolgreich publiziert")
            else:
                msg = f"Fehler beim Publizieren des Kommandos für {actor_id}: {result.rc}"
                logger.warning(msg)
                self.publish_debug_message(msg)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des Kommandos: {e}"
            logger.error(error_msg)
            self.publish_debug_message(error_msg)

    def publish_debug_message(self, message: str):
        """Veröffentlicht Debug-Nachrichten via MQTT"""
        if not self.connected.is_set():
            return
            
        topic = f"{self.base_topic}/debug"
        try:
            self.mqtt_client.publish(topic, message, qos=1, retain=True)
        except Exception as e:
            logger.error(f"Fehler beim Publizieren der Debug-Nachricht: {e}")