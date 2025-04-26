# mqtt_handler/__init__.py
# Version: 1.8.0

import json
from typing import Dict, Optional, Callable
import paho.mqtt.client as mqtt
import threading
import time
from ..logging_config import logger
from ..mcp2221_patch import MCP2221Device
from ..mqtt_config import EntityTypeConfig
from .debug import MQTTDebugMixin
from .base import MQTTBaseMixin
from .callbacks import MQTTCallbacksMixin
from .discovery import MQTTDiscoveryMixin
from .publishing import MQTTPublishingMixin
from .states import MQTTStatesMixin
from .connection import MQTTConnectionMixin

# Direkter Print ohne Logger (für Boot-Nachrichten)
def direct_print(message):
    print(message)

class MQTTHandler(MQTTDebugMixin, MQTTBaseMixin, MQTTCallbacksMixin, MQTTDiscoveryMixin, 
                 MQTTPublishingMixin, MQTTStatesMixin, MQTTConnectionMixin):
    """MQTT Handler Hauptklasse"""
    
    def __init__(self, config: Dict, debug_config=None):
        """Initialisiert den MQTT Handler"""
        self.config = config
        
        # Debug-Konfiguration initialisieren
        if debug_config is None:
            debug_config = {}
            
        # Debug-Attribute direkt setzen
        self._init_debug_config(debug_config)
        
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
        direct_print("MQTT Handler initialisiert")
    
    def register_command_callback(self, actor_id: str, callback: Callable[[str, str], None]):
        """Registriert einen Callback für Commands"""
        self.debug_process_msg(f"Registriere Command Callback für {actor_id}")
        self.command_callbacks[actor_id] = callback
    
    def set_sensors(self, sensors):
        """Setzt die Sensor-Objekte für State-Updates"""
        self._sensors = sensors
        self.debug_process_msg(f"{len(sensors)} Sensoren für MQTT-Integration registriert")
        
    def set_controller(self, controller):
        """Setzt die Referenz zum Controller für Cross-Updates"""
        self._controller = controller
        self.debug_process_msg("Controller-Referenz für MQTT-Handler gesetzt")
        
    def refresh_all_states(self):
        """Aktualisiert alle Zustände (Sensoren, Cover, Aktoren)"""
        # Sensor-Zustände aktualisieren
        self.force_publish_all_sensor_states()
        
        # Cover-Zustände aktualisieren
        if hasattr(self, 'force_publish_all_cover_states'):
            self.force_publish_all_cover_states()
        
        # Board- und Service-Status aktualisieren
        self.publish_all_states(force_republish=True)