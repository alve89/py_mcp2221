# mcp2221_io/main.py

import os
import time
import yaml

# Umgebungsvariablen nur setzen wenn nicht bereits gesetzt
if 'BLINKA_MCP2221' not in os.environ:
    os.environ['BLINKA_MCP2221'] = '1'
if 'BLINKA_MCP2221_RESET_DELAY' not in os.environ:
    os.environ['BLINKA_MCP2221_RESET_DELAY'] = '-1'

from mcp2221_io import IOController, Actor, SimpleInputHandler
from mcp2221_io.mqtt_handler import MQTTHandler

def load_config(config_path='config.yaml'):
    """Lädt die YAML-Konfiguration"""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(module_dir, config_path)
    print(f"[DEBUG] Lade Konfiguration aus {config_file}")
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
            if 'mqtt' in config:
                config['mqtt']['actors'] = config['actors']
            return config
    except Exception as e:
        print(f"[ERROR] Fehler beim Laden der Konfiguration: {e}")
        raise

def setup_actors(controller, actor_config):
    """Richtet die Aktoren basierend auf der Konfiguration ein"""
    print("[DEBUG] Konfiguriere Aktoren")
    for name, cfg in actor_config.items():
        try:
            # Reset delay nur für Buttons berücksichtigen
            reset_delay = 0.0
            if cfg.get('entity_type', 'switch').lower() == 'button':
                reset_delay = float(cfg.get('reset_delay', 0.0))
                print(f"[DEBUG] Button {name} mit Reset-Delay {reset_delay}s konfiguriert")
            
            actor = Actor(
                cfg['pin'], 
                inverted=cfg.get('inverted', False),
                reset_delay=reset_delay
            )
            controller.add_actor(name, actor)
            print(f"[DEBUG] Actor {name} ({cfg['description']}) an Pin {cfg['pin']} konfiguriert")
        except Exception as e:
            print(f"[ERROR] Fehler beim Konfigurieren von Actor {name}: {e}")
            raise

def setup_key_mappings(key_config):
    """Erstellt Key-Mappings aus der Konfiguration"""
    print("[DEBUG] Konfiguriere Key-Mappings")
    mappings = {}
    for key, cfg in key_config.items():
        mappings[key] = (cfg['target'], cfg['action'], None)
    print(f"[DEBUG] Key-Mappings erstellt: {mappings}")
    return mappings

def reset_actors_to_default(controller, config, mqtt_handler=None):
    """Setzt alle Aktoren auf ihre Standardwerte zurück"""
    print("[DEBUG] Setze Aktoren auf Standardwerte zurück")
    
    for actor_id, actor_config in config['actors'].items():
        try:
            if actor_id in controller.actors:
                entity_type = actor_config.get('entity_type', 'switch').lower()
                
                # Nur für Switches den Standardwert setzen
                if entity_type == 'switch':
                    # Standardwert aus Konfiguration ermitteln
                    default_state = actor_config.get('startup_state', 'off').lower() == 'on'
                    print(f"[DEBUG] Setze {actor_id} auf Standardwert: {default_state}")
                    
                    # Kommando über MQTT senden
                    if mqtt_handler:
                        mqtt_handler.publish_command(actor_id, "ON" if default_state else "OFF")
                        time.sleep(0.1)  # Kurze Pause für MQTT-Verarbeitung
                
                print(f"[DEBUG] {actor_id} erfolgreich zurückgesetzt")
        except Exception as e:
            print(f"[ERROR] Fehler beim Zurücksetzen von {actor_id}: {e}")

def main():
    print("[DEBUG] Starte Hauptprogramm")
    
    # Lade Konfiguration
    config = load_config()
    
    # Erstelle Controller
    controller = IOController()
    print("[DEBUG] Controller erstellt")
    
    # Konfiguriere Aktoren aus YAML
    setup_actors(controller, config['actors'])
    
    # Konfiguriere Key-Mappings aus YAML
    key_mappings = setup_key_mappings(config['key_mappings'])
    
    # MQTT Handler initialisieren wenn konfiguriert
    mqtt_handler = None
    if 'mqtt' in config:
        try:
            mqtt_handler = MQTTHandler(config['mqtt'])
            controller.set_mqtt_handler(mqtt_handler)
            mqtt_handler.connect()
            print("[DEBUG] MQTT Handler initialisiert und verbunden")
        except Exception as e:
            print(f"[WARNING] MQTT konnte nicht initialisiert werden: {e}")
            mqtt_handler = None
    
    # Erstelle und registriere Simple Handler
    input_handler = SimpleInputHandler(key_mappings)
    controller.add_input_handler(input_handler)
    print("[DEBUG] Input Handler erstellt und registriert")
    
    # System starten
    print("\nSystem gestartet. Steuerung:")
    for key, cfg in config['key_mappings'].items():
        if cfg['target'] in config['actors']:
            actor_cfg = config['actors'][cfg['target']]
            desc = f"{cfg['action'].capitalize()} {actor_cfg['description']} (GPIO '{actor_cfg['pin']}'"
            if actor_cfg.get('entity_type') == 'button' and actor_cfg.get('reset_delay', 0) > 0:
                desc += f", Reset nach {actor_cfg['reset_delay']}s)"
            else:
                desc += ")"
            print(f"  {key}: {desc}")
        elif cfg['target'] == 'system':
            print(f"  {key}: {cfg['action'].capitalize()}")
    print("\nBitte Taste eingeben und Enter drücken:")
    
    try:
        controller.start()
        controller.running = True
        print("[DEBUG] Controller gestartet")
        while controller.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nBeende Programm...")
    finally:
        print("[DEBUG] Beginne sauberes Herunterfahren...")
        
        # Stoppe Input Handler
        print("[DEBUG] Stoppe Input Handler...")
        controller.stop()
        print("[DEBUG] Input Handler gestoppt")
        
        # Aktoren auf Standardwerte zurücksetzen
        print("[DEBUG] Setze Aktoren zurück...")
        reset_actors_to_default(controller, config, mqtt_handler)
        print("[DEBUG] Aktoren zurückgesetzt")
        
        # Stoppe MQTT wenn aktiv
        if mqtt_handler:
            print("[DEBUG] Stoppe MQTT Handler...")
            try:
                mqtt_handler.disconnect()
                print("[DEBUG] MQTT Handler gestoppt")
            except Exception as e:
                print(f"[ERROR] Fehler beim Stoppen des MQTT Handlers: {e}")
        
        print("[DEBUG] System erfolgreich beendet")

if __name__ == "__main__":
    main()