# mqtt_handler/debug.py
# Version: 1.5.0

import os
from ..logging_config import logger

class MQTTDebugMixin:
    """Mixin-Klasse für MQTT-Debugging-Funktionalität"""
    
    def _init_debug_config(self, config):
        """Initialisiert die Debug-Konfiguration"""
        debug_config = config.get('debugging', {})
        mqtt_debug = debug_config.get('mqtt', {})
        self.debug_config = mqtt_debug
        self.debug_process = mqtt_debug.get("process", False)
        self.debug_send = mqtt_debug.get("send", False)
        self.debug_receive = mqtt_debug.get("receive", False)
        
        # Debug-Modus aus Umgebungsvariable prüfen
        self.debug_mode = os.environ.get('MCP2221_DEBUG', '0') == '1'

    def debug_process_msg(self, message):
        """Debug-Ausgabe für MQTT-Prozess-Informationen"""
        if hasattr(self, 'debug_process') and self.debug_process:
            # Bei wichtigen Nachrichten auch im Nicht-Debug-Modus ausgeben, aber ohne Debug-Präfix
            if not self.debug_mode and (
                "Verbindung hergestellt" in message or 
                "initialisiert" in message or 
                "Verbindung fehlgeschlagen" in message
            ):
                # Wichtige Meldungen als INFO ohne Debug-Präfix
                print(message)
            else:
                # Debug-Nachrichten normal mit Debug-Präfix
                logger.debug(f"[MQTT] {message}")

    def debug_send_msg(self, topic, payload, retained=False, qos=0):
        """Debug-Ausgabe für gesendete MQTT-Nachrichten"""
        if hasattr(self, 'debug_send') and self.debug_send:
            # Verbesserte Ausgabe mit mehr Details
            retain_flag = "RETAINED" if retained else ""
            qos_info = f"QoS={qos}" if qos > 0 else ""
            
            # Format: [MQTT SEND] Topic=topic Payload=payload [RETAINED] [QoS=1]
            details = []
            if retain_flag:
                details.append(retain_flag)
            if qos_info:
                details.append(qos_info)
            
            details_str = f" [{' '.join(details)}]" if details else ""
            
            # Füge MQTT Message-Typ dem Topic hinzu (basierend auf Topic-Pattern)
            topic_parts = topic.split('/')
            msg_type = ""
            if len(topic_parts) >= 3:
                if topic_parts[-1] == "set":
                    msg_type = " [COMMAND]"
                elif topic_parts[-1] == "state":
                    msg_type = " [STATE]"
                elif "discovery" in topic or "config" in topic:
                    msg_type = " [DISCOVERY]"
                    
            logger.debug(f"[MQTT SEND] Topic={topic}{msg_type} Payload={payload}{details_str}")

    def debug_receive_msg(self, topic, payload):
        """Debug-Ausgabe für empfangene MQTT-Nachrichten"""
        if hasattr(self, 'debug_receive') and self.debug_receive:
            # Verbesserte Ausgabe mit mehr Details
            topic_parts = topic.split('/')
            msg_type = ""
            
            # Identifiziere Nachrichtentyp basierend auf Topic-Muster
            if len(topic_parts) >= 3:
                if topic_parts[-1] == "set":
                    msg_type = " [COMMAND]"
                elif topic_parts[-1] == "state":
                    msg_type = " [STATE]"
                elif "status" in topic_parts[-1]:
                    msg_type = " [STATUS]"
            
            # Target-Gerät identifizieren (wenn vorhanden)
            target = ""
            if len(topic_parts) >= 2 and topic_parts[0] == self.base_topic:
                target = f" [Device={topic_parts[1]}]"
                
            logger.debug(f"[MQTT RECV] Topic={topic}{msg_type}{target} Payload={payload}")

    def debug_error(self, message, exception=None):
        """Debug-Ausgabe für MQTT-Fehler"""
        # Fehler immer ausgeben, aber im Nicht-Debug-Modus ohne Debug-Präfix
        if not hasattr(self, 'debug_mode'):
            self.debug_mode = os.environ.get('MCP2221_DEBUG', '0') == '1'
            
        if not self.debug_mode:
            if exception:
                print(f"MQTT-Fehler: {message}: {str(exception)}")
            else:
                print(f"MQTT-Fehler: {message}")
        else:
            if exception:
                logger.error(f"[MQTT ERROR] {message}: {exception}")
            else:
                logger.error(f"[MQTT ERROR] {message}")
                
    def publish_debug_message(self, message):
        """Veröffentlicht eine Debug-Nachricht über MQTT"""
        # Im Nicht-Debug-Modus unterdrücken wir das Protokollieren von Debug-Nachrichten
        if hasattr(self, 'debug_mode') and not self.debug_mode:
            return
            
        # Weiterleitung an die Implementierung in MQTTPublishingMixin
        if hasattr(self, '_publish_debug_message_impl'):
            self._publish_debug_message_impl(message)