# mqtt_handler/states.py
# Version: 1.1.0

import threading
import time
from typing import Dict
from ..logging_config import logger
from ..mqtt_config import EntityTypeConfig

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
                        self.publish_debug_message(
                            f"Board Status: {'Online' if status else 'Offline'} - {message}"
                        )
                        self.publish_all_states()
                    
                    # Regelmäßige Republizierung der States auch ohne Änderung
                    else:
                        self.publish_board_status()
                        self.publish_all_states()
                    
                    time.sleep(10)
                except Exception as e:
                    self.debug_error(f"Fehler im Board-Monitoring: {e}", e)
                    if not self._shutdown_flag.is_set():
                        time.sleep(30)  # Längere Pause bei Fehler
                        
        self._board_status_timer = threading.Thread(target=check_status, daemon=True)
        self._board_status_timer.start()
        self.debug_process_msg("Board-Monitoring Thread gestartet")

    def publish_board_status(self):
        """Veröffentlicht den Board-Status via MQTT"""
        if not self.connected.is_set():
            return
            
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

    def publish_all_states(self):
        """Aktualisiert die States aller Aktoren und Sensoren"""
        # Service Status
        service_topic = f"{self.base_topic}/status"
        self.mqtt_client.publish(
            service_topic,
            "online",
            qos=1,
            retain=True
        )
        self.debug_send_msg(service_topic, "online", retained=True, qos=1)
        
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
            
            # State-Topic nur für Entities mit State
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
            for sensor_id in self.config['sensors'].keys():
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
                
                # State-Topic für Sensoren (immer OFF bei Initialisierung)
                sensor_state_topic = f"{self.base_topic}/{sensor_id}/state"
                self.mqtt_client.publish(
                    sensor_state_topic,
                    "OFF",
                    qos=1,
                    retain=True
                )
                self.debug_send_msg(sensor_state_topic, "OFF", retained=True, qos=1)

    def _restore_states(self):
        """Stellt die letzten bekannten Zustände wieder her"""
        self.debug_process_msg("Stelle letzte bekannte Zustände wieder her...")
        self.publish_debug_message("Stelle Zustände wieder her...")
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
                    self.publish_debug_message(f"State für {actor_id} wiederhergestellt: {state_str}")
                    
                    if not pending_states:
                        self.restore_complete.set()
            except Exception as e:
                error_msg = f"Fehler beim Wiederherstellen des States: {e}"
                self.debug_error(error_msg, e)
                self.publish_debug_message(error_msg)

        original_on_message = self.mqtt_client.on_message
        self.mqtt_client.on_message = on_state_message
        
        try:
            if not self.restore_complete.wait(timeout=restore_timeout):
                self.debug_process_msg("Timeout beim Wiederherstellen der States")
                self.publish_debug_message("Timeout beim Wiederherstellen der States")
                for actor_id, actor_config in pending_states.items():
                    entity_type = actor_config.get('entity_type', 'switch')
                    startup_state = actor_config.get('startup_state', 'OFF')
                    
                    # Konvertiere startup_state in internen Boolean basierend auf Entity Type
                    self.restored_states[actor_id] = EntityTypeConfig.convert_startup_state(
                        entity_type, startup_state
                    )
                    
                    self.debug_process_msg(f"Default State für {actor_id}: {startup_state}")
                    self.publish_debug_message(f"Default State für {actor_id}: {startup_state}")
        finally:
            self.mqtt_client.on_message = original_on_message

    def get_startup_state(self, actor_id: str) -> bool:
        """Ermittelt den Startup-State für einen Actor"""
        if actor_id not in self.config['actors']:
            self.debug_error(f"Kein Config-Eintrag für {actor_id}")
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