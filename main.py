import os
import time
import yaml
from .logging_config import logger
from mcp2221_io import IOController, Actor, SimpleInputHandler
from mcp2221_io.mqtt_handler import MQTTHandler

def load_config(config_path='config.yaml'):
    module_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(module_dir, config_path)
    logger.debug(f"Lade Konfiguration aus {config_file}")
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
            if 'mqtt' in config:
                config['mqtt']['actors'] = config['actors']
            return config
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration: {e}")
        raise

def setup_actors(controller, actor_config):
    logger.debug("Konfiguriere Aktoren")
    for name, cfg in actor_config.items():
        try:
            reset_delay = 0.0
            entity_type = cfg.get('entity_type', 'switch').lower()
            
            if entity_type == 'button' or (entity_type == 'switch' and cfg.get('auto_reset', False)):
                reset_delay = float(cfg.get('reset_delay', 0.0))
                logger.debug(f"{entity_type.capitalize()} {name} mit Reset-Delay {reset_delay}s konfiguriert")
            
            actor = Actor(
                cfg['pin'], 
                inverted=cfg.get('inverted', False),
                reset_delay=reset_delay
            )
            controller.add_actor(name, actor)
            logger.debug(f"Actor {name} ({cfg['description']}) an Pin {cfg['pin']} konfiguriert")
        except Exception as e:
            logger.error(f"Fehler beim Konfigurieren von Actor {name}: {e}")
            raise

def setup_key_mappings(key_config):
    logger.debug("Konfiguriere Key-Mappings")
    mappings = {}
    for key, cfg in key_config.items():
        mappings[key] = (cfg['target'], cfg['action'], None)
    logger.debug(f"Key-Mappings erstellt: {mappings}")
    return mappings

def reset_actors_to_default(controller, config, mqtt_handler=None):
    logger.debug("Setze Aktoren auf Standardwerte zurück")
    
    for actor_id, actor_config in config['actors'].items():
        try:
            if actor_id in controller.actors:
                entity_type = actor_config.get('entity_type', 'switch').lower()
                
                if entity_type == 'switch':
                    default_state = actor_config.get('startup_state', 'off').lower() == 'on'
                    logger.debug(f"Setze {actor_id} auf Standardwert: {default_state}")
                    
                    if mqtt_handler:
                        mqtt_handler.publish_command(actor_id, "ON" if default_state else "OFF")
                        time.sleep(0.1)
                
                logger.debug(f"{actor_id} erfolgreich zurückgesetzt")
        except Exception as e:
            logger.error(f"Fehler beim Zurücksetzen von {actor_id}: {e}")

def main():
    logger.debug("Starte Hauptprogramm")
    config = load_config()
    controller = IOController()
    logger.debug("Controller erstellt")
    
    setup_actors(controller, config['actors'])
    key_mappings = setup_key_mappings(config['key_mappings'])
    
    mqtt_handler = None
    if 'mqtt' in config:
        try:
            mqtt_handler = MQTTHandler(config['mqtt'])
            controller.set_mqtt_handler(mqtt_handler)
            mqtt_handler.connect()
            mqtt_handler.start_board_monitoring()
            logger.debug("MQTT Handler initialisiert und verbunden")
        except Exception as e:
            logger.warning(f"MQTT konnte nicht initialisiert werden: {e}")
            mqtt_handler = None
    
    input_handler = SimpleInputHandler(key_mappings)
    controller.add_input_handler(input_handler)
    logger.debug("Input Handler erstellt und registriert")
    
    logger.info("\nSystem gestartet. Steuerung:")
    for key, cfg in config['key_mappings'].items():
        if cfg['target'] in config['actors']:
            actor_cfg = config['actors'][cfg['target']]
            desc = f"{cfg['action'].capitalize()} {actor_cfg['description']} (GPIO '{actor_cfg['pin']}'"
            if actor_cfg.get('entity_type') == 'button' and actor_cfg.get('reset_delay', 0) > 0:
                desc += f", Reset nach {actor_cfg['reset_delay']}s)"
            else:
                desc += ")"
            logger.info(f"  {key}: {desc}")
        elif cfg['target'] == 'system':
            logger.info(f"  {key}: {cfg['action'].capitalize()}")
    logger.info("\nBitte Taste eingeben und Enter drücken:")
    
    try:
        controller.start()
        controller.running = True
        logger.debug("Controller gestartet")
        while controller.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("\nBeende Programm...")
    finally:
        logger.debug("Beginne sauberes Herunterfahren...")
        
        controller.stop()
        logger.debug("Input Handler gestoppt")
        
        reset_actors_to_default(controller, config, mqtt_handler)
        logger.debug("Aktoren zurückgesetzt")
        
        if mqtt_handler:
            logger.debug("Stoppe MQTT Handler...")
            try:
                mqtt_handler.disconnect()
                logger.debug("MQTT Handler gestoppt")
            except Exception as e:
                logger.error(f"Fehler beim Stoppen des MQTT Handlers: {e}")
        
        logger.debug("System erfolgreich beendet")

if __name__ == "__main__":
    main()