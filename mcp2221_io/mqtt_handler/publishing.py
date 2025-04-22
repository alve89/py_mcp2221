# mqtt_handler/publishing.py
# Version: 1.7.0

import paho.mqtt.client as mqtt
import json
import time
import os
from ..logging_config import logger

class MQTTPublishingMixin:
    """Mixin-Klasse für MQTT Publishing Funktionalität"""
    
    def publish_state(self, actor_id: str, state: bool):
        """Veröffentlicht den State eines Actors"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Status für {actor_id} kann nicht gesendet werden"
            self.debug_error(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verfügbar - Status für {actor_id} kann nicht gesendet werden"
            self.debug_error(msg)
            return
            
        try:
            state_str = self._convert_internal_to_state(actor_id, state)
            topic = f"{self.base_topic}/{actor_id}/state"
            self.debug_process_msg(f"Publiziere State {state_str} für {actor_id}")
            
            result = self.mqtt_client.publish(topic, state_str, qos=1, retain=True)
            self.debug_send_msg(topic, state_str, retained=True, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.debug_process_msg(f"State für {actor_id} erfolgreich publiziert")
            else:
                msg = f"Fehler beim Publizieren des States für {actor_id}: {result.rc}"
                self.debug_error(msg)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des States: {e}"
            self.debug_error(error_msg, e)

    def publish_sensor_state(self, sensor_id: str, state: bool):
        """Veröffentlicht den State eines Sensors"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Sensor-Status für {sensor_id} kann nicht gesendet werden"
            self.debug_error(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verfügbar - Sensor-Status für {sensor_id} kann nicht gesendet werden"
            self.debug_error(msg)
            return
            
        if 'sensors' not in self.config or sensor_id not in self.config['sensors']:
            msg = f"Unbekannter Sensor {sensor_id}"
            self.debug_error(msg)
            return
            
        try:
            sensor_config = self.config['sensors'][sensor_id]
            entity_type = sensor_config.get('entity_type', 'binary_sensor')
            
            # Konvertiere bool state zu MQTT state (ON/OFF)
            state_str = "ON" if state else "OFF"
                
            topic = f"{self.base_topic}/{sensor_id}/state"
            self.debug_process_msg(f"Publiziere Sensor-State {state_str} für {sensor_id}")
            
            # Nachricht veröffentlichen
            result = self.mqtt_client.publish(topic, state_str, qos=1, retain=True)
            self.debug_send_msg(topic, state_str, retained=True, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.debug_process_msg(f"Sensor-State für {sensor_id} erfolgreich publiziert")
            else:
                msg = f"Fehler beim Publizieren des Sensor-States für {sensor_id}: {result.rc}"
                self.debug_error(msg)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des Sensor-States: {e}"
            self.debug_error(error_msg, e)

    def publish_command(self, actor_id: str, command: str):
        """Veröffentlicht ein Command für einen Actor"""
        if not self.connected.is_set():
            msg = f"MQTT nicht verbunden - Kommando für {actor_id} kann nicht gesendet werden"
            self.debug_error(msg)
            return
            
        if not self._board_status:
            msg = f"Board nicht verbunden - Kommando für {actor_id} kann nicht gesendet werden"
            self.debug_error(msg)
            return
            
        try:
            topic = f"{self.base_topic}/{actor_id}/set"
            self.debug_process_msg(f"Publiziere Kommando {command} für {actor_id}")
            
            result = self.mqtt_client.publish(topic, command, qos=1)
            self.debug_send_msg(topic, command, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.debug_process_msg(f"Kommando für {actor_id} erfolgreich publiziert")
            else:
                msg = f"Fehler beim Publizieren des Kommandos für {actor_id}: {result.rc}"
                self.debug_error(msg)
        except Exception as e:
            error_msg = f"Fehler beim Publizieren des Kommandos: {e}"
            self.debug_error(error_msg, e)

    def _publish_debug_message_impl(self, message: str):
        """Implementierung zum Veröffentlichen von Debug-Nachrichten via MQTT"""
        if not hasattr(self, 'connected') or not self.connected.is_set():
            return
            
        try:
            topic = f"{self.base_topic}/debug"
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            self.mqtt_client.publish(topic, formatted_message, qos=1, retain=True)
            self.debug_send_msg(topic, formatted_message, retained=True, qos=1)
        except Exception as e:
            # Keine Endlosschleife durch Debug-Aufrufe erzeugen
            logger.error(f"Fehler beim Publizieren der Debug-Nachricht: {e}")
            
    def force_publish_all_sensor_states(self):
        """Erzwingt die erneute Veröffentlichung aller Sensor-Zustände"""
        if not hasattr(self, '_sensors') or not self._sensors:
            self.debug_process_msg("Keine Sensoren verfügbar für Force-Publishing")
            return
            
        self.debug_process_msg(f"Erzwinge Veröffentlichung aller Sensor-Zustände ({len(self._sensors)} Sensoren)")
        
        # Überprüfen, ob wir im Debug-Modus sind
        debug_mode = os.environ.get('MCP2221_DEBUG', '0') == '1'
        
        for sensor_id, sensor in self._sensors.items():
            try:
                # Tiefere Diagnose durchführen
                if hasattr(sensor, 'test_pin_reading'):
                    test_result = sensor.test_pin_reading()
                    
                    # Nur im Debug-Modus loggen
                    if debug_mode:
                        logger.debug(f"[Sensor Diagnose] {sensor_id}: {test_result}")
                    
                    # Diagnoseinformationen als JSON veröffentlichen
                    if self.connected.is_set():
                        diag_topic = f"{self.base_topic}/{sensor_id}/diagnostic"
                        try:
                            diag_json = json.dumps(test_result)
                            self.mqtt_client.publish(diag_topic, diag_json, qos=1, retain=True)
                            if debug_mode:
                                logger.debug(f"[MQTT] Diagnose für {sensor_id} veröffentlicht")
                        except Exception as e:
                            logger.error(f"[MQTT] Fehler beim Veröffentlichen der Diagnose für {sensor_id}: {e}")
                    
                # Aktuellen Sensor-Zustand direkt lesen
                current_state = sensor.state
                
                # Explizit für das Logging - nur im Debug-Modus
                if debug_mode:
                    raw_state = sensor.get_raw_state() if hasattr(sensor, 'get_raw_state') else None
                    logger.debug(f"[Sensor Force-Publish] {sensor_id}: State={current_state}, Raw={raw_state}")
                
                # Zustand veröffentlichen
                self.publish_sensor_state(sensor_id, current_state)
                
            except Exception as e:
                logger.error(f"[Sensor Force-Publish] Fehler bei {sensor_id}: {e}")
                self.debug_error(f"Fehler beim Force-Publishing von Sensor {sensor_id}: {e}", e)
                
    def test_sensor_pins(self):
        """
        Führt einen umfassenden Test aller Sensor-Pins durch und veröffentlicht die Ergebnisse
        """
        if not hasattr(self, '_sensors') or not self._sensors:
            logger.warning("[Sensor Test] Keine Sensoren verfügbar für Test")
            return
            
        # Prüfen, ob wir im Debug-Modus sind
        debug_mode = os.environ.get('MCP2221_DEBUG', '0') == '1'
            
        if debug_mode:
            logger.info(f"[Sensor Test] Starte Test für {len(self._sensors)} Sensoren")
        
        # Test-Ergebnisse für alle Sensoren sammeln
        all_results = {}
        for sensor_id, sensor in self._sensors.items():
            try:
                if hasattr(sensor, 'test_pin_reading'):
                    result = sensor.test_pin_reading()
                    all_results[sensor_id] = result
                    
                    # Log-Ausführliches Ergebnis - nur im Debug-Modus
                    if debug_mode:
                        if result.get("success", False):
                            logger.info(f"[Sensor Test] {sensor_id}: Pin={result.get('pin')}, " +
                                       f"Raw={result.get('raw_value')}, Read={result.get('read_state')}, " +
                                       f"Current={result.get('current_state')}, Stable={result.get('stable_count')}")
                        else:
                            logger.error(f"[Sensor Test] {sensor_id}: Fehler - {result.get('error')}")
                else:
                    if debug_mode:
                        logger.warning(f"[Sensor Test] {sensor_id}: Test-Methode nicht verfügbar")
            except Exception as e:
                if debug_mode:
                    logger.error(f"[Sensor Test] Fehler beim Testen von {sensor_id}: {e}")
                all_results[sensor_id] = {"error": str(e), "success": False}
        
        # Gesamtergebnis als JSON
        try:
            if self.connected.is_set():
                diag_topic = f"{self.base_topic}/sensor_test_results"
                diag_json = json.dumps(all_results)
                self.mqtt_client.publish(diag_topic, diag_json, qos=1, retain=True)
                if debug_mode:
                    logger.info(f"[Sensor Test] Ergebnisse veröffentlicht unter {diag_topic}")
        except Exception as e:
            if debug_mode:
                logger.error(f"[Sensor Test] Fehler beim Veröffentlichen der Gesamtergebnisse: {e}")
        
        return all_results