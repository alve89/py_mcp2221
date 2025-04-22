# mqtt_handler/connection.py
# Version: 1.2.0

import time
from typing import Dict
from ..logging_config import logger

# Direkter Print ohne Logger (für Boot-Nachrichten)
def direct_print(message):
    print(message)

class MQTTConnectionMixin:
    """Mixin-Klasse für MQTT-Verbindungsfunktionalität"""
    
    def connect(self):
        """Verbindet mit dem MQTT Broker"""
        try:
            self.debug_process_msg(f"Verbinde mit MQTT Broker {self.config['broker']}:{self.config['port']}")
            self.mqtt_client.connect(
                self.config['broker'],
                self.config['port'],
                keepalive=self.config.get('timeouts', {}).get('keepalive', 60)
            )
            self.mqtt_client.loop_start()
            
            timeout = self.config.get('timeouts', {}).get('connect', 5.0)
            if not self.connected.wait(timeout=timeout):
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
            
            # Debug-Nachricht veröffentlichen wenn möglich
            try:
                if hasattr(self, 'publish_debug_message'):
                    self.publish_debug_message("MQTT Verbindung hergestellt")
            except Exception:
                pass
            
            self.publish_all_states()
            
            # Discovery
            time.sleep(1)
            self.publish_discoveries()
            
        except Exception as e:
            error_msg = f"MQTT Verbindungsfehler: {e}"
            self.debug_error(error_msg, e)
            
            # Debug-Nachricht veröffentlichen wenn möglich
            try:
                if hasattr(self, 'publish_debug_message'):
                    self.publish_debug_message(error_msg)
            except Exception:
                pass
            
            raise
    
    def disconnect(self):
        """Trennt die Verbindung zum MQTT Broker"""
        self.debug_process_msg("Trenne MQTT-Verbindung")
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
                self.debug_send_msg(f"{self.base_topic}/status", "offline", retained=True, qos=1)
                
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
                self.debug_error(f"Fehler beim Setzen des Offline-Status: {e}", e)
            
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
                    self.debug_process_msg("Verbindung manuell getrennt nach Timeout")
                
                direct_print("MQTT-Verbindung erfolgreich getrennt")
            except Exception as e:
                self.debug_error(f"Fehler beim Trennen der MQTT-Verbindung: {e}", e)
                
                # Stellen wir sicher, dass der Loop gestoppt ist
                try:
                    self.mqtt_client.loop_stop(force=True)
                except Exception:
                    pass
                
                # Stellen wir sicher, dass der Status zurückgesetzt ist
                self.connected.clear()