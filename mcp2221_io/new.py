import os
import time
import yaml
import digitalio
import board
import logging
from termcolor import colored
from typing import Dict, List, Optional, Any
from mcp2221_io.new_mqtt import MQTTClient
from mcp2221_io.new_classes import get_logger, get_config, IODevice, IOActor, IOSensor, IOController












if __name__ == "__main__":
    # Konfiguration einlesen
    current_dir = os.path.dirname(os.path.abspath(__file__))  # mcp2221_io/mcp2221_io/
    parent_dir = os.path.dirname(current_dir)                # mcp2221_io/
    config_path = os.path.join(parent_dir, "config.yaml")

    config = get_config()
    logger = get_logger()

    # Logger initialisieren
    debug_level = config.get_value("logging.level", "WARNING")
    # logger = Logger(debug_level).get_logger()

    # Controller erstellen und starten
    controller = IOController()

    if controller.start():
        # MQTT-Client erstellen und starten
        mqtt_client = MQTTClient(config.get_value('mqtt'), config.get_value('logging.mqtt'))
        
        try:
            # Haupt-Loop
            i = 0
            while controller.running:
                # Alle Geräte aktualisieren
                controller.update()
                
                # MQTT-Client aktualisieren
                mqtt_client.update()
                
                # Status-Ausgabe für Debugging
                for sensor_id, sensor in controller.sensors.items():
                    if config.get_value("logging.sensors", False):
                        logger.debug(f"Sensor " + colored(sensor_id, 'blue') + ": " + colored(sensor.state, 'green' if sensor.state else 'red'))
                for actor_id, actor in controller.actors.items():
                    if config.get_value("logging.actors", False):
                        logger.debug(f"Aktor " + colored(actor_id, 'magenta') + ": " + colored(actor.state, 'green' if actor.state else 'red'))

                
                if i == 20:
                    controller.get_actor('door_hintertuer').toggle()

                # Kurzes Timeout zum Verschnaufen
                i += 1
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            print("Programm durch Benutzer unterbrochen.")
        finally:
            # MQTT-Client trennen
            mqtt_client.disconnect()
            
            # Controller stoppen
            controller.stop()