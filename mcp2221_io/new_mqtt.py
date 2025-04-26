# mcp2221_io/new_mqtt.py

import paho.mqtt.client as mqtt
import time
import json
from termcolor import colored
from typing import Dict, Any, Optional, Callable
from mcp2221_io.new_core import get_logger

logger = get_logger()

class MQTTClient:
    """MQTT-Client für die Kommunikation mit Home Assistant.
    
    Diese Klasse ist nur für die Verbindung und den Nachrichtenversand zuständig.
    Die Logik zur Bestimmung, wann Nachrichten gesendet werden sollen, liegt im IOController.
    """
    
    def __init__(self, mqtt_config, logging_config):
        """Initialisiert den MQTT-Client."""
        
        logger.info(colored("MQTT-Client wird initialisiert.", 'cyan'))
        
        self.logging_config = logging_config

        # # MQTT-Konfiguration aus der Config extrahieren
        self.broker = mqtt_config.get("broker", "localhost")
        self.port = mqtt_config.get("port", 1883)
        self.username = mqtt_config.get("username")
        self.password = mqtt_config.get("password")
        self.base_topic = mqtt_config.get("base_topic", "mcp2221")
        
        # # Timeouts und Reconnect-Konfiguration
        timeouts = mqtt_config.get("timeouts", {})
        reconnect = mqtt_config.get("reconnect", {})
        
        self.connect_timeout = timeouts.get("connect", 5.0)
        self.keepalive = timeouts.get("keepalive", 60)
        
        self.reconnect_min_delay = reconnect.get("min_delay", 1)
        self.reconnect_max_delay = reconnect.get("max_delay", 30)
        self.reconnect_delay = self.reconnect_min_delay
        
        # MQTT-Client initialisieren
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Benutzeranmeldedaten setzen, falls vorhanden
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
        
        # Status-Variablen
        self.connected = False
        self.last_connection_attempt = 0
        self.subscriptions = {}  # Topic -> Callback-Funktion
        
        logger.info(colored("MQTT-Client wurde initialisiert und konfiguriert.", 'cyan'))


    def connect(self) -> bool:
        """Stellt eine Verbindung zum MQTT-Broker her.
        
        Returns:
            bool: True, wenn die Verbindung erfolgreich war, sonst False
        """
        if self.connected:
            return True
        
        # Prüfen, ob die Reconnect-Verzögerung eingehalten werden soll
        current_time = time.monotonic()
        if current_time - self.last_connection_attempt < self.reconnect_delay:
            return False
        
        self.last_connection_attempt = current_time
        
        try:
            logger.info(colored("Verbindung zum MQTT-Broker " + self.broker + ":" + str(self.port) + " wird hergestellt...", 'cyan'))
            self.client.connect(self.broker, self.port, self.keepalive)
            self.client.loop_start()
            
            # Warten bis die Verbindung hergestellt ist (oder Timeout)
            timeout_time = current_time + self.connect_timeout
            while not self.connected and current_time < timeout_time:
                time.sleep(0.1)
                current_time = time.monotonic()
            
            if not self.connected:
                logger.error(colored("Timeout beim Verbinden mit MQTT-Broker  " + self.broker + ":" + self.port))
                self._handle_connection_failure()
                return False
            
            logger.info(colored("Verbindung zum MQTT-Broker " + self.broker + ":" + str(self.port) + " hergestellt", 'cyan'))
            
            # Alle zuvor registrierten Subscriptions wiederherstellen
            self._restore_subscriptions()
            
            return True
            
        except Exception as e:
            logger.error(colored("Fehler beim Verbinden mit MQTT-Broker: " + str(e), 'cyan'))
            self._handle_connection_failure()
            return False
    
    def disconnect(self) -> None:
        """Trennt die Verbindung zum MQTT-Broker."""
        if self.connected:
            logger.debug(colored("Verbindung zum MQTT-Broker wird getrennt", 'cyan'))
            try:
                self.client.disconnect()
                self.client.loop_stop()
                logger.info(colored("MQTT-Verbindung getrennt", 'cyan'))
            except Exception as e:
                logger.error(colored("Fehler beim Trennen der MQTT-Verbindung: " + str(e), 'cyan'))
        
        self.connected = False
    
    def update(self) -> None:
        """Aktualisiert den MQTT-Client und prüft die Verbindung.
        
        Diese Funktion sollte regelmäßig in der Hauptschleife aufgerufen werden.
        """
        # Verbindung prüfen und ggf. wiederherstellen
        if not self.connected:
            self.connect()
    
    def publish(self, topic: str, payload: str, retain: bool = False, skip_prefix: bool = False) -> bool:
        """Veröffentlicht eine Nachricht an ein MQTT-Topic.
        
        Args:
            topic: Das MQTT-Topic
            payload: Die zu veröffentlichende Nachricht
            retain: Ob die Nachricht beibehalten werden soll
            skip_prefix: Wenn True, wird der base_topic nicht vorangestellt (für Discovery-Topics)
            
        Returns:
            bool: True, wenn die Nachricht erfolgreich veröffentlicht wurde, sonst False
        """
        if not self.connected:
            if self.logging_config['send']:
                logger.warning(f"Kann Nachricht nicht veröffentlichen: Keine MQTT-Verbindung")
            return False
        
        try:
            # Vollständiges Topic zusammensetzen, außer wenn skip_prefix True ist
            full_topic = topic if skip_prefix else f"{self.base_topic}/{topic}"
            
            # Nachricht veröffentlichen
            result = self.client.publish(full_topic, payload, retain=retain)
            
            # Ergebnis prüfen
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                if self.logging_config['send']:
                    logger.debug(colored("MQTT-Nachricht veröffentlicht: " + full_topic + " = " + payload, 'cyan'))
                return True
            else:
                logger.error(colored("Fehler beim Veröffentlichen der MQTT-Nachricht: " + mqtt.error_string(result.rc), 'cyan'))
                return False
                
        except Exception as e:
            logger.error(colored("Fehler beim Veröffentlichen der MQTT-Nachricht: " + str(e), 'cyan'))
            return False
    
    def subscribe(self, topic: str, callback: Callable[[str, str], None]) -> bool:
        """Abonniert ein MQTT-Topic und registriert einen Callback.
        
        Args:
            topic: Das MQTT-Topic (ohne base_topic)
            callback: Die Callback-Funktion, die aufgerufen wird, wenn eine Nachricht empfangen wird.
                      Die Funktion sollte zwei Parameter annehmen: topic und payload.
            
        Returns:
            bool: True, wenn das Abonnement erfolgreich war, sonst False
        """
        # Abonnement speichern, unabhängig vom Verbindungsstatus
        self.subscriptions[topic] = callback
        
        if not self.connected:
            return False
        
        try:
            # Vollständiges Topic zusammensetzen
            full_topic = f"{self.base_topic}/{topic}"
            
            # Topic abonnieren
            result = self.client.subscribe(full_topic)
            
            # Ergebnis prüfen
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                if self.logging_config['process']:
                    logger.debug(f"MQTT-Topic abonniert: {full_topic}")
                return True
            else:
                logger.error(colored("Fehler beim Abonnieren des MQTT-Topics: " + mqtt.error_string(result[0]), 'cyan'))
                return False
                
        except Exception as e:
            logger.error(colored("Fehler beim Abonnieren des MQTT-Topics: " + str(e), 'cyan'))
            return False
    
    def _on_connect(self, client, userdata, flags, rc) -> None:
        """Callback für erfolgreiche Verbindung."""
        if rc == 0:
            self.connected = True
            self.reconnect_delay = self.reconnect_min_delay  # Zurücksetzen des Reconnect-Delays
            
            if self.logging_config['process']:
                logger.info(colored("Verbunden mit MQTT-Broker mit Ergebnis: " + str(rc), 'cyan'))
            
            # Abonnements wiederherstellen
            self._restore_subscriptions()
        else:
            logger.error(colored("Verbindung zum MQTT-Broker fehlgeschlagen mit Ergebnis: " + str(rc), 'cyan'))
            self._handle_connection_failure()
    
    def _on_disconnect(self, client, userdata, rc) -> None:
        """Callback für Verbindungstrennung."""
        self.connected = False
        
        if rc != 0:
            if self.logging_config['process']:
                logger.warning("Unerwartete Trennung vom MQTT-Broker: " + str(rc), 'cyan')
        else:
            if self.logging_config['process']:
                logger.debug(colored("Planmäßige Trennung vom MQTT-Broker", 'cyan'))
    
    def _on_message(self, client, userdata, msg) -> None:
        """Callback für eingehende Nachrichten."""
        try:
            # Prefix entfernen, um den Basis-Topic zu identifizieren
            if not msg.topic.startswith(f"{self.base_topic}/"):
                return
            
            # Topic ohne Basis-Prefix extrahieren
            relative_topic = msg.topic[len(self.base_topic) + 1:]
            
            # Payload dekodieren
            payload = msg.payload.decode()
            
            if self.logging_config['receive']:
                logger.debug(colored(f"MQTT-Nachricht empfangen: {msg.topic} = {payload}", 'cyan'))
            
            # Prüfen, ob ein Callback für dieses Topic registriert ist
            for subscribed_topic, callback in self.subscriptions.items():
                # Einfacher Wildcard-Support für +
                if '+' in subscribed_topic:
                    topic_parts = subscribed_topic.split('/')
                    relative_parts = relative_topic.split('/')
                    
                    if len(topic_parts) != len(relative_parts):
                        continue
                    
                    match = True
                    for i, part in enumerate(topic_parts):
                        if part != '+' and part != relative_parts[i]:
                            match = False
                            break
                    
                    if match:
                        callback(relative_topic, payload)
                        break
                
                # Exakte Übereinstimmung
                elif subscribed_topic == relative_topic:
                    callback(relative_topic, payload)
                    break
                
        except Exception as e:
            logger.error(colored(f"Fehler bei der Verarbeitung der MQTT-Nachricht: {e}", 'cyan'))
    
    def _restore_subscriptions(self) -> None:
        """Stellt alle gespeicherten Subscriptions wieder her."""
        for topic in self.subscriptions.keys():
            full_topic = f"{self.base_topic}/{topic}"
            result = self.client.subscribe(full_topic)
            
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                if self.logging_config['process']:
                    logger.debug(colored("MQTT-Topic wiederhergestellt: " + full_topic, 'cyan'))
            else:
                logger.error(colored("Fehler beim Wiederherstellen des MQTT-Topics: " + mqtt.error_string(result[0]), 'cyan'))
    
    def _handle_connection_failure(self) -> None:
        """Behandelt einen Verbindungsfehler und passt das Reconnect-Delay an."""
        # Erhöht das Reconnect-Delay exponentiell bis zum Maximum
        self.reconnect_delay = min(self.reconnect_delay * 2, self.reconnect_max_delay)
        logger.debug(colored("Reconnect-Delay auf " + str(self.reconnect_delay) + " Sekunden erhöht", 'cyan'))