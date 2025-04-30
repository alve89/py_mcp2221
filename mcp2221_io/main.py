import mcp2221_io.const as const

import os
import time
import yaml



import logging
from termcolor import colored
from typing import Dict, List, Optional, Any
from mcp2221_io import get_logger, get_config, MQTTClient, IOController
from mcp2221_io.const import MCP2221, FT232H, HW, validate_hardware_config


def validate_hardware_config(config_value):
    """
    Überprüft, ob in der Hardware-Konfiguration genau ein Eintrag den Wert True hat.
    
    Args:
        config_value: Der zurückgegebene Wert von config.get_value("use.hardware")
        Kann ein Dictionary oder ein String sein.
        
    Returns:
        bool: True wenn genau ein Eintrag True ist, sonst False
    """
    # Überprüfen, welcher Datentyp vorliegt
    if isinstance(config_value, str):
        # Wenn es ein String ist, konvertieren wir ihn zu einem Dictionary
        import ast
        try:
            config_dict = ast.literal_eval(config_value)
        except (SyntaxError, ValueError):
            return False  # Ungültiges Format
    elif isinstance(config_value, dict):
        # Wenn es bereits ein Dictionary ist, verwenden wir es direkt
        config_dict = config_value
    else:
        # Wenn es weder ein String noch ein Dictionary ist, ist es ungültig
        return False
    
    # Zähle die Anzahl der True-Werte
    true_count = sum(1 for value in config_dict.values() if value is True)
    
    # Überprüfe, ob genau ein Eintrag True ist
    return true_count == 1





if __name__ == "__main__":
    # Konfiguration einlesen
    current_dir = os.path.dirname(os.path.abspath(__file__))  # mcp2221_io/mcp2221_io/
    parent_dir = os.path.dirname(current_dir)                # mcp2221_io/
    config_path = os.path.join(parent_dir, "config.yaml")

    config = get_config()
    logger = get_logger()

    # Logger initialisieren
    debug_level = config.get_value("logging.level", "WARNING")

    # Zu nutzende Hardware festlegen
    hw_str = "NoHardware"

    if not validate_hardware_config(config.get_value("hardware")):
        logger.critical(colored("Die Konfiguration des Punkts 'hardware' ist fehlerhaft. Mögliche Fehler: KEIN Eintrag ODER MEHRERE Einträge sind 'true'.", "red"))
        exit(1)

    if config.get_value("hardware.mcp2221"):
        const.HW = const.MCP2221
        hw_str = "MCP2221"
        import digitalio
        import board
    elif config.get_value("hardware.ft232h"):
        const.HW = const.FT232H
        hw_str = "FT232H"
    else:
        logger.critical(colored("Kein Hardware-Board konfiguriert!", "red"))
        exit(1)

    logger.info("Hardware festgelegt als " + hw_str)


    # MQTT-Client erstellen
    mqtt_client = MQTTClient(config.get_value('mqtt'), config.get_value('logging.mqtt'))
    mqtt_client.connect()  # Verbindung herstellen



    # Controller erstellen und starten
    controller = IOController(mqtt_client)

    if controller.start():        
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

                
                if i == 10:
                    # controller.get_actor('door_hintertuer').toggle()
                    print("")

                # Kurzes Timeout zum Verschnaufen
                i += 1
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("Programm durch Benutzer unterbrochen.")

        finally:
            # Controller stoppen
            controller.stop()

            # MQTT-Client trennen
            mqtt_client.disconnect()