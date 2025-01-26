import paho.mqtt.client as mqtt
import json
from typing import Dict, Callable
import time
import threading
from .logging_config import logger
from .mcp2221_patch import MCP2221Device

class MQTTHandler:
    def __init__(self, config: Dict):
        self.config = config
        self.mqtt_client = mqtt.Client()
        self.connected = threading.Event()
        self.restored_states: Dict[str, bool] = {}
        self.restore_complete = threading.Event()
        
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
        self.mqtt_client.will_set(
            f"{self.base_topic}/status",
            "offline",
            qos=1,
            retain=True
        )
        
        if 'username' in config and 'password' in config:
            self.mqtt_client.username_pw_set(config['username'], config['password'])
            
        self.ha_discovery_prefix = config.get('discovery_prefix', 'homeassistant')
        self.device_name = config.get('device_name', 'MCP2221 IO Controller')
        self.device_id = config.get('device_id', 'mcp2221_controller')
        self.command_callbacks: Dict[str, Callable] = {}

    def start_board_monitoring(self):
        """Startet das Board-Monitoring"""
        def check_status():
            while self.connected.is_set():
                status, message = self._mcp_device.check_board_status()
                if status != self._board_status or message != self._board_status_message:
                    self._board_status = status
                    self._board_status_message = message
                    self.publish_board_status()
                time.sleep(10)  # Reduziert auf 10 Sekunden
                
        self._board_status_timer = threading.Thread(target=check_status, daemon=True)
        self._board_status_timer.start()

    def publish_board_status(self):
        """Veröffentlicht den Board-Status via MQTT"""
        if not self.connected.is_set():
            return
            
        status_topic = f"{self.base_topic}/board_status/state"
        message_topic = f"{self.base_topic}/board_status/message"
        
        self.mqtt_client.publish(
            status_topic,
            "online" if self._board_status else "offline",
            qos=1,
            retain=True
        )
        self.mqtt_client.publish(
            message_topic,
            self._board_status_message,
            qos=1,
            retain=True
        )

    def publish_all_states(self):
        """Aktualisiert die States aller Aktoren"""
        for actor_id in self.config['actors'].keys():
            topic = f"{self.base_topic}/{actor_id}/status"
            state = "online" if self._board_status else "offline"
            self.mqtt_client.publish(topic, state, qos=1, retain=True)

    def register_command_callback(self, actor_id: str, callback: Callable[[str, str], None]):
        logger.debug(f"Registriere Command Callback für {actor_id}")
        self.command_callbacks[actor_id] = callback

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.debug("MQTT Verbindung erfolgreich")
            self.connected.set()
            
            self._restore_states()
            self.mqtt_client.publish(f"{self.base_topic}/status", "online", qos=1, retain=True)
            
            # Abonniere Topics
            topics = []
            for actor_id in self.config['actors'].keys():
                command_topic = f"{self.base_topic}/{actor_id}/set"
                state_topic = f"{self.base_topic}/{actor_id}/state"
                topics.extend([(command_topic, 1), (state_topic, 1)])
                logger.debug(f"Abonniere {command_topic} und {state_topic}")
            
            if topics:
                self.mqtt_client.subscribe(topics)

    def _restore_states(self):
        logger.debug("Stelle letzte bekannte Zustände wieder her...")
        restore_timeout = float(self.config['timeouts'].get('state_restore', 3.0))
        pending_states = set(self.config['actors'].keys())
        
        def on_state_message(client, userdata, message):
            try:
                actor_id = message.topic.split('/')[-2]
                if actor_id in pending_states:
                    state_str = message.payload.decode().upper()
                    self.restored_states[actor_id] = (state_str == "ON")
                    pending_states.remove(actor_id)
                    logger.debug(f"Wiederhergestellter State für {actor_id}: {state_str}")
                    
                    if not pending_states:
                        self.restore_complete.set()
            except Exception as e:
                logger.error(f"Fehler beim Wiederherstellen des States: {e}")

        original_on_message = self.mqtt_client.on_message
        self.mqtt_client.on_message = on_state_message
        
        try:
            if not self.restore_complete.wait(timeout=restore_timeout):
                logger.warning("Timeout beim Wiederherstellen der States")
                for actor_id in pending_states:
                    startup_state = self.config['actors'][actor_id].get('startup_state', 'off')
                    if startup_state in ['on', 'off']:
                        self.restored_states[actor_id] = (startup_state == 'on')
                        logger.debug(f"Default State für {actor_id}: {startup_state}")
        finally:
            self.mqtt_client.on_message = original_on_message

    def _on_disconnect(self, client, userdata, rc):
        logger.debug(f"MQTT Verbindung getrennt mit Code {rc}")
        self.connected.clear()

    def _on_message(self, client, userdata, message):
        try:
            topic = message.topic
            payload = message.payload.decode()
            logger.debug(f"MQTT Nachricht empfangen: {topic} = {payload}")
            
            topic_parts = topic.split('/')
            if len(topic_parts) == 3 and topic_parts[2] == 'set':
                actor_id = topic_parts[1]
                if actor_id in self.command_callbacks and self._board_status:
                    logger.debug(f"Führe Callback für {actor_id} aus mit Wert {payload}")
                    self.command_callbacks[actor_id](actor_id, payload)
                else:
                    if not self._board_status:
                        logger.warning(f"Board nicht verfügbar - Kommando für {actor_id} wird ignoriert")
                    else:
                        logger.warning(f"Kein Callback für {actor_id} registriert")
        except Exception as e:
            logger.error(f"Fehler bei der Nachrichtenverarbeitung: {e}")

    def _on_publish(self, client, userdata, mid):
        logger.debug(f"MQTT Nachricht {mid} erfolgreich veröffentlicht")

    def publish_state(self, actor_id: str, state: bool):
        if not self.connected.is_set():
            logger.warning(f"MQTT nicht verbunden - Status für {actor_id} kann nicht gesendet werden")
            return
            
        if not self._board_status:
            logger.warning(f"Board nicht verfügbar - Status für {actor_id} kann nicht gesendet werden")
            return
            
        state_str = "ON" if state else "OFF"
        topic = f"{self.base_topic}/{actor_id}/state"
        logger.debug(f"Publiziere State {state_str} für {actor_id}")
        try:
            result = self.mqtt_client.publish(topic, state_str, qos=1, retain=True)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"State für {actor_id} erfolgreich publiziert")
            else:
                logger.warning(f"Fehler beim Publizieren des States für {actor_id}: {result.rc}")
        except Exception as e:
            logger.error(f"Fehler beim Publizieren des States: {e}")

    def publish_command(self, actor_id: str, command: str):
        if not self.connected.is_set():
            logger.warning(f"MQTT nicht verbunden - Kommando für {actor_id} kann nicht gesendet werden")
            return
            
        if not self._board_status:
            logger.warning(f"Board nicht verfügbar - Kommando für {actor_id} kann nicht gesendet werden")
            return
            
        topic = f"{self.base_topic}/{actor_id}/set"
        logger.debug(f"Publiziere Kommando {command} für {actor_id}")
        try:
            result = self.mqtt_client.publish(topic, command, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Kommando für {actor_id} erfolgreich publiziert")
            else:
                logger.warning(f"Fehler beim Publizieren des Kommandos für {actor_id}: {result.rc}")
        except Exception as e:
            logger.error(f"Fehler beim Publizieren des Kommandos: {e}")

    def connect(self):
        try:
            logger.debug(f"Verbinde mit MQTT Broker {self.config['broker']}:{self.config['port']}")
            self.mqtt_client.connect(
                self.config['broker'],
                self.config['port'],
                keepalive=self.config['timeouts'].get('keepalive', 60)
            )
            self.mqtt_client.loop_start()
            
            if not self.connected.wait(timeout=self.config['timeouts'].get('connect', 5.0)):
                raise Exception("Timeout beim Verbinden mit MQTT Broker")
                
            logger.debug("MQTT Verbindung hergestellt")
            time.sleep(1)
            
            self.publish_discoveries()
            
        except Exception as e:
            logger.error(f"MQTT Verbindungsfehler: {e}")
            raise

    def publish_discoveries(self):
        if not self.connected.is_set():
            logger.error("MQTT nicht verbunden - Discovery nicht möglich")
            return
            
        logger.debug("Starte Home Assistant Auto Discovery")
        
        # Board Status Discovery
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
            "device_class": "connectivity"
        }
        
        self.mqtt_client.publish(
            config_topic,
            json.dumps(payload),
            qos=1,
            retain=True
        )
        
        # Actor Discoveries
        for actor_id, actor_config in self.config['actors'].items():
            config_topic = f"{self.ha_discovery_prefix}/switch/{self.device_id}/{actor_id}/config"
            entity_type = actor_config.get('entity_type', 'switch').lower()
            
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
                ],
                "state_topic": f"{self.base_topic}/{actor_id}/state",
                "command_topic": f"{self.base_topic}/{actor_id}/set",
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
                "optimistic": False
            }
            
            if entity_type == 'button':
                config_topic = f"{self.ha_discovery_prefix}/button/{self.device_id}/{actor_id}/config"
                payload.update({
                    "payload_press": "ON",
                    "press_action_topic": f"{self.base_topic}/{actor_id}/set"
                })
                payload.pop("state_topic", None)
                payload.pop("state_on", None)
                payload.pop("state_off", None)
            
            logger.debug(f"Sende Discovery für {actor_id} (Typ: {entity_type})")
            result = self.mqtt_client.publish(
                config_topic,
                json.dumps(payload),
                qos=1,
                retain=True
            )
            
            if result.is_published():
                logger.debug(f"Discovery für {actor_id} erfolgreich gesendet")
            else:
                logger.warning(f"Timeout beim Senden der Discovery für {actor_id}")

    def get_startup_state(self, actor_id: str) -> bool:
        if actor_id not in self.config['actors']:
            logger.warning(f"Kein Config-Eintrag für {actor_id}")
            return False
            
        startup_state = self.config['actors'][actor_id].get('startup_state', 'off')
        
        if startup_state == 'restore':
            if actor_id in self.restored_states:
                state = self.restored_states[actor_id]
                logger.debug(f"Wiederhergestellter State für {actor_id}: {state}")
                return state
            logger.debug(f"Kein State wiederhergestellt für {actor_id}, verwende 'off'")
            return False
        else:
            state = (startup_state == 'on')
            logger.debug(f"Konfigurierter State für {actor_id}: {state}")
            return state

    def disconnect(self):
        try:
            logger.debug("Sende Offline-Status...")
            self.mqtt_client.publish(f"{self.base_topic}/status", "offline", qos=1, retain=True)
            time.sleep(self.config['timeouts'].get('disconnect', 0.5))
            
            logger.debug("Stoppe MQTT Client...")
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logger.debug("MQTT Verbindung getrennt")
        except Exception as e:
            logger.error(f"Fehler beim Trennen der MQTT-Verbindung: {e}")