# main.py
# Version: 3.7.0

import os
import time
import yaml
import sys
import logging
from mcp2221_io.logging_config import logger, set_debug_mode
from mcp2221_io import IOController, Actor, Sensor, SimpleInputHandler, InputEvent
from mcp2221_io.virtual_sensor import VirtualSensor
from mcp2221_io.mqtt_handler import MQTTHandler
from mcp2221_io.cli_interface import execute_system_command, custom_event_handler, run_cli_sensor_tests

def direct_print(message):
    """Direktes Ausgeben von Meldungen ohne Logger"""
    print(message)

def set_logging_level_from_config(config, cli_debug_mode=False):
    """
    Setzt das Logging-Level basierend auf der Konfiguration
    
    :param config: Die Konfiguration
    :param cli_debug_mode: Ob der CLI-Debug-Modus aktiv ist (z.B. Diagnose-Menü)
    """
    # Debug-Konfiguration nur überschreiben, wenn nicht im CLI-Debug-Modus
    if not cli_debug_mode:
        # Im normalen Betrieb bestimmte Debug-Ausgaben unterdrücken für bessere Performance
        config['debugging']['system']['entities']['actors'] = False
        config['debugging']['system']['entities']['sensors'] = False
        config['debugging']['system']['process'] = False
    
    level_str = config.get("debugging", {}).get("level", "DEBUG").upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "NONE": logging.CRITICAL + 10
    }
    level = level_map.get(level_str, logging.DEBUG)
    logger.setLevel(level)
    
    # Debug-Modus aus Konfiguration setzen
    debug_mode = config.get("debugging", {}).get("mqtt", {}).get("process", False)
    if debug_mode:
        set_debug_mode(True)
    else:
        set_debug_mode(False)
    
    if level > logging.DEBUG:
        logging.getLogger("mcp2221_io").propagate = False

def load_config(config_path='config.yaml'):
    if os.path.exists(config_path):
        config_file = config_path
    else:
        package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_file = os.path.join(package_dir, config_path)
        if not os.path.exists(config_file):
            example_config = os.path.join(package_dir, 'config.example.yaml')
            if os.path.exists(example_config):
                import shutil
                direct_print(f"Keine config.yaml gefunden, kopiere example config nach {config_file}")
                shutil.copy2(example_config, config_file)
            else:
                raise FileNotFoundError(f"Weder config.yaml noch config.example.yaml gefunden in {package_dir}")

    direct_print(f"Lade Konfiguration aus {config_file}")
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
            if 'mqtt' in config:
                config['mqtt']['actors'] = config['actors']
                if 'sensors' in config:
                    config['mqtt']['sensors'] = config['sensors']
            return config
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration: {e}")
        raise

def setup_actors(controller, actor_config, debug_config={}):
    direct_print("Konfiguriere Aktoren")
    for name, cfg in actor_config.items():
        try:
            reset_delay = 0.0
            entity_type = cfg.get('entity_type', 'switch').lower()
            if entity_type == 'button' or ((entity_type in ['switch', 'lock']) and cfg.get('auto_reset', False)):
                reset_delay = float(cfg.get('reset_delay', 0.0))
            actor = Actor(
                cfg['pin'],
                inverted=cfg.get('inverted', False),
                reset_delay=reset_delay,
                debug_config=debug_config
            )
            controller.add_actor(name, actor)
            direct_print(f"  - {name} (Pin {cfg['pin']}, inverted: {cfg.get('inverted', False)}, Typ: {entity_type})")
        except Exception as e:
            logger.error(f"Fehler beim Konfigurieren von Actor {name}: {e}")
            raise

def setup_sensors(controller, sensor_config, debug_config={}):
    if not sensor_config:
        direct_print("Keine Sensoren in der Konfiguration gefunden")
        return

    direct_print(f"Konfiguriere {len(sensor_config)} Sensoren")
    for name, cfg in sensor_config.items():
        try:
            sensor_type = cfg.get('sensor_type', '').upper()
            if sensor_type in ["GPIO", "TEST"]:
                poll_interval = float(cfg.get('poll_interval', 0.1))
                inverted = cfg.get('inverted', False)
                sensor = Sensor(
                    cfg['pin'],
                    inverted=inverted,
                    poll_interval=poll_interval,
                    debug_config=debug_config
                )
                if 'debounce_time' in cfg:
                    sensor.set_debounce_time(float(cfg['debounce_time']))
                if hasattr(sensor, 'set_stable_readings'):
                    stable_readings = int(cfg.get('stable_readings', 3))
                    sensor.set_stable_readings(stable_readings)
                controller.add_sensor(name, sensor)
                direct_print(f"  - {name} (Pin {cfg['pin']}, inverted: {inverted}, Typ: {cfg.get('entity_type', 'binary')})")
            elif sensor_type == "VIRTUAL":
                inverted = cfg.get('inverted', False)
                sensor = VirtualSensor(name, inverted=inverted, debug_config=debug_config)
                controller.add_sensor(name, sensor)
                direct_print(f"  - {name} (virtuell, Typ: {cfg.get('entity_type', 'binary')})")
            else:
                direct_print(f"  - {name}: Unbekannter Sensor-Typ: {sensor_type}")
        except Exception as e:
            logger.error(f"Fehler beim Konfigurieren von Sensor {name}: {e}")
            raise

def setup_key_mappings(key_config):
    direct_print("Konfiguriere Key-Mappings")
    mappings = {}
    for key, cfg in key_config.items():
        mappings[key] = (cfg['target'], cfg['action'], None)
    return mappings

def reset_actors_to_default(controller, config, mqtt_handler=None):
    direct_print("Setze Aktoren auf Standardwerte zurück")
    for actor_id, actor_config in config['actors'].items():
        try:
            if actor_id in controller.actors:
                entity_type = actor_config.get('entity_type', 'switch').lower()
                if entity_type == 'switch':
                    default_state = actor_config.get('startup_state', 'off').lower() == 'on'
                    if mqtt_handler:
                        mqtt_handler.publish_command(actor_id, "ON" if default_state else "OFF")
                        time.sleep(0.1)
                direct_print(f"  - {actor_id} zurückgesetzt")
        except Exception as e:
            logger.error(f"Fehler beim Zurücksetzen von {actor_id}: {e}")

def stop_sensors(controller):
    direct_print("Stoppe Sensoren")
    for name, sensor in controller.sensors.items():
        try:
            if hasattr(sensor, "stop_polling"):
                sensor.stop_polling()
            direct_print(f"  - {name} gestoppt")
        except Exception as e:
            logger.error(f"Fehler beim Stoppen von Sensor {name}: {e}")

def main():
    global key_mappings
    direct_print("Starte Hauptprogramm")
    config = load_config()
    
    # Standardmäßig normalen Debug-Modus verwenden
    cli_debug_mode = False
    set_logging_level_from_config(config, cli_debug_mode)
    debug_config = config.get('debugging', {})

    controller = IOController(debug_config=debug_config)
    setup_actors(controller, config['actors'], debug_config)
    setup_sensors(controller, config.get('sensors', {}), debug_config)
    key_mappings = setup_key_mappings(config['key_mappings'])

    mqtt_handler = None
    if 'mqtt' in config:
        try:
            # Explizit debug_config übergeben
            mqtt_handler = MQTTHandler(config['mqtt'], debug_config=debug_config)
            mqtt_handler.set_sensors(controller.sensors)
            controller.set_mqtt_handler(mqtt_handler)
            direct_print(f"Konfiguriere MQTT (Host: {config['mqtt'].get('broker')}, Port: {config['mqtt'].get('port', 1883)})")
            
            # Verbindung mit Retry-Logik
            max_retries = 3
            retry_delay = 5  # Sekunden
            connected = False
            
            for retry in range(max_retries):
                try:
                    mqtt_handler.connect()
                    connected = True
                    direct_print(f"MQTT-Verbindung erfolgreich hergestellt zu {config['mqtt'].get('broker')}")
                    break
                except Exception as e:
                    if retry < max_retries - 1:
                        direct_print(f"MQTT-Verbindung fehlgeschlagen (Versuch {retry+1}/{max_retries}): {str(e)}")
                        direct_print(f"Neuer Verbindungsversuch in {retry_delay} Sekunden...")
                        time.sleep(retry_delay)
                    else:
                        direct_print(f"MQTT konnte nicht initialisiert werden nach {max_retries} Versuchen: {str(e)}")
            
            if connected:
                if hasattr(mqtt_handler, 'force_publish_all_sensor_states'):
                    time.sleep(1)
                    # Umgebungsvariable temporär setzen, um Debug-Ausgaben zu unterdrücken
                    old_debug = os.environ.get('MCP2221_DEBUG', '0')
                    os.environ['MCP2221_DEBUG'] = '0'
                    mqtt_handler.force_publish_all_sensor_states()
                    if hasattr(mqtt_handler, 'test_sensor_pins'):
                        mqtt_handler.test_sensor_pins()
                    # Zurücksetzen der Umgebungsvariable
                    os.environ['MCP2221_DEBUG'] = old_debug
                mqtt_handler.start_board_monitoring()
                direct_print("MQTT Board-Monitoring gestartet")
            else:
                mqtt_handler = None
                direct_print("MQTT nicht verfügbar - System läuft im Standalone-Modus")
                
        except Exception as e:
            direct_print(f"MQTT konnte nicht initialisiert werden: {str(e)}")
            logger.warning(f"MQTT konnte nicht initialisiert werden: {e}")
            mqtt_handler = None
            direct_print("MQTT nicht verfügbar - System läuft im Standalone-Modus")

    # Erweiterter Event-Handler für CLI-Modi
    def cli_event_handler(event):
        # Bei speziellen Diagnose-Events temporär den CLI-Debug-Modus aktivieren
        if event.target == 'system' and event.action == 'diagnose':
            nonlocal cli_debug_mode
            # Debug-Konfiguration für CLI-Modus aktivieren
            cli_debug_mode = True
            set_logging_level_from_config(config, cli_debug_mode)
            try:
                custom_event_handler(event, controller, mqtt_handler, config, key_mappings)
            finally:
                # Zurück zum normalen Debug-Modus
                cli_debug_mode = False
                set_logging_level_from_config(config, cli_debug_mode)
        else:
            # Normale Event-Verarbeitung
            custom_event_handler(event, controller, mqtt_handler, config, key_mappings)

    input_handler = SimpleInputHandler(key_mappings)
    input_handler.observers = [cli_event_handler]
    controller.add_input_handler(input_handler)

    print_main_menu(key_mappings)

    try:
        controller.start()
        while controller.running:
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nBeende Programm durch Tastendruck...")
    finally:
        controller.stop()
        stop_sensors(controller)
        reset_actors_to_default(controller, config, mqtt_handler)
        if mqtt_handler:
            try:
                mqtt_handler.disconnect()
                direct_print("MQTT-Verbindung getrennt")
            except Exception as e:
                logger.error(f"Fehler beim Stoppen des MQTT Handlers: {e}")
        direct_print("System erfolgreich beendet")

    return 0

def print_main_menu(key_mappings):
    print("System gestartet. Steuerung:")
    for key, value in key_mappings.items():
        if isinstance(value, dict):
            print(f"  {key}: {value.get('action', '?').capitalize()} {value.get('target', '?')}")
        elif isinstance(value, tuple) and len(value) >= 2:
            print(f"  {key}: {value[1].capitalize()} {value[0]}")
    print("\nBitte Taste eingeben und Enter drücken:")

if __name__ == "__main__":
    main()