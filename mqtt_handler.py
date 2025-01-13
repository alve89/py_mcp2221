# mcp2221_io/mqtt_handler.py

import paho.mqtt.client as mqtt
import json
from typing import Dict, Callable
import time
import threading

class MQTTHandler:
    def __init__(self, config: Dict):
        self.config = config
        self.mqtt_client = mqtt.Client()
        self.connected = threading.Event()
        self.restored_states: Dict[str, bool] = {}  # Speicher für wiederhergestellte States
        self.restore_complete = threading.Event()
        
        # Debug Callbacks
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_publish = self._on_publish
        
        # Client Konfiguration
        self.timeouts = config.get('timeouts', {
            'connect': 5.0,
            'state_restore': 3.0,
            'keepalive': 60,
            'discovery': 5.0,
            'disconnect': 0.5
        })
        self.reconnect = config.get('reconnect', {
            'min_delay': 1,
            'max_delay': 30
        })
        self.mqtt_client.reconnect_delay_set(
            min_delay=self.reconnect['min_delay'],
            max_delay=self.reconnect['max_delay']
        )
        self.base_topic = config.get('base_topic', 'mcp2221')
        
        # Last Will setzen
        self.mqtt_client.will_set(
            f"{self.base_topic}/status",
            "offline",
            qos=1,
            retain=True
        )
        
        # Auth wenn konfiguriert
        if 'username' in config and 'password' in config:
            self.mqtt_client.username_pw_set(config['username'], config['password'])
            
        self.ha_discovery_prefix = config.get('discovery_prefix', 'homeassistant')
        self.device_name = config.get('device_name', 'MCP2221 IO Controller')
        self.device_id = config.get('device_id', 'mcp2221_controller')
        self.command_callbacks: Dict[str, Callable] = {}

    def register_command_callback(self, actor_id: str, callback: Callable[[str, str], None]):
        """Registriert einen Callback für Actor-Kommandos"""
        print(f"[DEBUG] Registriere Command Callback für {actor_id}")
        self.command_callbacks[actor_id] = callback

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[DEBUG] MQTT Verbindung erfolgreich")
            self.connected.set()
            
            # Zuerst States wiederherstellen
            self._restore_states()
            
            # Dann erst Online-Status senden
            self.mqtt_client.publish(f"{self.base_topic}/status", "online", qos=1, retain=True)
                
            # Command Topics abonnieren
            for actor_id in self.config['actors'].keys():
                command_topic = f"{self.base_topic}/{actor_id}/set"
                state_topic = f"{self.base_topic}/{actor_id}/state"
                self.mqtt_client.subscribe([(command_topic, 1), (state_topic, 1)])
                print(f"[DEBUG] Subscribed to {command_topic} and {state_topic}")

    def _restore_states(self):
        """Stellt die letzten bekannten Zustände wieder her"""
        print("[DEBUG] Stelle letzte bekannte Zustände wieder her...")
        restore_timeout = self.timeouts['state_restore']
        pending_states = set(self.config['actors'].keys())
        
        def on_state_message(client, userdata, message):
            try:
                actor_id = message.topic.split('/')[-2]  # Topic-Format: base_topic/actor_id/state
                if actor_id in pending_states:
                    state_str = message.payload.decode().upper()
                    self.restored_states[actor_id] = (state_str == "ON")
                    pending_states.remove(actor_id)
                    print(f"[DEBUG] Wiederhergestellter State für {actor_id}: {state_str}")
                    
                    if not pending_states:  # Alle States wiederhergestellt
                        self.restore_complete.set()
            except Exception as e:
                print(f"[ERROR] Fehler beim Wiederherstellen des States: {e}")

        # Temporär Message-Handler überschreiben
        original_on_message = self.mqtt_client.on_message
        self.mqtt_client.on_message = on_state_message
        
        try:
            # Warte auf States
            if not self.restore_complete.wait(timeout=restore_timeout):
                print("[WARNING] Timeout beim Wiederherstellen der States")
                # Setze Default-States für nicht wiederhergestellte Aktoren
                for actor_id in pending_states:
                    startup_state = self.config['actors'][actor_id].get('startup_state', 'off')
                    if startup_state in ['on', 'off']:  # Ignoriere 'restore' hier
                        self.restored_states[actor_id] = (startup_state == 'on')
                        print(f"[DEBUG] Default State für {actor_id}: {startup_state}")
        finally:
            # Message-Handler zurücksetzen
            self.mqtt_client.on_message = original_on_message

    def _on_disconnect(self, client, userdata, rc):
        print(f"[DEBUG] MQTT Verbindung getrennt mit Code {rc}")
        self.connected.clear()

    def _on_message(self, client, userdata, message):
        """Verarbeitet eingehende MQTT Nachrichten"""
        try:
            topic = message.topic
            payload = message.payload.decode()
            print(f"[DEBUG] MQTT Nachricht empfangen: {topic} = {payload}")
            
            # Extrahiere actor_id aus dem Topic
            # Format: base_topic/actor_id/set
            topic_parts = topic.split('/')
            if len(topic_parts) == 3 and topic_parts[2] == 'set':
                actor_id = topic_parts[1]
                if actor_id in self.command_callbacks:
                    print(f"[DEBUG] Führe Callback für {actor_id} aus mit Wert {payload}")
                    self.command_callbacks[actor_id](actor_id, payload)
                else:
                    print(f"[WARNING] Kein Callback für {actor_id} registriert")
        except Exception as e:
            print(f"[ERROR] Fehler bei der Nachrichtenverarbeitung: {e}")

    def _on_publish(self, client, userdata, mid):
        print(f"[DEBUG] MQTT Nachricht {mid} erfolgreich veröffentlicht")

    def publish_state(self, actor_id: str, state: bool):
        """Veröffentlicht den Zustand eines Actors"""
        if not self.connected.is_set():
            print(f"[WARNING] MQTT nicht verbunden - Status für {actor_id} kann nicht gesendet werden")
            return
            
        state_str = "ON" if state else "OFF"
        topic = f"{self.base_topic}/{actor_id}/state"
        print(f"[DEBUG] Publiziere State {state_str} für {actor_id}")
        try:
            result = self.mqtt_client.publish(topic, state_str, qos=1, retain=True)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"[DEBUG] State für {actor_id} erfolgreich publiziert")
            else:
                print(f"[WARNING] Fehler beim Publizieren des States für {actor_id}: {result.rc}")
        except Exception as e:
            print(f"[ERROR] Fehler beim Publizieren des States: {e}")

    def publish_command(self, actor_id: str, command: str):
        """Veröffentlicht ein Kommando für einen Actor"""
        if not self.connected.is_set():
            print(f"[WARNING] MQTT nicht verbunden - Kommando für {actor_id} kann nicht gesendet werden")
            return
            
        topic = f"{self.base_topic}/{actor_id}/set"
        print(f"[DEBUG] Publiziere Kommando {command} für {actor_id}")
        try:
            result = self.mqtt_client.publish(topic, command, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"[DEBUG] Kommando für {actor_id} erfolgreich publiziert")
            else:
                print(f"[WARNING] Fehler beim Publizieren des Kommandos für {actor_id}: {result.rc}")
        except Exception as e:
            print(f"[ERROR] Fehler beim Publizieren des Kommandos: {e}")

    def connect(self):
        try:
            print(f"[DEBUG] Verbinde mit MQTT Broker {self.config['broker']}:{self.config['port']}")
            self.mqtt_client.connect(self.config['broker'], self.config['port'], 
                                   keepalive=self.timeouts['keepalive'])
            self.mqtt_client.loop_start()
            
            # Warte auf Verbindung
            if not self.connected.wait(timeout=self.timeouts['connect']):
                raise Exception("Timeout beim Verbinden mit MQTT Broker")
                
            print("[DEBUG] MQTT Verbindung hergestellt, warte 1 Sekunde...")
            time.sleep(1)  # Kurz warten für Stabilität
            
            # Erst jetzt Auto Discovery starten
            self.publish_discoveries()
            
        except Exception as e:
            print(f"[ERROR] MQTT Verbindungsfehler: {e}")
            raise

    def publish_discoveries(self):
        if not self.connected.is_set():
            print("[ERROR] MQTT nicht verbunden - Discovery nicht möglich")
            return
            
        print("[DEBUG] Starte Home Assistant Auto Discovery")
        
        for actor_id, actor_config in self.config['actors'].items():
            config_topic = f"{self.ha_discovery_prefix}/switch/{self.device_id}/{actor_id}/config"
            
            # Bestimme Entitätstyp, Standard ist 'switch'
            entity_type = actor_config.get('entity_type', 'switch').lower()
            
            # Payload basierend auf Entitätstyp anpassen
            payload = {
                "name": actor_config['description'],
                "unique_id": f"{self.device_id}_{actor_id}",
                "device": {
                    "identifiers": [
                        f"mcp2221_{self.device_id}"
                    ],
                    "name": self.device_name,
                    "model": "MCP2221 IO Controller",
                    "manufacturer": "Custom",
                    "sw_version": "1.0.0"
                },
                "availability": {
                    "topic": f"{self.base_topic}/status",
                    "payload_available": "online",
                    "payload_not_available": "offline"
                },
                "state_topic": f"{self.base_topic}/{actor_id}/state",
                "command_topic": f"{self.base_topic}/{actor_id}/set",
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
                "optimistic": True
            }
            
            # Konfiguriere Payload basierend auf Entitätstyp
            if entity_type == 'button':
                config_topic = f"{self.ha_discovery_prefix}/button/{self.device_id}/{actor_id}/config"
                payload.update({
                    # Button-spezifische Eigenschaften
                    "payload_press": "ON",
                    "press_action_topic": f"{self.base_topic}/{actor_id}/set"
                })
                # Entferne state-bezogene Felder für Button
                payload.pop("state_topic", None)
                payload.pop("state_on", None)
                payload.pop("state_off", None)
            
            print(f"[DEBUG] Sende Discovery für {actor_id} (Typ: {entity_type}) an {config_topic}")
            result = self.mqtt_client.publish(
                config_topic,
                json.dumps(payload),
                qos=1,
                retain=True
            )
            
            # Warte auf Bestätigung
            start_time = time.time()
            while not result.is_published() and (time.time() - start_time) < self.timeouts['discovery']:
                time.sleep(0.1)
                
            if result.is_published():
                print(f"[DEBUG] Discovery für {actor_id} erfolgreich gesendet")
            else:
                print(f"[WARNING] Timeout beim Senden der Discovery für {actor_id}")

    def get_startup_state(self, actor_id: str) -> bool:
        """Ermittelt den Startup-State für einen Aktor"""
        if actor_id not in self.config['actors']:
            print(f"[WARNING] Kein Config-Eintrag für {actor_id}")
            return False
            
        startup_state = self.config['actors'][actor_id].get('startup_state', 'off')
        
        if startup_state == 'restore':
            # Wenn State wiederhergestellt wurde, diesen verwenden
            if actor_id in self.restored_states:
                state = self.restored_states[actor_id]
                print(f"[DEBUG] Wiederhergestellter State für {actor_id}: {state}")
                return state
            # Sonst auf 'off' fallen
            print(f"[DEBUG] Kein State wiederhergestellt für {actor_id}, verwende 'off'")
            return False
        else:
            # Direkt konfigurierten State verwenden
            state = (startup_state == 'on')
            print(f"[DEBUG] Konfigurierter State für {actor_id}: {state}")
            return state

    def disconnect(self):
        try:
            print("[DEBUG] Sende Offline-Status...")
            self.mqtt_client.publish(f"{self.base_topic}/status", "offline", qos=1, retain=True)
            time.sleep(0.5)  # Kurz warten, damit die Nachricht noch rausgeht
            
            print("[DEBUG] Stoppe MQTT Client...")
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            print("[DEBUG] MQTT Verbindung getrennt")
        except Exception as e:
            print(f"[ERROR] Fehler beim Trennen der MQTT-Verbindung: {e}")