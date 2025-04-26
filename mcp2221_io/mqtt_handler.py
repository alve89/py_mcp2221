# mqtt_handler.py
# Version: 2.0.0

import json
import time
import threading
from typing import Dict, Optional, Callable, List, Tuple, Any
import paho.mqtt.client as mqtt

from .logging_config import logger, LogCategory
from .debug_mixin import DebugMixin
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
                True: 'UNLOCKED',
                False: 'LOCKED'
            },
            'commands': {
                'LOCK': False,      # LOCK Kommando setzt den internen State auf False
                'UNLOCK': True,     # UNLOCK Kommando setzt den internen State auf True
                # Zusätzliche Kommandos für Home Assistant Kompatibilität
                'LOCK': False,
                'UNLOCK': True
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
                'locked': False,    # "LOCKED" Startup-State setzt internen Value auf False
                'unlocked': True,   # "UNLOCKED" Startup-State setzt internen Value auf True
                'LOCKED': False,
                'UNLOCKED': True
            }
        },
        'cover': {
            'discovery_type': 'cover',
            'states': {
                'open': 'open',
                'closed': 'closed',
                'opening': 'opening',
                'closing': 'closing'
            },
            'commands': {
                'OPEN': 'OPEN',
                'CLOSE': 'CLOSE',
                'STOP': 'STOP'
            },
            'discovery_config': {
                'state_topic': True,
                'command_topic': True,
                'state_opening': 'opening',
                'state_closing': 'closing',
                'state_open': 'open',
                'state_closed': 'closed',
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'optimistic': False
            },
            'startup_state_map': {
                'open': 'open',
                'closed': 'closed',
                'opening': 'opening',
                'closing': 'closing'
            }
        },
        'binary_sensor': {
            'discovery_type': 'binary_sensor',
            'states': {
                True: 'ON',
                False: 'OFF'
            },
            'commands': {},  # Sensoren haben keine Commands
            'discovery_config': {
                'state_topic': True,
                'payload_on': 'ON',
                'payload_off': 'OFF'
            },
            'startup_state_map': {
                'on': True,
                'off': False
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
        startup_state = startup_state.upper()
        return config['startup_state_map'].get(startup_state.lower(), False)

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


class MQTTHandler(DebugMixin):
    """Zentralisierter MQTT Handler ohne separate Mixins"""
    
    def __init__(self, config: Dict, debug_config=None):
        """Initialisiert den MQTT Handler"""
        if debug_config is None:
            debug_config = {}
        
        # Debug-Konfiguration initialisieren
        self._init_debug_config(debug_config)
        
        # MQTT-Config speichern
        self.config = config
        
        # MQTT-Client initialisieren
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
        
        # Sensoren und Callbacks
        self._sensors = {}
        self._controller = None  # Referenz zum Controller für Cross-Updates
        self.command_callbacks = {}
        
        # MQTT Client Setup
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_publish = self._on_publish
        
        # Reconnect-Einstellungen
        reconnect_config = config.get('reconnect', {})
        min_delay = reconnect_config.get('min_delay', 1)
        max_delay = reconnect_config.get('max_delay', 30)
        
        self.mqtt_client.reconnect_delay_set(
            min_delay=min_delay,
            max_delay=max_delay
        )
        
        # Basis-Topic und Discovery-Einstellungen
        self.base_topic = config.get('base_topic', 'mcp2221')
        self.ha_discovery_prefix = config.get('discovery_prefix', 'homeassistant')
        self.device_name = config.get('device_name', 'MCP2221 IO Controller')
        self.device_id = config.get('device_id', 'mcp2221_controller')
        
        # Last Will and Testament einrichten
        self._setup_last_will()
        
        # Authentifizierung einrichten, wenn konfiguriert
        if 'username' in config and 'password' in config:
            self.mqtt_client.username_pw_set(config['username'], config['password'])
        
        # Initialisierung abgeschlossen
        logger.info("MQTT Handler initialisiert", LogCategory.MQTT)
    
    # =========== BASISOPERATIONEN ===========
    
    def _setup_last_will(self):
        """Konfiguriert Last Will and Testament"""
        # LWT für Service-Status
        self.mqtt_client.will_set(
            f"{self.base_topic}/status",
            "offline",
            qos=1,
            retain=True
        )
        self.debug_mqtt_process("Service-Status LWT konfiguriert")
        
        # LWT für Board-Status
        self.mqtt_client.will_set(
            f"{self.base_topic}/board_status/state",
            "offline",
            qos=1,
            retain=True
        )
        self.debug_mqtt_process("Board-Status LWT konfiguriert")
    
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
    
    # =========== VERBINDUNGSMANAGEMENT ===========
    
    def connect(self):
        """Verbindet mit dem MQTT Broker"""
        try:
            self.debug_mqtt_process(f"Verbinde mit MQTT Broker {self.config['broker']}:{self.config['port']}")
            self.mqtt_client.connect(
                self.config['broker'],
                self.config['port'],
                keepalive=self.config.get('timeouts', {}).get('keepalive', 60)
            )
            self.mqtt_client.loop_start()
            
            timeout = self.config.get('timeouts', {}).get('connect', 5.0)
            if not self.connected.wait(timeout=timeout):
                self.debug_mqtt_error("Timeout beim Verbinden mit MQTT Broker")
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
            self.debug_mqtt_send(f"{self.base_topic}/status", "online", retained=True, qos=1)
            
            self.publish_board_status()
            self.debug_mqtt_process("MQTT Verbindung hergestellt")
            
            # Debug-Nachricht veröffentlichen
            self.publish_debug_message("MQTT Verbindung hergestellt")
            
            self.publish_all_states()
            
            # Discovery
            time.sleep(1)
            self.publish_discoveries()
            
            # Board-Monitoring starten
            self.start_board_monitoring()
            
        except Exception as e:
            error_msg = f"MQTT Verbindungsfehler: {e}"
            self.debug_mqtt_error(error_msg, e)
            
            # Debug-Nachricht veröffentlichen
            try:
                self.publish_debug_message(error_msg)
            except Exception:
                pass
            
            raise
    
    def disconnect(self):
        """Trennt die Verbindung zum MQTT Broker"""
        self.debug_mqtt_process("Trenne MQTT-Verbindung")
        self._shutdown_flag.set()
        
        if hasattr(self, '_board_status_timer') and self._board_status_timer and self._board_status_timer.is_alive():
            self._board_status_timer.join(timeout=1.0)
        
        if self.connected.is_set():
            # Status auf offline setzen
            try:
                self.mqtt_client.publish(
                    f"{self.base_topic}/status",
                    "offline",
                    qos=1,
                    retain=True
                )
                self.debug_mqtt_send(f"{self.base_topic}/status", "offline", retained=True, qos=1)
                
                # Offline-Status für Board
                self.mqtt_client.publish(
                    f"{self.base_topic}/board_status/state",
                    "offline",
                    qos=1,
                    retain=True
                )
                
                # Warte kurz, damit die Nachricht gesendet werden kann
                time.sleep(self.config.get('timeouts', {}).get('disconnect', 0.5))
            except Exception as e:
                self.debug_mqtt_error(f"Fehler beim Setzen des Offline-Status: {e}", e)
            
            try:
                # Stoppe zuerst den Loop, dann trenne die Verbindung
                self.mqtt_client.loop_stop()
                
                # Verbindung mit kurzer Timeout trennen
                disconnect_timeout = self.config.get('timeouts', {}).get('disconnect', 0.5)
                self.mqtt_client.disconnect()
                
                # Warte kurz auf die Bestätigung der Trennung
                wait_start = time.time()
                while self.connected.is_set() and (time.time() - wait_start) < disconnect_timeout:
                    time.sleep(0.1)
                
                # Falls immer noch verbunden, manuell den Status zurücksetzen
                if self.connected.is_set():
                    self.connected.clear()
                    self.debug_mqtt_process("Verbindung manuell getrennt nach Timeout")
                
                logger.info("MQTT-Verbindung erfolgreich getrennt", LogCategory.MQTT)
            except Exception as e:
                self.debug_mqtt_error(f"Fehler beim Trennen der MQTT-Verbindung: {e}", e)
                
                # Stellen wir sicher, dass der Loop gestoppt ist
                try:
                    self.mqtt_client.loop_stop(force=True)
                except Exception:
                    pass
                
                # Stellen wir sicher, dass der Status zurückgesetzt ist
                self.connected.clear()
    
    # =========== CALLBACKS ===========
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback für erfolgreiche MQTT-Verbindung"""
        if rc == 0:
            self.debug_mqtt_process("MQTT Verbindung erfolgreich")
            self.connected.set()
            
            self._restore_states()
            self.mqtt_client.publish(f"{self.base_topic}/status", "online", qos=1, retain=True)
            self.debug_mqtt_send(f"{self.base_topic}/status", "online", retained=True, qos=1)
            
            # Subscribe to topics
            topics = []
            for actor_id, actor_config in self.config['actors'].items():
                entity_type = actor_config.get('entity_type', 'switch')
                discovery_config = EntityTypeConfig.get_discovery_config(entity_type)
                
                # Command Topic für alle Entities
                if discovery_config.get('command_topic'):
                    command_topic = f"{self.base_topic}/{actor_id}/set"
                    topics.append((command_topic, 1))
                    self.debug_mqtt_process(f"Topic zum Abonnieren vorbereitet: {command_topic}")
                
                # State Topic nur für Entities mit State
                if discovery_config.get('state_topic'):
                    state_topic = f"{self.base_topic}/{actor_id}/state"
                    topics.append((state_topic, 1))
                    self.debug_mqtt_process(f"Topic zum Abonnieren vorbereitet: {state_topic}")
            
            if topics:
                self.debug_mqtt_process(f"Abonniere {len(topics)} Topics...")
                self.mqtt_client.subscribe(topics)
                for topic, qos in topics:
                    self.debug_mqtt_process(f"Topic abonniert: {topic} (QoS: {qos})")
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
            self.debug_mqtt_error(f"MQTT Verbindung fehlgeschlagen: {error_msg}")
            
            # Fallback für kritische Fehler direkt über logger
            logger.error(f"MQTT Verbindung fehlgeschlagen: {error_msg}", LogCategory.MQTT)

    def _on_disconnect(self, client, userdata, rc):
        """Callback für MQTT-Verbindungstrennung"""
        if rc == 0:
            self.debug_mqtt_process("MQTT Verbindung ordnungsgemäß getrennt")
        else:
            self.debug_mqtt_process(f"MQTT Verbindung unerwartet getrennt mit Code {rc}")
            
        self.connected.clear()
        
        # Ensure board status is set to offline on disconnect
        try:
            offline_topic = f"{self.base_topic}/board_status/state"
            self.mqtt_client.publish(offline_topic, "offline", qos=1, retain=True)
            self.debug_mqtt_send(offline_topic, "offline", retained=True, qos=1)
        except Exception as e:
            # Direktes Logging bei kritischen Fehlern
            logger.error(f"Fehler beim Setzen des Offline-Status: {e}", LogCategory.MQTT)

    def _on_message(self, client, userdata, message):
        """Callback für eingehende MQTT-Nachrichten"""
        try:
            topic = message.topic
            payload = message.payload.decode()
            self.debug_mqtt_receive(topic, payload)
            
            topic_parts = topic.split('/')
            if len(topic_parts) == 3 and topic_parts[2] == 'set':
                actor_id = topic_parts[1]
                self.debug_mqtt_process(f"Command-Topic erkannt für {actor_id}: {payload}")
                
                if actor_id in self.command_callbacks:
                    if self._board_status:
                        self.debug_mqtt_process(f"Führe Callback für {actor_id} aus mit Wert {payload}")
                        self.command_callbacks[actor_id](actor_id, payload)
                    else:
                        error_msg = f"Board nicht verfügbar - Kommando für {actor_id} wird ignoriert"
                        self.debug_mqtt_error(error_msg)
                        self.publish_debug_message(error_msg)
                else:
                    self.debug_mqtt_error(f"Kein Callback für {actor_id} registriert")
            else:
                self.debug_mqtt_process(f"Keine Aktion für Topic {topic} definiert")
        except Exception as e:
            error_msg = f"Fehler bei der Nachrichtenverarbeitung: {e}"
            self.debug_mqtt_error(error_msg, e)
            
            # Direktes Logging für kritische Fehler
            logger.error(error_msg, LogCategory.MQTT)
            
            self.publish_debug_message(error_msg)
                    
    def _on_publish(self, client, userdata, mid):
        """Callback für erfolgreiche MQTT-Publizierung"""
        # Message-ID-Protokollierung nur im ausführlichen Debug-Modus aktivieren
        if self.debug_mqtt_send:
            # Nur im ausführlichen Debug-Modus loggen wir Message IDs
            self.debug_mqtt_process(f"MQTT Nachricht {mid} erfolgreich veröffentlicht")
    
    # =========== STATE MANAGEMENT ===========
    
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
                        self.debug_mqtt_process(f"Board Status geändert: {status} - {message}")
                        self.publish_board_status()
                        
                        # Debug-Nachricht senden
                        self.publish_debug_message(
                            f"Board Status: {'Online' if status else 'Offline'} - {message}"
                        )
                        
                        # Nur bei Statusänderung alle States republizieren
                        self.publish_all_states(force_republish=True)
                    
                    # Regelmäßige Republizierung NUR des Board-Status, nicht aller Actor-States
                    else:
                        self.publish_board_status()
                    
                    time.sleep(10)
                except Exception as e:
                    self.debug_mqtt_error(f"Fehler im Board-Monitoring: {e}", e)
                    
                    if not self._shutdown_flag.is_set():
                        time.sleep(30)  # Längere Pause bei Fehler
                        
        self._board_status_timer = threading.Thread(target=check_status, daemon=True)
        self._board_status_timer.start()
        logger.info("Board-Monitoring Thread gestartet", LogCategory.MQTT)

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
            self.debug_mqtt_send(status_topic, status_str, retained=True, qos=1)
            
            self.mqtt_client.publish(
                message_topic,
                self._board_status_message,
                qos=1,
                retain=True
            )
            self.debug_mqtt_send(message_topic, self._board_status_message, retained=True, qos=1)
        except Exception as e:
            # Direktes Logging für kritische Fehler
            logger.error(f"Fehler beim Veröffentlichen des Board-Status: {e}", LogCategory.MQTT)

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
            self.debug_mqtt_send(service_topic, "online", retained=True, qos=1)
            
            if force_republish:
                # Actors
                for actor_id, actor_config in self.config['actors'].items():
                    entity_type = actor_config.get('entity_type', 'switch').lower()
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
                    self.debug_mqtt_send(status_topic, status_str, retained=True, qos=1)
                    
                    # State-Topic nur für Entities mit State (aber NICHT command republizieren)
                    if discovery_config.get('state_topic'):
                        state_topic = f"{self.base_topic}/{actor_id}/state"
                        
                        # Spezialfall für Cover-Entities
                        if entity_type == 'cover':
                            # Für Cover den Standard-Zustand setzen (meist "closed")
                            state_str = actor_config.get('startup_state', 'closed')
                            self.mqtt_client.publish(
                                state_topic,
                                state_str,
                                qos=1,
                                retain=True
                            )
                            self.debug_mqtt_send(state_topic, state_str, retained=True, qos=1)
                        else:
                            # Für normale Entities den internen Boolean-State verwenden
                            state_str = self._convert_internal_to_state(actor_id, False)
                            self.mqtt_client.publish(
                                state_topic,
                                state_str,
                                qos=1,
                                retain=True
                            )
                            self.debug_mqtt_send(state_topic, state_str, retained=True, qos=1)

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
                        self.debug_mqtt_send(sensor_status_topic, status_str, retained=True, qos=1)
                        
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
                            self.debug_mqtt_send(sensor_state_topic, state_str, retained=True, qos=1)
        except Exception as e:
            # Direktes Logging für kritische Fehler
            logger.error(f"Fehler beim Veröffentlichen aller States: {e}", LogCategory.MQTT)

    def _restore_states(self):
        """Stellt die letzten bekannten Zustände wieder her"""
        self.debug_mqtt_process("Stelle letzte bekannte Zustände wieder her...")
        
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
                    
                    self.debug_mqtt_process(f"Wiederhergestellter State für {actor_id}: {state_str}")
                    self.publish_debug_message(f"State für {actor_id} wiederhergestellt: {state_str}")
                    
                    if not pending_states:
                        self.restore_complete.set()
            except Exception as e:
                error_msg = f"Fehler beim Wiederherstellen des States: {e}"
                self.debug_mqtt_error(error_msg, e)
                
                # Direktes Logging für kritische Fehler
                logger.error(error_msg, LogCategory.MQTT)
                self.publish_debug_message(error_msg)

        original_on_message = self.mqtt_client.on_message
        self.mqtt_client.on_message = on_state_message
        
        try:
            if not self.restore_complete.wait(timeout=restore_timeout):
                self.debug_mqtt_process("Timeout beim Wiederherstellen der States")
                self.publish_debug_message("Timeout beim Wiederherstellen der States")
                
                for actor_id, actor_config in pending_states.items():
                    entity_type = actor_config.get('entity_type', 'switch')
                    startup_state = actor_config.get('startup_state', 'OFF')
                    
                    # Spezialbehandlung für Cover
                    if entity_type.lower() == 'cover':
                        # Für Cover speichern wir den Startup-State als String
                        self.restored_states[actor_id] = startup_state
                    else:
                        # Konvertiere startup_state in internen Boolean basierend auf Entity Type
                        self.restored_states[actor_id] = EntityTypeConfig.convert_startup_state(
                            entity_type, startup_state
                        )
                    
                    self.debug_mqtt_process(f"Default State für {actor_id}: {startup_state}")
                    self.publish_debug_message(f"Default State für {actor_id}: {startup_state}")
        finally:
            self.mqtt_client.on_message = original_on_message

    def get_startup_state(self, actor_id: str) -> bool:
        """Ermittelt den Startup-State für einen Actor"""
        if actor_id not in self.config['actors']:
            self.debug_mqtt_error(f"Kein Config-Eintrag für {actor_id}")
            logger.error(f"Kein Config-Eintrag für {actor_id}", LogCategory.MQTT)
            return False
            
        actor_config = self.config['actors'][actor_id]
        entity_type = actor_config.get('entity_type', 'switch')
        
        # Spezialbehandlung für Cover
        if entity_type.lower() == 'cover':
            # Für Cover wird der Zustand durch die Sensoren bestimmt,
            # daher ist kein initialer State erforderlich
            return False
            
        startup_state = actor_config.get('startup_state', 'OFF')
        
        if startup_state == 'restore' and actor_id in self.restored_states:
            state = self.restored_states[actor_id]
            self.debug_mqtt_process(f"Wiederhergestellter State für {actor_id}: {state}")
            return state
            
        # Konvertiere startup_state in internen Boolean
        return EntityTypeConfig.convert_startup_state(entity_type, startup_state)
        
    # =========== DISCOVERY ===========
    
    def publish_discoveries(self):
        """Veröffentlicht die Discovery-Konfigurationen"""
        if not self.connected.is_set():
            self.debug_mqtt_error("MQTT nicht verbunden - Discovery nicht möglich")
            return
            
        try:
            self.debug_mqtt_process("Starte Home Assistant Auto Discovery")
            
            # Board Status Discovery
            self._publish_board_discovery()
            
            # Actor Discoveries
            for actor_id, actor_config in self.config['actors'].items():
                self._publish_actor_discovery(actor_id, actor_config)
                
            # Sensor Discoveries
            if 'sensors' in self.config:
                for sensor_id, sensor_config in self.config['sensors'].items():
                    self._publish_sensor_discovery(sensor_id, sensor_config)
                
            self.debug_mqtt_process("Home Assistant Auto Discovery abgeschlossen")
        except Exception as e:
            self.debug_mqtt_error(f"Fehler bei Discovery: {e}", e)

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
            self.debug_mqtt_process("Board Discovery-Konfiguration veröffentlicht")
            self.debug_mqtt_send(config_topic, json.dumps(payload), retained=True, qos=1)
        except Exception as e:
            self.debug_mqtt_error(f"Fehler bei Board-Discovery: {e}", e)

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
            
            # Spezifische Konfiguration für Cover-Entitäten
            if entity_type == 'cover':
                # Device-Klasse für Cover (z.B. garage, door, blind, ...)
                if 'device_class' in actor_config:
                    payload["device_class"] = actor_config['device_class']
            
            # Debug-Ausgabe generieren für vollständige Konfiguration
            self.debug_mqtt_process(f"Discovery-Konfiguration für {actor_id} ({entity_type})")
            
            # Veröffentlichen der Konfiguration
            self.mqtt_client.publish(
                config_topic,
                json.dumps(payload),
                qos=1,
                retain=True  # Retain auf True setzen für permanente Verfügbarkeit
            )
            self.debug_mqtt_process(f"Discovery-Konfiguration für Actor {actor_id} veröffentlicht")
            self.debug_mqtt_send(config_topic, json.dumps(payload), retained=True, qos=1)
        except Exception as e:
            self.debug_mqtt_error(f"Fehler bei Actor-Discovery {actor_id}: {e}", e)
        
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
            self.debug_mqtt_process(f"Discovery-Konfiguration für Sensor {sensor_id} veröffentlicht")
            self.debug_mqtt_send(config_topic, json.dumps(payload), retained=True, qos=1)
        except Exception as e:
            self.debug_mqtt_error(f"Fehler bei Sensor-Discovery {sensor_id}: {e}", e)
    
    # =========== PUBLISH OPERATIONS ===========
    
    def publish_state(self, actor_id: str, state: bool):
        """Veröffentlicht den State eines Actors"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Status für {actor_id} kann nicht gesendet werden"
            self.debug_mqtt_error(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verfügbar - Status für {actor_id} kann nicht gesendet werden"
            self.debug_mqtt_error(msg)
            return
            
        try:
            state_str = self._convert_internal_to_state(actor_id, state)
            topic = f"{self.base_topic}/{actor_id}/state"
            self.debug_mqtt_process(f"Publiziere State {state_str} für {actor_id}")
            
            result = self.mqtt_client.publish(topic, state_str, qos=1, retain=True)
            self.debug_mqtt_send(topic, state_str, retained=True, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.debug_mqtt_process(f"State für {actor_id} erfolgreich publiziert")
            else:
                msg = f"Fehler beim Publizieren des States für {actor_id}: {result.rc}"
                self.debug_mqtt_error(msg)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des States: {e}"
            self.debug_mqtt_error(error_msg, e)

    def publish_cover_state(self, cover_id: str, state: str):
        """Veröffentlicht den State eines Covers"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Cover-Status für {cover_id} kann nicht gesendet werden"
            self.debug_mqtt_error(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verfügbar - Cover-Status für {cover_id} kann nicht gesendet werden"
            self.debug_mqtt_error(msg)
            return
            
        if 'actors' not in self.config or cover_id not in self.config['actors']:
            msg = f"Unbekanntes Cover {cover_id}"
            self.debug_mqtt_error(msg)
            return
            
        try:
            actor_config = self.config['actors'][cover_id]
            entity_type = actor_config.get('entity_type', 'switch')
            
            if entity_type.lower() != 'cover':
                msg = f"{cover_id} ist kein Cover (Typ: {entity_type})"
                self.debug_mqtt_error(msg)
                return
                
            topic = f"{self.base_topic}/{cover_id}/state"
            self.debug_mqtt_process(f"Publiziere Cover-State {state} für {cover_id}")
            logger.info(f"Publiziere Cover-State: {cover_id} -> {state}", LogCategory.MQTT)
            
            # Nachricht veröffentlichen
            result = self.mqtt_client.publish(topic, state, qos=1, retain=True)
            self.debug_mqtt_send(topic, state, retained=True, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.debug_mqtt_process(f"Cover-State für {cover_id} erfolgreich publiziert")
                logger.info(f"Cover-State für {cover_id} erfolgreich publiziert", LogCategory.MQTT)
            else:
                msg = f"Fehler beim Publizieren des Cover-States für {cover_id}: {result.rc}"
                self.debug_mqtt_error(msg)
                logger.error(msg, LogCategory.MQTT)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des Cover-States: {e}"
            self.debug_mqtt_error(error_msg, e)
            logger.error(error_msg, LogCategory.MQTT)

    def publish_sensor_state(self, sensor_id: str, state: bool):
        """Veröffentlicht den State eines Sensors"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Sensor-Status für {sensor_id} kann nicht gesendet werden"
            self.debug_mqtt_error(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verfügbar - Sensor-Status für {sensor_id} kann nicht gesendet werden"
            self.debug_mqtt_error(msg)
            return
            
        if 'sensors' not in self.config or sensor_id not in self.config['sensors']:
            msg = f"Unbekannter Sensor {sensor_id}"
            self.debug_mqtt_error(msg)
            return
            
        try:
            sensor_config = self.config['sensors'][sensor_id]
            entity_type = sensor_config.get('entity_type', 'binary_sensor')
            
            # Konvertiere bool state zu MQTT state (ON/OFF)
            state_str = "ON" if state else "OFF"
            
            # Erweiterte Logging-Ausgabe
            logger.info(f"Sensor {sensor_id}: Publiziere State {state_str}", LogCategory.MQTT)
                
            topic = f"{self.base_topic}/{sensor_id}/state"
            self.debug_mqtt_process(f"Publiziere Sensor-State {state_str} für {sensor_id}")
            
            # Nachricht veröffentlichen
            result = self.mqtt_client.publish(topic, state_str, qos=1, retain=True)
            self.debug_mqtt_send(topic, state_str, retained=True, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.debug_mqtt_process(f"Sensor-State für {sensor_id} erfolgreich publiziert")
            else:
                msg = f"Fehler beim Publizieren des Sensor-States für {sensor_id}: {result.rc}"
                self.debug_mqtt_error(msg)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des Sensor-States: {e}"
            self.debug_mqtt_error(error_msg, e)

    def publish_command(self, actor_id: str, command: str):
        """Veröffentlicht ein Command für einen Actor"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Kommando für {actor_id} kann nicht gesendet werden"
            self.debug_mqtt_error(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verbunden - Kommando für {actor_id} kann nicht gesendet werden"
            self.debug_mqtt_error(msg)
            return
            
        try:
            topic = f"{self.base_topic}/{actor_id}/set"
            self.debug_mqtt_process(f"Publiziere Kommando {command} für {actor_id}")
            
            # Erweiterte Logging-Ausgabe
            logger.info(f"Command für {actor_id}: {command}", LogCategory.MQTT)
            
            result = self.mqtt_client.publish(topic, command, qos=1)
            self.debug_mqtt_send(topic, command, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.debug_mqtt_process(f"Kommando für {actor_id} erfolgreich publiziert")
            else:
                msg = f"Fehler beim Publizieren des Kommandos für {actor_id}: {result.rc}"
                self.debug_mqtt_error(msg)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des Kommandos: {e}"
            self.debug_mqtt_error(error_msg, e)

    def publish_debug_message(self, message: str):
        """Veröffentlicht eine Debug-Nachricht über MQTT"""
        if not self.connected.is_set():
            return
            
        try:
            topic = f"{self.base_topic}/debug"
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            self.mqtt_client.publish(topic, formatted_message, qos=1, retain=True)
            self.debug_mqtt_send(topic, formatted_message, retained=True, qos=1)
        except Exception as e:
            # Keine Endlosschleife durch Debug-Aufrufe erzeugen
            logger.error(f"Fehler beim Publizieren der Debug-Nachricht: {e}", LogCategory.MQTT)
    
    # =========== SENSORS & COVER OPERATIONS ===========
    
    def force_publish_all_sensor_states(self):
        """Erzwingt die erneute Veröffentlichung aller Sensor-Zustände"""
        if not hasattr(self, '_sensors') or not self._sensors:
            self.debug_mqtt_process("Keine Sensoren verfügbar für Force-Publishing")
            return
            
        self.debug_mqtt_process(f"Erzwinge Veröffentlichung aller Sensor-Zustände ({len(self._sensors)} Sensoren)")
        
        # Liste der Sensoren für bessere Log-Ausgabe erstellen
        sensor_names = list(self._sensors.keys())
        logger.info(f"Erzwinge Veröffentlichung aller Sensor-Zustände: {len(self._sensors)} Sensoren ({', '.join(sensor_names)})", LogCategory.MQTT)
        
        for sensor_id, sensor in self._sensors.items():
            try:
                # Tiefere Diagnose durchführen
                if hasattr(sensor, 'test_pin_reading'):
                    test_result = sensor.test_pin_reading()
                    
                    logger.debug(f"Sensor {sensor_id} (Pin: {test_result.get('pin')}): {test_result}", LogCategory.SENSOR)
                    
                    # Diagnoseinformationen als JSON veröffentlichen
                    if self.connected.is_set():
                        diag_topic = f"{self.base_topic}/{sensor_id}/diagnostic"
                        try:
                            diag_json = json.dumps(test_result)
                            self.mqtt_client.publish(diag_topic, diag_json, qos=1, retain=True)
                            logger.info(f"Diagnose für {sensor_id} (Pin: {test_result.get('pin')}) veröffentlicht", LogCategory.MQTT)
                        except Exception as e:
                            logger.error(f"Fehler beim Veröffentlichen der Diagnose für {sensor_id}: {e}", LogCategory.MQTT)
                    
                # Wenn möglich, erzwingend aktualisieren
                if hasattr(sensor, 'force_update'):
                    new_state = sensor.force_update()
                    logger.info(f"Sensor {sensor_id} force_update: {new_state}", LogCategory.MQTT)
                else:
                    # Aktuellen Sensor-Zustand direkt lesen
                    current_state = sensor.state
                    logger.info(f"Sensor {sensor_id} aktueller Zustand: {current_state}", LogCategory.MQTT)
                    
                    # Zustand veröffentlichen
                    self.publish_sensor_state(sensor_id, current_state)
                
            except Exception as e:
                logger.error(f"Fehler bei Force-Publishing von Sensor {sensor_id}: {e}", LogCategory.SENSOR)
                self.debug_mqtt_error(f"Fehler beim Force-Publishing von Sensor {sensor_id}: {e}", e)
                
    def test_sensor_pins(self):
        """
        Führt einen umfassenden Test aller Sensor-Pins durch und veröffentlicht die Ergebnisse
        """
        if not hasattr(self, '_sensors') or not self._sensors:
            logger.warning("Keine Sensoren verfügbar für Test", LogCategory.SENSOR)
            return
            
        logger.info(f"Starte Test für {len(self._sensors)} Sensoren", LogCategory.SENSOR)
        
        # Test-Ergebnisse für alle Sensoren sammeln
        all_results = {}
        for sensor_id, sensor in self._sensors.items():
            try:
                if hasattr(sensor, 'test_pin_reading'):
                    result = sensor.test_pin_reading()
                    all_results[sensor_id] = result
                    
                    # Detailliertes Log-Ergebnis
                    if result.get("success", False):
                        logger.info(f"{sensor_id}: Pin={result.get('pin')}, " +
                                   f"Raw={result.get('raw_value')}, Read={result.get('read_state')}, " +
                                   f"Current={result.get('current_state')}, Stable={result.get('stable_count')}", 
                                   LogCategory.SENSOR)
                    else:
                        logger.error(f"{sensor_id}: Fehler - {result.get('error')}", LogCategory.SENSOR)
                    
                    # Wenn der aktuelle Zustand nicht mit dem gelesenen Wert übereinstimmt,
                    # erzwinge ein Update
                    if result.get("success", False) and result.get("read_state") != result.get("current_state"):
                        logger.warning(f"{sensor_id} - Zustandsdiskrepanz: Read={result.get('read_state')}, " +
                                      f"Current={result.get('current_state')} - Erzwinge Update", 
                                      LogCategory.SENSOR)
                        if hasattr(sensor, 'force_update'):
                            new_state = sensor.force_update()
                            logger.info(f"{sensor_id} - Zustand nach erzwungenem Update: {new_state}", 
                                      LogCategory.SENSOR)
                else:
                    logger.warning(f"{sensor_id}: Test-Methode nicht verfügbar", LogCategory.SENSOR)
            except Exception as e:
                logger.error(f"Fehler beim Testen von {sensor_id}: {e}", LogCategory.SENSOR)
                all_results[sensor_id] = {"error": str(e), "success": False}
        
        # Gesamtergebnis als JSON
        try:
            if self.connected.is_set():
                diag_topic = f"{self.base_topic}/sensor_test_results"
                diag_json = json.dumps(all_results)
                self.mqtt_client.publish(diag_topic, diag_json, qos=1, retain=True)
                logger.info(f"Sensor-Test-Ergebnisse veröffentlicht unter {diag_topic}", LogCategory.SENSOR)
        except Exception as e:
            logger.error(f"Fehler beim Veröffentlichen der Gesamtergebnisse: {e}", LogCategory.SENSOR)
        
        # Nach dem Test alle Cover-Zustände aktualisieren, falls nötig
        try:
            if self._controller and hasattr(self._controller, 'initialize_covers'):
                logger.info(f"Initialisiere Cover-Zustände nach Sensor-Test", LogCategory.COVER)
                self._controller.initialize_covers()
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Cover-Zustände: {e}", LogCategory.COVER)
        
        return all_results
        
    def force_publish_all_cover_states(self):
        """
        Erzwingt die erneute Veröffentlichung aller Cover-Zustände
        """
        # Diese Methode benötigt Zugriff auf den Controller und seine Cover-Entitäten
        if not hasattr(self, '_controller') or not self._controller:
            logger.info("Kein Controller für Force-Publishing der Cover-Zustände verfügbar", LogCategory.MQTT)
            return
            
        controller = self._controller
        if not hasattr(controller, 'covers') or not controller.covers:
            logger.info("Keine Cover für Force-Publishing verfügbar", LogCategory.MQTT)
            return
            
        logger.info(f"Erzwinge Veröffentlichung aller Cover-Zustände: {len(controller.covers)} Cover", LogCategory.MQTT)
        
        # Jedes Cover initialisieren und Status aktualisieren
        controller.initialize_covers()
    
    # =========== REGISTRY / SETUP METHODS ===========
    
    def register_command_callback(self, actor_id: str, callback: Callable[[str, str], None]):
        """Registriert einen Callback für Commands"""
        self.debug_mqtt_process(f"Registriere Command Callback für {actor_id}")
        self.command_callbacks[actor_id] = callback
    
    def set_sensors(self, sensors):
        """Setzt die Sensor-Objekte für State-Updates"""
        self._sensors = sensors
        self.debug_mqtt_process(f"{len(sensors)} Sensoren für MQTT-Integration registriert")
        
    def set_controller(self, controller):
        """Setzt die Referenz zum Controller für Cross-Updates"""
        self._controller = controller
        self.debug_mqtt_process("Controller-Referenz für MQTT-Handler gesetzt")
        
    def refresh_all_states(self):
        """Aktualisiert alle Zustände (Sensoren, Cover, Aktoren)"""
        # Sensor-Zustände aktualisieren
        self.force_publish_all_sensor_states()
        
        # Cover-Zustände aktualisieren
        self.force_publish_all_cover_states()
        
        # Board- und Service-Status aktualisieren
        self.publish_all_states(force_republish=True)