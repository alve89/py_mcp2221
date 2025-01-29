# mqtt_handler.py
# Version: 1.5.0

import paho.mqtt.client as mqtt
import json
from typing import Dict, Callable
import time
import threading
from .logging_config import logger
from .mcp2221_patch import MCP2221Device

class EntityTypeConfig:
    """Konfigurationsklasse für Entity Types"""
    TYPES = {
        'switch': {
            'discovery_type': 'switch',
            'states': {
                True: 'ON',
                False: 'OFF'
            },
            'commands': {
                'ON': True,
                'OFF': False
            },
            'discovery_config': {
                'state_topic': True,
                'command_topic': True,
                'payload_on': 'ON',
                'payload_off': 'OFF',
                'state_on': 'ON',
                'state_off': 'OFF',
                'optimistic': False
            },
            'startup_state_map': {
                'on': True,
                'off': False
            }
        },
        'button': {
            'discovery_type': 'button',
            'states': {},  # Buttons haben keinen State
            'commands': {
                'ON': True,
                'PRESS': True  # Alternative Command
            },
            'discovery_config': {
                'command_topic': True,
                'payload_press': 'ON'
            },
            'startup_state_map': {
                'on': True,
                'off': False
            }
        },
        'lock': {
            'discovery_type': 'lock',
            'states': {
                True: 'LOCKED',
                False: 'UNLOCKED'
            },
            'commands': {
                'LOCK': True,
                'UNLOCK': False
            },
            'discovery_config': {
                'state_topic': True,
                'command_topic': True,
                'payload_lock': 'LOCK',
                'payload_unlock': 'UNLOCK',
                'state_locked': 'LOCKED',
                'state_unlocked': 'UNLOCKED',
                'optimistic': False
            },
            'startup_state_map': {
                'locked': True,
                'unlocked': False
            }
        }
    }

    @classmethod
    def get_config(cls, entity_type: str) -> dict:
        """Gibt die Konfiguration für einen Entity Type zurück"""
        return cls.TYPES.get(entity_type.lower(), cls.TYPES['switch'])

    @classmethod
    def convert_to_mqtt_state(cls, entity_type: str, internal_state: bool) -> str:
        """Konvertiert einen internen State in einen MQTT State"""
        config = cls.get_config(entity_type)
        return config['states'].get(internal_state, 'OFF')

    @classmethod
    def convert_to_internal_state(cls, entity_type: str, mqtt_command: str) -> bool:
        """Konvertiert einen MQTT Command in einen internen State"""
        config = cls.get_config(entity_type)
        return config['commands'].get(mqtt_command.upper(), False)

    @classmethod
    def convert_startup_state(cls, entity_type: str, startup_state: str) -> bool:
        """Konvertiert einen Startup State String in einen internen Boolean State"""
        config = cls.get_config(entity_type)
        startup_state = startup_state.lower()
        return config['startup_state_map'].get(startup_state, False)

    @classmethod
    def get_discovery_config(cls, entity_type: str) -> dict:
        """Gibt die Discovery-Konfiguration für einen Entity Type zurück"""
        config = cls.get_config(entity_type)
        return config['discovery_config']

    @classmethod
    def get_discovery_type(cls, entity_type: str) -> str:
        """Gibt den Discovery Type für einen Entity Type zurück"""
        config = cls.get_config(entity_type)
        return config['discovery_type']

class MQTTHandler:
    def __init__(self, config: Dict):
        self.config = config
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
        
        # Set last will for device status and board status
        self._setup_last_will()
        
        if 'username' in config and 'password' in config:
            self.mqtt_client.username_pw_set(config['username'], config['password'])
            
        self.ha_discovery_prefix = config.get('discovery_prefix', 'homeassistant')
        self.device_name = config.get('device_name', 'MCP2221 IO Controller')
        self.device_id = config.get('device_id', 'mcp2221_controller')
        self.command_callbacks: Dict[str, Callable] = {}

    def _setup_last_will(self):
        """Konfiguriert Last Will and Testament"""
        # LWT für Service-Status
        self.mqtt_client.will_set(
            f"{self.base_topic}/status",
            "offline",
            qos=1,
            retain=True
        )
        
        # LWT für Board-Status
        self.mqtt_client.will_set(
            f"{self.base_topic}/board_status/state",
            "offline",
            qos=1,
            retain=True
        )

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
                        logger.debug(f"Board Status geändert: {status} - {message}")
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
                    logger.error(f"Fehler im Board-Monitoring: {e}")
                    if not self._shutdown_flag.is_set():
                        time.sleep(30)  # Längere Pause bei Fehler
                        
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

    def publish_debug_message(self, message: str):
        """Veröffentlicht Debug-Nachrichten via MQTT"""
        if not self.connected.is_set():
            return
            
        topic = f"{self.base_topic}/debug"
        self.mqtt_client.publish(topic, message, qos=1, retain=True)

    def publish_all_states(self):
        """Aktualisiert die States aller Aktoren und Sensoren"""
        # Service Status
        self.mqtt_client.publish(
            f"{self.base_topic}/status",
            "online",
            qos=1,
            retain=True
        )
        
        # Actors
        for actor_id, actor_config in self.config['actors'].items():
            entity_type = actor_config.get('entity_type', 'switch')
            discovery_config = EntityTypeConfig.get_discovery_config(entity_type)
            
            # Status-Topic für alle Entities
            self.mqtt_client.publish(
                f"{self.base_topic}/{actor_id}/status",
                "online" if self._board_status else "offline",
                qos=1,
                retain=True
            )
            
            # State-Topic nur für Entities mit State
            if discovery_config.get('state_topic'):
                self.mqtt_client.publish(
                    f"{self.base_topic}/{actor_id}/state",
                    self._convert_internal_to_state(actor_id, False),
                    qos=1,
                    retain=True
                )

        # Sensoren
        if 'sensors' in self.config:
            for sensor_id in self.config['sensors'].keys():
                # Status-Topic für Sensoren
                self.mqtt_client.publish(
                    f"{self.base_topic}/{sensor_id}/status",
                    "online" if self._board_status else "offline",
                    qos=1,
                    retain=True
                )
                # State-Topic für Sensoren (immer OFF bei Initialisierung)
                self.mqtt_client.publish(
                    f"{self.base_topic}/{sensor_id}/state",
                    "OFF",
                    qos=1,
                    retain=True
                )
                
    def register_command_callback(self, actor_id: str, callback: Callable[[str, str], None]):
        """Registriert einen Callback für Commands"""
        logger.debug(f"Registriere Command Callback für {actor_id}")
        self.command_callbacks[actor_id] = callback

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
                "sw_version": "1.5.0"
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
                "sw_version": "1.5.0"
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

    def connect(self):
        """Verbindet mit dem MQTT Broker"""
        try:
            logger.debug(f"Verbinde mit MQTT Broker {self.config['broker']}:{self.config['port']}")
            self.mqtt_client.connect(
                self.config['broker'],
                self.config['port'],
                keepalive=self.config['timeouts'].get('keepalive', 60)
            )
            self.mqtt_client.loop_start()
            
            if not self.connected.wait(timeout=self.config['timeouts'].get('connect', 5.0)):
                raise TimeoutError("Timeout beim Verbinden mit MQTT Broker")
            
            # Sofortige Statusprüfung und -publikation
            status, message = self._mcp_device.check_board_status()
            self._board_status = status
            self._board_status_message = message
            
            # Publiziere Service-Status
            self.mqtt_client.publish(
                f"{self.base_topic}/status",
                "online",
                qos=1,
                retain=True
            )
            
            # Publiziere Board-Status
            self.publish_board_status()
            
            logger.debug("MQTT Verbindung hergestellt")
            self.publish_debug_message("MQTT Verbindung hergestellt")
            
            # Publiziere alle States
            self.publish_all_states()
            
            # Discovery erst nach erfolgreicher Verbindung
            time.sleep(1)  # Kurze Pause für Stabilität
            self.publish_discoveries()
            
        except Exception as e:
            error_msg = f"MQTT Verbindungsfehler: {e}"
            logger.error(error_msg)
            self.publish_debug_message(error_msg)
            raise

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

    def _restore_states(self):
        """Stellt die letzten bekannten Zustände wieder her"""
        logger.debug("Stelle letzte bekannte Zustände wieder her...")
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
                    logger.debug(f"Wiederhergestellter State für {actor_id}: {state_str}")
                    self.publish_debug_message(f"State für {actor_id} wiederhergestellt: {state_str}")
                    
                    if not pending_states:
                        self.restore_complete.set()
            except Exception as e:
                error_msg = f"Fehler beim Wiederherstellen des States: {e}"
                logger.error(error_msg)
                self.publish_debug_message(error_msg)

        original_on_message = self.mqtt_client.on_message
        self.mqtt_client.on_message = on_state_message
        
        try:
            if not self.restore_complete.wait(timeout=restore_timeout):
                logger.warning("Timeout beim Wiederherstellen der States")
                self.publish_debug_message("Timeout beim Wiederherstellen der States")
                for actor_id, actor_config in pending_states.items():
                    entity_type = actor_config.get('entity_type', 'switch')
                    startup_state = actor_config.get('startup_state', 'OFF')
                    
                    # Konvertiere startup_state in internen Boolean basierend auf Entity Type
                    self.restored_states[actor_id] = EntityTypeConfig.convert_startup_state(
                        entity_type, startup_state
                    )
                    
                    logger.debug(f"Default State für {actor_id}: {startup_state}")
                    self.publish_debug_message(f"Default State für {actor_id}: {startup_state}")
        finally:
            self.mqtt_client.on_message = original_on_message

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
            msg = f"Board nicht verfügbar - Kommando für {actor_id} kann nicht gesendet werden"
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

    def get_startup_state(self, actor_id: str) -> bool:
        """Ermittelt den Startup-State für einen Actor"""
        if actor_id not in self.config['actors']:
            logger.warning(f"Kein Config-Eintrag für {actor_id}")
            return False
            
        actor_config = self.config['actors'][actor_id]
        entity_type = actor_config.get('entity_type', 'switch')
        startup_state = actor_config.get('startup_state', 'OFF')
        
        if startup_state == 'restore' and actor_id in self.restored_states:
            state = self.restored_states[actor_id]
            logger.debug(f"Wiederhergestellter State für {actor_id}: {state}")
            return state
            
        # Konvertiere startup_state in internen Boolean
        return EntityTypeConfig.convert_startup_state(entity_type, startup_state)

    def disconnect(self):
        """Trennt die MQTT-Verbindung"""
        try:
            logger.debug("Sende Offline-Status...")
            
            # Set debug sensor offline
            self.mqtt_client.publish(
                f"{self.base_topic}/debug",
                "System wird heruntergefahren",
                qos=1,
                retain=True
            )
            
            # Set board status to offline first
            self.mqtt_client.publish(
                f"{self.base_topic}/board_status/state",
                "offline",
                qos=1,
                retain=True
            )
            
            # Set device status to offline
            self.mqtt_client.publish(
                f"{self.base_topic}/status",
                "offline",
                qos=1,
                retain=True
            )
            
            # Set all actors to offline and their states to off/unlocked
            for actor_id, actor_config in self.config['actors'].items():
                self.mqtt_client.publish(
                    f"{self.base_topic}/{actor_id}/status",
                    "offline",
                    qos=1,
                    retain=True
                )
                
                # Nur State setzen wenn Entity einen State hat
                entity_type = actor_config.get('entity_type', 'switch')
                if EntityTypeConfig.get_discovery_config(entity_type).get('state_topic'):
                    self.mqtt_client.publish(
                        f"{self.base_topic}/{actor_id}/state",
                        self._convert_internal_to_state(actor_id, False),
                        qos=1,
                        retain=True
                    )
            
            # Wait for messages to be sent
            time.sleep(self.config['timeouts'].get('disconnect', 0.5))
            
            logger.debug("Stoppe MQTT Client...")
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logger.debug("MQTT Verbindung getrennt")
        except Exception as e:
            logger.error(f"Fehler beim Trennen der MQTT-Verbindung: {e}")