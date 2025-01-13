# mcp2221_io/mqtt_handler.py

import paho.mqtt.client as mqtt
import json
from typing import Dict
import time
import threading

class MQTTHandler:
    def __init__(self, config: Dict):
        self.config = config
        self.mqtt_client = mqtt.Client()
        self.connected = threading.Event()  # Flag für Verbindungsstatus
        
        # Debug Callbacks
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_publish = self._on_publish
        
        # Client Konfiguration
        self.mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
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

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[DEBUG] MQTT Verbindung erfolgreich")
            self.connected.set()  # Markiere als verbunden
            # Online-Status senden
            self.mqtt_client.publish(f"{self.base_topic}/status", "online", qos=1, retain=True)
        else:
            print(f"[ERROR] MQTT Verbindung fehlgeschlagen mit Code {rc}")
            self.connected.clear()

    def _on_disconnect(self, client, userdata, rc):
        print(f"[DEBUG] MQTT Verbindung getrennt mit Code {rc}")
        self.connected.clear()

    def _on_message(self, client, userdata, message):
        print(f"[DEBUG] MQTT Nachricht empfangen: {message.topic} = {message.payload}")

    def _on_publish(self, client, userdata, mid):
        print(f"[DEBUG] MQTT Nachricht {mid} erfolgreich veröffentlicht")

    def connect(self):
        try:
            print(f"[DEBUG] Verbinde mit MQTT Broker {self.config['broker']}:{self.config['port']}")
            self.mqtt_client.connect(self.config['broker'], self.config['port'], keepalive=60)
            self.mqtt_client.loop_start()
            
            # Warte auf Verbindung
            if not self.connected.wait(timeout=5.0):
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
            
            print(f"[DEBUG] Sende Discovery für {actor_id} an {config_topic}")
            result = self.mqtt_client.publish(
                config_topic,
                json.dumps(payload),
                qos=1,
                retain=True
            )
            
            # Warte auf Bestätigung
            start_time = time.time()
            while not result.is_published() and (time.time() - start_time) < 5:
                time.sleep(0.1)
                
            if result.is_published():
                print(f"[DEBUG] Discovery für {actor_id} erfolgreich gesendet")
            else:
                print(f"[WARNING] Timeout beim Senden der Discovery für {actor_id}")

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