# mqtt_handler/callbacks.py
# Version: 1.5.0

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
                    self.debug_process_msg(f"Topic zum Abonnieren vorbereitet: {command_topic}")
                
                # State Topic nur für Entities mit State
                if discovery_config.get('state_topic'):
                    state_topic = f"{self.base_topic}/{actor_id}/state"
                    topics.append((state_topic, 1))
                    self.debug_process_msg(f"Topic zum Abonnieren vorbereitet: {state_topic}")
            
            if topics:
                self.debug_process_msg(f"Abonniere {len(topics)} Topics...")
                self.mqtt_client.subscribe(topics)
                for topic, qos in topics:
                    self.debug_process_msg(f"Topic abonniert: {topic} (QoS: {qos})")
        else:
            # MQTT Connect Return Codes interpretieren
            error_messages = {
                1: "Falsche Protokollversion",
                2: "Ungültige Client-ID",
                3: "Server nicht verfügbar",
                4: "Falsche Anmeldedaten",
                5: "Nicht autorisiert"
            }
            error_msg = error_messages.get(rc, f"Unbekannter Fehler (Code: {rc})")
            self.debug_error(f"MQTT Verbindung fehlgeschlagen: {error_msg}")
            
            # Fallback für kritische Fehler direkt über logger
            logger.error(f"MQTT Verbindung fehlgeschlagen: {error_msg}")
            
            # Versuche Debug-Nachricht zu veröffentlichen, wenn Methode existiert
            try:
                if hasattr(self, 'publish_debug_message'):
                    self.publish_debug_message(f"MQTT Verbindung fehlgeschlagen: {error_msg}")
            except Exception as e:
                # Ignoriere Fehler bei der Debug-Nachricht, aber logge direkt
                logger.error(f"Fehler bei Debug-Nachricht: {e}")
                pass

    def _on_disconnect(self, client, userdata, rc):
        """Callback für MQTT-Verbindungstrennung"""
        if rc == 0:
            self.debug_process_msg("MQTT Verbindung ordnungsgemäß getrennt")
        else:
            self.debug_process_msg(f"MQTT Verbindung unerwartet getrennt mit Code {rc}")
            
        self.connected.clear()
        
        # Versuche Debug-Nachricht zu veröffentlichen, wenn Methode existiert
        if hasattr(self, 'publish_debug_message'):
            try:
                self.publish_debug_message(f"MQTT Verbindung getrennt mit Code {rc}")
            except:
                pass  # Ignoriere Fehler bei der Debug-Nachricht
        
        # Ensure board status is set to offline on disconnect
        try:
            offline_topic = f"{self.base_topic}/board_status/state"
            self.mqtt_client.publish(offline_topic, "offline", qos=1, retain=True)
            self.debug_send_msg(offline_topic, "offline", retained=True, qos=1)
        except Exception as e:
            # Direktes Logging bei kritischen Fehlern
            logger.error(f"Fehler beim Setzen des Offline-Status: {e}")

    def _on_message(self, client, userdata, message):
        """Callback für eingehende MQTT-Nachrichten"""
        try:
            topic = message.topic
            payload = message.payload.decode()
            self.debug_receive_msg(topic, payload)
            
            topic_parts = topic.split('/')
            if len(topic_parts) == 3 and topic_parts[2] == 'set':
                actor_id = topic_parts[1]
                self.debug_process_msg(f"Command-Topic erkannt für {actor_id}: {payload}")
                
                if actor_id in self.command_callbacks:
                    if self._board_status:
                        self.debug_process_msg(f"Führe Callback für {actor_id} aus mit Wert {payload}")
                        self.command_callbacks[actor_id](actor_id, payload)
                    else:
                        error_msg = f"Board nicht verfügbar - Kommando für {actor_id} wird ignoriert"
                        self.debug_error(error_msg)
                        if hasattr(self, 'publish_debug_message'):
                            try:
                                self.publish_debug_message(error_msg)
                            except:
                                pass  # Ignoriere Fehler bei der Debug-Nachricht
                else:
                    self.debug_error(f"Kein Callback für {actor_id} registriert")
            else:
                self.debug_process_msg(f"Keine Aktion für Topic {topic} definiert")
        except Exception as e:
            error_msg = f"Fehler bei der Nachrichtenverarbeitung: {e}"
            self.debug_error(error_msg, e)
            
            # Direktes Logging für kritische Fehler
            logger.error(f"Fehler bei der Nachrichtenverarbeitung: {e}")
            
            if hasattr(self, 'publish_debug_message'):
                try:
                    self.publish_debug_message(error_msg)
                except:
                    pass  # Ignoriere Fehler bei der Debug-Nachricht
                    
    def _on_publish(self, client, userdata, mid):
        """Callback für erfolgreiche MQTT-Publizierung"""
        # Message-ID-Protokollierung nur im ausführlichen Debug-Modus aktivieren
        # Reduzieren wir hier die Standard-Protokollierung, da detailliertere Protokolle 
        # bereits beim Versenden von Nachrichten erstellt werden
        if hasattr(self, 'debug_mode') and self.debug_mode and hasattr(self, 'debug_send') and self.debug_send:
            # Nur im ausführlichen Debug-Modus loggen wir Message IDs
            self.debug_process_msg(f"MQTT Nachricht {mid} erfolgreich veröffentlicht")