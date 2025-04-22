# mqtt_handler/states.py
# Version: 1.6.0

import threading
import time
from typing import Dict
from ..logging_config import logger
from ..mqtt_config import EntityTypeConfig

# Direkter Print ohne Logger (für Boot-Nachrichten)
def direct_print(message):
    print(message)

class MQTTStatesMixin:
    """Mixin-Klasse für MQTT State Management"""

    def start_board_monitoring(self):
        """Startet das Board-Monitoring"""
        def check_status():
            while not self._shutdown_flag.is_set() and self.connected.is_set():
                try:
                    status, message = self._mcp_device.check_board_status()
                    status_changed = (status != self._board_status or 
                                    message != self._board_status_message)
                    
                    self._board_status = status
                    self._board_status_message = message
                    
                    if status_changed:
                        self.debug_process_msg(f"Board Status geändert: {status} - {message}")
                        self.publish_board_status()
                        
                        # Versuche Debug-Nachricht zu senden
                        try:
                            if hasattr(self, 'publish_debug_message'):
                                self.publish_debug_message(
                                    f"Board Status: {'Online' if status else 'Offline'} - {message}"
                                )
                        except Exception as e:
                            logger.error(f"Fehler beim Senden der Board-Status-Nachricht: {e}")
                        
                        # Nur bei Statusänderung alle States republizieren
                        self.publish_all_states(force_republish=False)
                    
                    # Regelmäßige Republizierung NUR des Board-Status, nicht aller Actor-States
                    else:
                        self.publish_board_status()
                    
                    time.sleep(10)
                except Exception as e:
                    if hasattr(self, 'debug_error'):
                        self.debug_error(f"Fehler im Board-Monitoring: {e}", e)
                    
                    # Direktes Logging für kritische Fehler
                    logger.error(f"Fehler im Board-Monitoring: {e}")
                    
                    if not self._shutdown_flag.is_set():
                        time.sleep(30)  # Längere Pause bei Fehler
                        
        self._board_status_timer = threading.Thread(target=check_status, daemon=True)
        self._board_status_timer.start()
        direct_print("Board-Monitoring Thread gestartet")  # Direktes Logging ohne Zeitstempel

    def publish_board_status(self):
        """Veröffentlicht den Board-Status via MQTT"""
        if not self.connected.is_set():
            return
            
        try:
            status_topic = f"{self.base_topic}/board_status/state"
            message_topic = f"{self.base_topic}/board_status/message"
            
            status_str = "online" if self._board_status else "offline"
            
            self.mqtt_client.publish(
                status_topic,
                status_str,
                qos=1,
                retain=True
            )
            self.debug_send_msg(status_topic, status_str, retained=True, qos=1)
            
            self.mqtt_client.publish(
                message_topic,
                self._board_status_message,
                qos=1,
                retain=True
            )
            self.debug_send_msg(message_topic, self._board_status_message, retained=True, qos=1)
        except Exception as e:
            # Direktes Logging für kritische Fehler
            logger.error(f"Fehler beim Veröffentlichen des Board-Status: {e}")

    def publish_all_states(self, force_republish=True):
        """
        Aktualisiert die States aller Aktoren und Sensoren
        
        :param force_republish: Wenn True, werden auch die Actor-States republiziert, 
                                sonst nur Service und Board Status
        """
        # Service Status
        try:
            service_topic = f"{self.base_topic}/status"
            self.mqtt_client.publish(
                service_topic,
                "online",
                qos=1,
                retain=True
            )
            self.debug_send_msg(service_topic, "online", retained=True, qos=1)
            
            if force_republish:
                # Actors
                for actor_id, actor_config in self.config['actors'].items():
                    entity_type = actor_config.get('entity_type', 'switch')
                    discovery_config = EntityTypeConfig.get_discovery_config(entity_type)
                    
                    # Status-Topic für alle Entities
                    status_topic = f"{self.base_topic}/{actor_id}/status"
                    status_str = "online" if self._board_status else "offline"
                    self.mqtt_client.publish(
                        status_topic,
                        status_str,
                        qos=1,
                        retain=True
                    )
                    self.debug_send_msg(status_topic, status_str, retained=True, qos=1)
                    
                    # State-Topic nur für Entities mit State (aber NICHT command republizieren)
                    if discovery_config.get('state_topic'):
                        state_topic = f"{self.base_topic}/{actor_id}/state"
                        state_str = self._convert_internal_to_state(actor_id, False)
                        self.mqtt_client.publish(
                            state_topic,
                            state_str,
                            qos=1,
                            retain=True
                        )
                        self.debug_send_msg(state_topic, state_str, retained=True, qos=1)

                # Sensoren
                if 'sensors' in self.config:
                    for sensor_id, sensor_config in self.config['sensors'].items():
                        entity_type = sensor_config.get('entity_type', 'binary_sensor')
                        discovery_config = EntityTypeConfig.get_discovery_config(entity_type)
                        
                        # Status-Topic für Sensoren
                        sensor_status_topic = f"{self.base_topic}/{sensor_id}/status"
                        status_str = "online" if self._board_status else "offline"
                        self.mqtt_client.publish(
                            sensor_status_topic,
                            status_str,
                            qos=1,
                            retain=True
                        )
                        self.debug_send_msg(sensor_status_topic, status_str, retained=True, qos=1)
                        
                        # State-Topic für Sensoren (immer OFF bei Initialisierung, sofern nicht anders bekannt)
                        if discovery_config.get('state_topic'):
                            sensor_state_topic = f"{self.base_topic}/{sensor_id}/state"
                            state_str = "OFF"  # Default-Zustand
                            
                            # Wenn möglich, tatsächlichen Sensorwert verwenden
                            if hasattr(self, '_sensors') and sensor_id in self._sensors:
                                sensor_obj = self._sensors[sensor_id]
                                sensor_state = sensor_obj.state
                                state_str = "ON" if sensor_state else "OFF"
                            
                            self.mqtt_client.publish(
                                sensor_state_topic,
                                state_str,
                                qos=1,
                                retain=True
                            )
                            self.debug_send_msg(sensor_state_topic, state_str, retained=True, qos=1)
        except Exception as e:
            # Direktes Logging für kritische Fehler
            logger.error(f"Fehler beim Veröffentlichen aller States: {e}")

    def _restore_states(self):
        """Stellt die letzten bekannten Zustände wieder her"""
        self.debug_process_msg("Stelle letzte bekannte Zustände wieder her...")
        
        try:
            if hasattr(self, 'publish_debug_message'):
                self.publish_debug_message("Stelle Zustände wieder her...")
        except Exception as e:
            logger.error(f"Fehler beim Senden der Debug-Nachricht: {e}")
            
        restore_timeout = float(self.config['timeouts'].get('state_restore', 3.0))
        pending_states = {
            actor_id: actor_config 
            for actor_id, actor_config in self.config['actors'].items()
            if EntityTypeConfig.get_discovery_config(
                actor_config.get('entity_type', 'switch')
            ).get('state_topic')
        }
        
        def on_state_message(client, userdata, message):
            try:
                actor_id = message.topic.split('/')[-2]
                if actor_id in pending_states:
                    state_str = message.payload.decode().upper()
                    # Konvertiere MQTT State in internen State
                    self.restored_states[actor_id] = self._convert_command_to_internal(actor_id, state_str)
                    del pending_states[actor_id]
                    
                    self.debug_process_msg(f"Wiederhergestellter State für {actor_id}: {state_str}")
                    
                    try:
                        if hasattr(self, 'publish_debug_message'):
                            self.publish_debug_message(f"State für {actor_id} wiederhergestellt: {state_str}")
                    except Exception as e:
                        logger.error(f"Fehler beim Senden der Debug-Nachricht: {e}")
                    
                    if not pending_states:
                        self.restore_complete.set()
            except Exception as e:
                error_msg = f"Fehler beim Wiederherstellen des States: {e}"
                
                if hasattr(self, 'debug_error'):
                    self.debug_error(error_msg, e)
                
                # Direktes Logging für kritische Fehler
                logger.error(error_msg)
                
                try:
                    if hasattr(self, 'publish_debug_message'):
                        self.publish_debug_message(error_msg)
                except Exception as ex:
                    logger.error(f"Fehler beim Senden der Debug-Nachricht: {ex}")

        original_on_message = self.mqtt_client.on_message
        self.mqtt_client.on_message = on_state_message
        
        try:
            if not self.restore_complete.wait(timeout=restore_timeout):
                self.debug_process_msg("Timeout beim Wiederherstellen der States")
                
                try:
                    if hasattr(self, 'publish_debug_message'):
                        self.publish_debug_message("Timeout beim Wiederherstellen der States")
                except Exception as e:
                    logger.error(f"Fehler beim Senden der Debug-Nachricht: {e}")
                
                for actor_id, actor_config in pending_states.items():
                    entity_type = actor_config.get('entity_type', 'switch')
                    startup_state = actor_config.get('startup_state', 'OFF')
                    
                    # Konvertiere startup_state in internen Boolean basierend auf Entity Type
                    self.restored_states[actor_id] = EntityTypeConfig.convert_startup_state(
                        entity_type, startup_state
                    )
                    
                    self.debug_process_msg(f"Default State für {actor_id}: {startup_state}")
                    
                    try:
                        if hasattr(self, 'publish_debug_message'):
                            self.publish_debug_message(f"Default State für {actor_id}: {startup_state}")
                    except Exception as e:
                        logger.error(f"Fehler beim Senden der Debug-Nachricht: {e}")
        finally:
            self.mqtt_client.on_message = original_on_message

    def get_startup_state(self, actor_id: str) -> bool:
        """Ermittelt den Startup-State für einen Actor"""
        if actor_id not in self.config['actors']:
            if hasattr(self, 'debug_error'):
                self.debug_error(f"Kein Config-Eintrag für {actor_id}")
            logger.error(f"Kein Config-Eintrag für {actor_id}")
            return False
            
        actor_config = self.config['actors'][actor_id]
        entity_type = actor_config.get('entity_type', 'switch')
        startup_state = actor_config.get('startup_state', 'OFF')
        
        if startup_state == 'restore' and actor_id in self.restored_states:
            state = self.restored_states[actor_id]
            self.debug_process_msg(f"Wiederhergestellter State für {actor_id}: {state}")
            return state
            
        # Konvertiere startup_state in internen Boolean
        return EntityTypeConfig.convert_startup_state(entity_type, startup_state)
        
    def set_sensors(self, sensors):
        """Setzt die verfügbaren Sensoren für State-Updates"""
        self._sensors = sensors