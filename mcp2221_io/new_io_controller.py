# mcp2221_io/new_classes.py

import os
import time
import yaml
import digitalio
import board
import logging
import json
from termcolor import colored
from typing import Dict, List, Optional, Any
from mcp2221_io.new_io_actor import IOActor
from mcp2221_io.new_io_sensor import IOSensor
from mcp2221_io.new_io_device import IODevice
from mcp2221_io.new_core import logger, config


class IOController:
    """Controller zur Verwaltung von IO-Geräten basierend auf YAML-Konfiguration."""
    
    def __init__(self, mqtt_client=None):
        logger.info("IOController wird initialisiert.")
        self.actors = {}  # Speichert alle Aktoren nach Namen
        self.sensors = {}  # Speichert alle Sensoren nach Namen
        self.running = False      
        self.mqtt_client = mqtt_client  # MQTT-Client Referenz speichern

        if self.mqtt_client:
            self.mqtt_client.client.on_message = self.mqtt_client._on_message
 
    def setup_entities(self) -> bool:
        """Erstellt alle Geräte basierend auf der geladenen Konfiguration."""
        try:
            logger.info("Entitäten werden erstellt.")

            # Sensoren erstellen
            if 'sensors' in config:
                for sensor_id, sensor_config in config['sensors'].items():
                    if sensor_config.get('entity_type') == 'binary_sensor':
                        logger.debug(f"Entität {sensor_id} ist ein Sensor vom Typ '{sensor_config.get('entity_type')}'")
                        self._create_binary_sensor(sensor_id, sensor_config)
      
            # Aktoren erstellen
            if 'actors' in config:
                for actor_id, actor_config in config['actors'].items():
                    if actor_config.get('entity_type') == 'switch':
                        logger.debug(f"Entität {actor_id} ist ein Sensor vom Typ '{actor_config.get('entity_type')}'")
                        self._create_switch(actor_id, actor_config)
            
            logger.info(f"Geräte erfolgreich eingerichtet: {len(self.sensors)} Sensoren, {len(self.actors)} Aktoren")
            return True
        except Exception as e:
            print(f"Fehler beim Einrichten der Geräte: {e}")
            return False
    
    def _create_binary_sensor(self, sensor_id: str, config: Dict[str, Any]) -> None:
        """Erstellt einen binären Sensor basierend auf der Konfiguration."""
        sensor = IOSensor(
            pin=config['pin'],
            type=config['entity_type'],
            inverted=config.get('inverted', False),
            name=sensor_id,
            device_class=config.get('device_class', '')
        )
        
        # Zusätzliche Konfigurationen anwenden
        if 'poll_interval' in config:
            sensor.set_poll_interval(float(config['poll_interval']))
        if 'debounce_time' in config:
            sensor.set_debounce_time(float(config['debounce_time']))
        if 'stable_readings' in config:
            sensor.set_stable_readings(int(config['stable_readings']))
        
        self.sensors[sensor_id] = sensor
        logger.info(f"Sensor '{sensor_id}' erstellt (Pin: {config['pin']})")
    
    def _create_switch(self, actor_id: str, config: Dict[str, Any]) -> None:
        """Erstellt einen Schalter basierend auf der Konfiguration."""
        actor = IOActor(
            pin=config['pin'],
            type=config['entity_type'],
            inverted=config.get('inverted', False),
            name=actor_id,
            device_class=config.get('device_class', '')
        )
        
        # Automatische Rückstellung konfigurieren
        if config.get('auto_reset', False) and 'reset_delay' in config:
            actor.set_auto_reset(float(config['reset_delay']))
        
        # Initialen Zustand setzen
        if config.get('startup_state') == 'on':
            actor.turn_on()
        else:
            actor.turn_off()
            
        self.actors[actor_id] = actor
        logger.info(f"Aktor '{actor_id}' erstellt (Pin: {config['pin']})")
        
    def start(self) -> bool:
        """Startet den Controller und initialisiert alle Geräte."""
        
        if not self.setup_entities():
            return False
        
        self.running = True
        logger.info("IOController erfolgreich gestartet.")

        if self.mqtt_client and self.mqtt_client.connected:
            # Status online veröffentlichen
            self.mqtt_client.publish("status", "online", retain=True)
            logger.debug("MQTT Online-Status veröffentlicht.")

            # Home Assistant Auto-Discovery Konfiguration
            discovery_prefix = config.get_value("mqtt.discovery_prefix", "homeassistant")
            node_id = config.get_value("mqtt.node_id", "mcp2221")
            
            # Auto-Discovery für Sensoren
            for sensor_id, sensor in self.sensors.items():
                # Aktuellen Status veröffentlichen
                state_value = "ON" if sensor.state else "OFF"
                self.mqtt_client.publish(f"sensors/{sensor_id}/state", state_value, retain=True)
                
                # Auto-Discovery Payload für Sensor erstellen
                sensor_config = {
                    "name": sensor.name,
                    "unique_id": f"{node_id}_{sensor_id}",
                    "device_class": sensor.device_class if sensor.device_class else None,
                    "state_topic": f"{self.mqtt_client.base_topic}/sensors/{sensor_id}/state",
                    "availability_topic": f"{self.mqtt_client.base_topic}/status",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device": {
                        "identifiers": [f"{node_id}"],
                        "name": f"MCP2221 IO Controller",
                        "manufacturer": "Custom",
                        "model": "MCP2221 IO"
                    }
                }
                
                # Überprüfen der Konfiguration und Entfernen von None-Werten
                sensor_config = {k: v for k, v in sensor_config.items() if v is not None}
                
                # Auto-Discovery Nachricht für Sensor veröffentlichen
                discovery_topic = f"{discovery_prefix}/binary_sensor/{node_id}/{sensor_id}/config"
                self.mqtt_client.publish(discovery_topic, json.dumps(sensor_config), retain=True, skip_prefix=True)
                logger.debug(f"Auto-Discovery für Sensor {sensor_id} veröffentlicht: {discovery_topic}")
            
            # Auto-Discovery für Aktoren
            for actor_id, actor in self.actors.items():
                # Aktuellen Status veröffentlichen
                state_value = "ON" if actor.state else "OFF"
                self.mqtt_client.publish(f"actors/{actor_id}/state", state_value, retain=True)
                
                # Auto-Discovery Payload für Aktor erstellen
                actor_config = {
                    "name": actor.name,
                    "unique_id": f"{node_id}_{actor_id}",
                    "device_class": actor.device_class if actor.device_class else None,
                    "state_topic": f"{self.mqtt_client.base_topic}/actors/{actor_id}/state",
                    "command_topic": f"{self.mqtt_client.base_topic}/actors/{actor_id}/set",
                    "availability_topic": f"{self.mqtt_client.base_topic}/status",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device": {
                        "identifiers": [f"{node_id}"],
                        "name": f"MCP2221 IO Controller",
                        "manufacturer": "Custom",
                        "model": "MCP2221 IO"
                    }
                }
                
                # Überprüfen der Konfiguration und Entfernen von None-Werten
                actor_config = {k: v for k, v in actor_config.items() if v is not None}
                
                # Auto-Discovery Nachricht für Aktor veröffentlichen
                discovery_topic = f"{discovery_prefix}/switch/{node_id}/{actor_id}/config"
                self.mqtt_client.publish(discovery_topic, json.dumps(actor_config), retain=True, skip_prefix=True)
                logger.debug(f"Auto-Discovery für Aktor {actor_id} veröffentlicht: {discovery_topic}")
                
                # Subscribe auf Command-Topic des Aktors
                self.mqtt_client.subscribe(f"actors/{actor_id}/set", self._handle_actor_command)

        return True

    def _handle_actor_command(self, topic: str, payload: str) -> None:
        """Verarbeitet Befehle für Aktoren von Home Assistant."""
        try:
            # Extrahiert die Aktor-ID aus dem Topic (Format: "actors/{actor_id}/set")
            parts = topic.split('/')
            if len(parts) >= 2:
                actor_id = parts[1]
                logger.info(f"MQTT Befehl empfangen für Aktor {actor_id}: {payload}")
                
                # Aktor abrufen
                actor = self.get_actor(actor_id)
                
                if actor:
                    if payload.upper() == "ON":
                        # Prüfen, ob Auto-Reset konfiguriert ist
                        if hasattr(actor, '_auto_reset') and actor._auto_reset > 0:
                            actor.toggle()  # Toggle für Aktoren mit Auto-Reset
                        else:
                            actor.turn_on()  # Normale Einschaltung für Aktoren ohne Auto-Reset
                        logger.info(f"Aktor {actor_id} wurde durch MQTT-Befehl eingeschaltet")
                    elif payload.upper() == "OFF":
                        actor.turn_off()
                        logger.info(f"Aktor {actor_id} wurde durch MQTT-Befehl ausgeschaltet")
                    else:
                        logger.warning(f"Unbekannter Befehl für Aktor {actor_id}: {payload}")
                else:
                    logger.warning(f"Aktor {actor_id} nicht gefunden für Befehl: {payload}")
        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung des Aktor-Befehls: {e}")
            import traceback
            logger.error(traceback.format_exc())



    def stop(self) -> None:
        """Stoppt den Controller und gibt alle Ressourcen frei."""
        self.running = False
        # Alle Aktoren herunterfahren
        for actor_id, actor in self.actors.items():
            actor.shutdown()
            state_value = "ON" if actor.state else "OFF"
            self.mqtt_client.publish(f"actors/{actor_id}/state", state_value, retain=True)
        
        # Alle Sensoren herunterfahren
        for sensor_id, sensor in self.sensors.items():
            sensor.shutdown()
            state_value = "ON" if sensor.state else "OFF"
            self.mqtt_client.publish(f"sensors/{sensor_id}/state", state_value, retain=True)
        
        if self.mqtt_client and self.mqtt_client.connected:
            self.mqtt_client.publish("status", "offline", retain=True)
            logger.info("MQTT Online-Status veröffentlicht.")

        logger.info("IOController gestoppt.")
    
    # Rest der Methoden bleibt unverändert...
    def update(self) -> None:
        """Aktualisiert alle Geräte - sollte in einer Schleife aufgerufen werden."""
        if not self.running:
            return
        
        self.check_state_change()

        # Aktoren aktualisieren
        for actor in self.actors.values():
            actor.update()
            actor.sync_state()
        
        # Sensoren aktualisieren
        for sensor in self.sensors.values():
            sensor.sync_state()
    
    def check_state_change(self):
        # Aktoren auf geänderten Status prüfen
        for actor_id, actor in self.actors.items():
            if actor.state_changed:
                logger.info(f"Aktor {actor_id} hat seinen Wert geändert, aktueller Wert: {actor.state}")
        
                if self.mqtt_client and self.mqtt_client.connected:
                    state_value = "ON" if actor.state else "OFF"
                    self.mqtt_client.publish(f"actors/{actor_id}/state", state_value, retain=True)
                

        # Sensoren auf geänderten Status prüfen
        for sensor_id, sensor in self.sensors.items():
            if sensor.state_changed:
                
                logger.info(f"Sensor {sensor_id} hat seinen Wert geändert, aktueller Wert: {sensor.state}")

                if self.mqtt_client and self.mqtt_client.connected:
                    state_value = "ON" if sensor.state else "OFF"
                    self.mqtt_client.publish(f"sensors/{sensor_id}/state", state_value, retain=True)
                


    def get_actor(self, actor_id: str) -> Optional[IOActor]:
        """Gibt den Aktor mit der angegebenen ID zurück."""
        return self.actors.get(actor_id)
    
    def get_sensor(self, sensor_id: str) -> Optional[IOSensor]:
        """Gibt den Sensor mit der angegebenen ID zurück."""
        return self.sensors.get(sensor_id)
    
    def print_all_states(self) -> None:
        """Gibt den Status aller Geräte aus."""
        print("\n--- Aktueller Gerätestatus ---")
        for sensor_id, sensor in self.sensors.items():
            sensor.print_state()
        
        for actor_id, actor in self.actors.items():
            actor.print_state()
            if isinstance(actor, IOActor) and hasattr(actor, 'toggle_active'):
                print(f"  Toggle aktiv: {actor.toggle_active}")
        print("-----------------------------\n")


