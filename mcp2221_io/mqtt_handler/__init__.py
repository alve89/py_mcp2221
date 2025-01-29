# mqtt_handler/__init__.py
# Version: 1.1.1

from .base import MQTTHandler
from .callbacks import MQTTCallbacksMixin
from .discovery import MQTTDiscoveryMixin
from .publishing import MQTTPublishingMixin
from .states import MQTTStatesMixin
from .debug import MQTTDebugMixin

class MQTTHandler(MQTTHandler, 
                 MQTTDebugMixin,
                 MQTTCallbacksMixin,
                 MQTTDiscoveryMixin,
                 MQTTPublishingMixin,
                 MQTTStatesMixin):
    """MQTT Handler Hauptklasse mit allen Mixins"""
    
    def __init__(self, config: dict):
        """Initialisiert den MQTT Handler"""
        # Debug-Konfiguration zuerst initialisieren
        self._init_debug_config(config)
        
        # Basis-Handler initialisieren
        super().__init__(config)

__all__ = ['MQTTHandler']