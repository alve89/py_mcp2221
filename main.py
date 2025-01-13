# mcp2221_io/main.py

import os
import time
import yaml

# Umgebungsvariable MUSS vor board/digitalio Import gesetzt werden
os.environ['BLINKA_MCP2221'] = '1'

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
            actor = Actor(cfg['pin'], inverted=cfg.get('inverted', False))
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
            controller.set_mqtt_handler(mqtt_handler)  # MQTT Handler dem Controller zuweisen
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
            print(f"  {key}: {cfg['action'].capitalize()} {config['actors'][cfg['target']]['description']} (GPIO '{config['actors'][cfg['target']]['pin']}')")
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