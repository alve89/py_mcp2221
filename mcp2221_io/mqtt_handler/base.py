# mqtt_handler/base.py
# Version: 1.1.1

import paho.mqtt.client as mqtt
import threading
import time
from typing import Dict, Optional, Callable
from ..logging_config import logger
from ..mcp2221_patch import MCP2221Device
from ..mqtt_config import EntityTypeConfig

class MQTTHandler:
    def __init__(self, config: Dict):
        """Initialisiert den MQTT Handler"""
        self.config = config
        
        # Debug-Konfiguration initialisieren
        self._init_debug_config(config)
        
        self.mqtt_client = mqtt.Client()
        self.connected = threading.Event()
        self.restored_states: Dict[str, bool] = {}
        self.restore_complete = threading.Event()
        self._shutdown_flag = threading.Event()
        
        # Board Status
        self._board_status = False
        self._board_status_message = "Not initialized"
        self._board_status_timer = None
        self._mcp_device = MCP2221Device.get_instance()
        
        # MQTT Client Setup
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_publish = self._on_publish
        
        self.mqtt_client.reconnect_delay_set(
            min_delay=config['reconnect'].get('min_delay', 1),
            max_delay=config['reconnect'].get('max_delay', 30)
        )
        
        self.base_topic = config.get('base_topic', 'mcp2221')
        
        # Set last will
        self._setup_last_will()
        
        if 'username' in config and 'password' in config:
            self.mqtt_client.username_pw_set(config['username'], config['password'])
            
        self.ha_discovery_prefix = config.get('discovery_prefix', 'homeassistant')
        self.device_name = config.get('device_name', 'MCP2221 IO Controller')
        self.device_id = config.get('device_id', 'mcp2221_controller')
        self.command_callbacks: Dict[str, Callable] = {}
        
        self.debug_process_msg("MQTT Handler initialisiert")

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

    def connect(self):
        """Verbindet mit dem MQTT Broker"""
        try:
            self.debug_process_msg(f"Verbinde mit MQTT Broker {self.config['broker']}:{self.config['port']}")
            self.mqtt_client.connect(
                self.config['broker'],
                self.config['port'],
                keepalive=self.config['timeouts'].get('keepalive', 60)
            )
            self.mqtt_client.loop_start()
            
            if not self.connected.wait(timeout=self.config['timeouts'].get('connect', 5.0)):
                self.debug_error("Timeout beim Verbinden mit MQTT Broker")
                raise TimeoutError("Timeout beim Verbinden mit MQTT Broker")
            
            # Status-Aktualisierung
            status, message = self._mcp_device.check_board_status()
            self._board_status = status
            self._board_status_message = message
            
            # Status publizieren
            self.mqtt_client.publish(
                f"{self.base_topic}/status",
                "online",
                qos=1,
                retain=True
            )
            self.debug_send_msg(f"{self.base_topic}/status", "online", retained=True, qos=1)
            
            self.publish_board_status()
            self.debug_process_msg("MQTT Verbindung hergestellt")
            self.publish_debug_message("MQTT Verbindung hergestellt")
            
            self.publish_all_states()
            
            # Discovery
            self.mqtt_client.loop_start()
            time.sleep(1)
            self.publish_discoveries()
            
        except Exception as e:
            error_msg = f"MQTT Verbindungsfehler: {e}"
            self.debug_error(error_msg, e)
            self.publish_debug_message(error_msg)
            raise

    def disconnect(self):
        """Trennt die Verbindung zum MQTT Broker"""
        try:
            # Signal an alle Threads zum Beenden
            self._shutdown_flag.set()
            
            # Status auf offline setzen
            if self.connected.is_set():
                try:
                    self.mqtt_client.publish(
                        f"{self.base_topic}/status",
                        "offline",
                        qos=1,
                        retain=True
                    )
                    self.mqtt_client.publish(
                        f"{self.base_topic}/board_status/state",
                        "offline",
                        qos=1,
                        retain=True
                    )
                except:
                    pass  # Ignoriere Fehler beim finalen Publish
            
            # Warte kurz auf ausstehende Publishes
            timeout = self.config['timeouts'].get('disconnect', 0.5)
            disconnect_start = time.time()
            
            # Versuche graceful disconnect mit Timeout
            try:
                self.mqtt_client.disconnect()
                time_left = max(0, timeout - (time.time() - disconnect_start))
                if time_left > 0:
                    time.sleep(time_left)
            except:
                pass  # Ignoriere Fehler beim Disconnect
            
            # Force Stop des Loop nach Timeout
            try:
                self.mqtt_client.loop_stop(force=True)
            except:
                pass  # Ignoriere Fehler beim Loop Stop
            
            # Cleanup
            self.connected.clear()
            self.debug_process_msg("MQTT Verbindung getrennt")
            
        except Exception as e:
            self.debug_error(f"Fehler beim Trennen der MQTT Verbindung: {e}")
            # Stelle sicher, dass der Loop gestoppt wird
            try:
                self.mqtt_client.loop_stop(force=True)
            except:
                pass