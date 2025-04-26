# main.py
# Version: 5.0.0

import os
import time
import yaml
import sys
import logging
from mcp2221_io.logging_config import logger, LogCategory, set_debug_mode, set_logging_level_from_config
from mcp2221_io import IOController, Actor, Sensor, SimpleInputHandler, InputEvent, VirtualSensor
from mcp2221_io.mqtt_handler import MQTTHandler
from mcp2221_io.io_cover import Cover, CoverState
from mcp2221_io.cli_interface import execute_system_command, custom_event_handler, print_main_menu

from termcolor import colored

def load_config(config_path='config.yaml'):
    """Lädt die Konfiguration aus einer YAML-Datei"""
    if os.path.exists(config_path):
        config_file = config_path
    else:
        package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_file = os.path.join(package_dir, config_path)
        if not os.path.exists(config_file):
            example_config = os.path.join(package_dir, 'config.example.yaml')
            if os.path.exists(example_config):
                import shutil
                logger.info(f"Keine config.yaml gefunden, kopiere example config nach {config_file}", LogCategory.SYSTEM)
                shutil.copy2(example_config, config_file)
            else:
                raise FileNotFoundError(f"Weder config.yaml noch config.example.yaml gefunden in {package_dir}")

    logger.info(f"Lade Konfiguration aus {config_file}", LogCategory.SYSTEM)
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
            if 'mqtt' in config:
                config['mqtt']['actors'] = config['actors']
                if 'sensors' in config:
                    config['mqtt']['sensors'] = config['sensors']
            return config
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration: {e}", LogCategory.SYSTEM)
        raise

def setup_actors(controller, actor_config, sensor_config=None, debug_config={}):
    """Konfiguriert Aktoren basierend auf der Konfiguration"""
    logger.info("Konfiguriere Aktoren", LogCategory.SYSTEM)
    covers = {}

    for name, cfg in actor_config.items():
        try:
            reset_delay = 0.0
            entity_type = cfg.get('entity_type', 'switch').lower()

            if entity_type == 'cover':
                covers[name] = cfg
                logger.info(f"  - {name} (Cover, Pin {cfg['pin']}, inverted: {cfg.get('inverted', False)})", LogCategory.SYSTEM)

            if entity_type == 'button' or ((entity_type in ['switch', 'lock', 'cover']) and cfg.get('auto_reset', False)):
                reset_delay = float(cfg.get('reset_delay', 0.0))

            actor = Actor(
                cfg['pin'],
                inverted=cfg.get('inverted', False),
                reset_delay=reset_delay,
                debug_config=debug_config
            )
            controller.add_actor(name, actor)

            if entity_type != 'cover':
                logger.info(f"  - {name} (Pin {cfg['pin']}, inverted: {cfg.get('inverted', False)}, Typ: {entity_type})", LogCategory.SYSTEM)
        except Exception as e:
            logger.error(f"Fehler beim Konfigurieren von Actor {name}: {e}", LogCategory.SYSTEM)
            raise

    return covers

def setup_sensors(controller, sensor_config, debug_config={}):
    """Konfiguriert Sensoren basierend auf der Konfiguration"""
    if not sensor_config:
        logger.info("Keine Sensoren in der Konfiguration gefunden", LogCategory.SYSTEM)
        return

    logger.info(f"Konfiguriere {len(sensor_config)} Sensoren", LogCategory.SYSTEM)
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
                    debug_config=debug_config,
                    name=name  # Setze den Sensornamen hier!
                )
                if 'debounce_time' in cfg:
                    sensor.set_debounce_time(float(cfg['debounce_time']))
                if hasattr(sensor, 'set_stable_readings'):
                    stable_readings = int(cfg.get('stable_readings', 3))
                    sensor.set_stable_readings(stable_readings)
                controller.add_sensor(name, sensor)
                logger.info(f"  - {name} (Pin {cfg['pin']}, inverted: {inverted}, Typ: {cfg.get('entity_type', 'binary')})", LogCategory.SYSTEM)
            elif sensor_type == "VIRTUAL":
                inverted = cfg.get('inverted', False)
                sensor = VirtualSensor(name, inverted=inverted, debug_config=debug_config)
                controller.add_sensor(name, sensor)
                logger.info(f"  - {name} (virtuell, Typ: {cfg.get('entity_type', 'binary')})", LogCategory.SYSTEM)
            else:
                logger.info(f"  - {name}: Unbekannter Sensor-Typ: {sensor_type}", LogCategory.SYSTEM)
        except Exception as e:
            logger.error(f"Fehler beim Konfigurieren von Sensor {name}: {e}", LogCategory.SYSTEM)
            raise

def setup_covers(controller, covers, debug_config={}):
    """Konfiguriert Cover basierend auf der Konfiguration"""
    if not covers:
        return

    logger.info(f"Konfiguriere {len(covers)} Cover-Entitäten", LogCategory.SYSTEM)
    for name, cfg in covers.items():
        try:
            if name not in controller.actors:
                logger.error(f"Aktor für Cover {name} nicht gefunden", LogCategory.COVER)
                continue

            actor = controller.actors[name]
            sensor_open_id = cfg.get('sensor_open')
            sensor_closed_id = cfg.get('sensor_closed')

            if sensor_open_id and sensor_open_id not in controller.sensors:
                logger.error(f"Sensor {sensor_open_id} für Cover {name} (open) nicht gefunden", LogCategory.COVER)
                sensor_open_id = None

            if sensor_closed_id and sensor_closed_id not in controller.sensors:
                logger.error(f"Sensor {sensor_closed_id} für Cover {name} (closed) nicht gefunden", LogCategory.COVER)
                sensor_closed_id = None

            cover = Cover(
                actor,
                sensor_open_id=sensor_open_id,
                sensor_closed_id=sensor_closed_id,
                inverted=cfg.get('inverted', False),
                debug_config=debug_config
            )

            controller.add_cover(name, cover, sensor_open_id, sensor_closed_id)

            logger.info(f"  - Cover {name} konfiguriert mit Sensoren: open={sensor_open_id}, closed={sensor_closed_id}", LogCategory.SYSTEM)

        except Exception as e:
            logger.error(f"Fehler beim Konfigurieren von Cover {name}: {e}", LogCategory.COVER)
            logger.info(f"  - Fehler bei Cover {name}: {e}", LogCategory.SYSTEM)

def setup_key_mappings(key_config):
    """Konfiguriert Key-Mappings für Tastaturbefehle"""
    logger.info("Konfiguriere Key-Mappings", LogCategory.SYSTEM)
    mappings = {}
    for key, cfg in key_config.items():
        if isinstance(cfg, dict):
            target = cfg.get('target', 'unknown')
            action = cfg.get('action', 'unknown')
            value = cfg.get('value', None)
            mappings[key] = (target, action, value)
        else:
            logger.warning(f"Ungültiges Key-Mapping-Format für Taste {key}: {cfg}", LogCategory.SYSTEM)
    return mappings

def main():
    """Hauptfunktion des Programms"""
    logger.info("Starte Hauptprogramm", LogCategory.SYSTEM)
    
    # Konfiguration laden
    config = load_config()

    # Debug-Modus für bessere Diagnose konfigurieren
    cli_debug_mode = True
    set_logging_level_from_config(config, cli_debug_mode)
    debug_config = config.get('debugging', {})

    # Controller initialisieren
    controller = IOController(debug_config=debug_config)

    # Komponenten konfigurieren
    covers = setup_actors(controller, config['actors'], config.get('sensors', {}), debug_config)
    setup_sensors(controller, config.get('sensors', {}), debug_config)

    # Force-Update für alle Sensoren nach der Initialisierung
    logger.info("Führe Initial-Update für alle Sensoren durch", LogCategory.SYSTEM)
    for sensor_id, sensor in controller.sensors.items():
        if hasattr(sensor, 'force_update'):
            try:
                state = sensor.force_update()
                logger.info(f"  - Initialer Zustand für {sensor_id}: {state}", LogCategory.SENSOR)
            except Exception as e:
                logger.error(f"Fehler beim Initial-Update von Sensor {sensor_id}: {e}", LogCategory.SENSOR)

    # MQTT-Handler initialisieren, wenn konfiguriert
    mqtt_handler = None
    if 'mqtt' in config:
        try:
            mqtt_handler = MQTTHandler(config['mqtt'], debug_config=debug_config)
            mqtt_handler.set_sensors(controller.sensors)
            logger.info(f"Konfiguriere MQTT (Host: {config['mqtt'].get('broker')}, Port: {config['mqtt'].get('port', 1883)})", LogCategory.MQTT)

            # Verbindung vor dem Setzen des MQTT-Handlers herstellen
            mqtt_handler.connect()
            logger.info(f"MQTT-Verbindung erfolgreich hergestellt zu {config['mqtt'].get('broker')}", LogCategory.MQTT)
            
            # Controller im MQTT-Handler registrieren
            if hasattr(mqtt_handler, 'set_controller'):
                mqtt_handler.set_controller(controller)
                logger.info("Controller im MQTT-Handler registriert", LogCategory.MQTT)

            # Jetzt den MQTT-Handler setzen (dabei werden Callbacks registriert)
            controller.set_mqtt_handler(mqtt_handler)

        except Exception as e:
            logger.error(f"MQTT konnte nicht initialisiert werden: {str(e)}", LogCategory.MQTT)
            mqtt_handler = None

    # Setup covers erst nach MQTT-Setup, damit die Zustandsänderungen korrekt publiziert werden
    setup_covers(controller, covers, debug_config)

    # Wenn MQTT nicht verfügbar ist, können wir die Cover-Initialisierung hier noch manuell aufrufen
    if not mqtt_handler and covers:
        controller.initialize_covers()

    # Key-Mappings konfigurieren
    key_mappings = setup_key_mappings(config.get('key_mappings', {}))

    # Input-Handler für Tastaturbefehle einrichten
    input_handler = SimpleInputHandler(key_mappings)
    input_handler.observers = [lambda event: custom_event_handler(event, controller, mqtt_handler, config, key_mappings)]
    controller.add_input_handler(input_handler)

    # Hauptmenü anzeigen
    print_main_menu(key_mappings)

    try:
        # Controller starten
        controller.start()
        
        # Führe nach dem Start noch ein umfassendes Update aller Zustände durch
        logger.info("Führe umfassendes Update aller Zustände nach Systemstart durch...", LogCategory.SYSTEM)
        
        # Erst Sensor-Test
        if mqtt_handler:
            mqtt_handler.test_sensor_pins()
            # Warte kurz, damit die Sensor-Updates verarbeitet werden können
            time.sleep(0.5)
            # Dann Cover neu initialisieren (mit aktuellen Sensor-Werten)
            controller.initialize_covers()
            # Dann alle Zustände neu publizieren
            mqtt_handler.refresh_all_states()
        
        logger.info("System ist bereit.", LogCategory.SYSTEM)
        
        # Haupt-Event-Loop
        while controller.running:
            time.sleep(0.05)
    except KeyboardInterrupt:
        logger.info("Beende Programm durch Tastendruck...", LogCategory.SYSTEM)
    finally:
        # Aufräumen
        controller.stop()
        if mqtt_handler:
            mqtt_handler.disconnect()
            logger.info("MQTT-Verbindung getrennt", LogCategory.MQTT)
        logger.info("System erfolgreich beendet", LogCategory.SYSTEM)

if __name__ == "__main__":
    main()