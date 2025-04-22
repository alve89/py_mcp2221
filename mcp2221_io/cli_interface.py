# cli_interface.py
# Version: 1.8.1

import time
import os
import sys
import copy
import select
from termcolor import colored
from mcp2221_io import InputEvent
import pprint

def format_debug_parameter(key, value, indent=0):
    prefix = "  " * indent
    if isinstance(value, bool):
        symbol = "✅" if value else "❌"
        return f"{prefix}{key}: {symbol}"
    elif isinstance(value, dict):
        lines = [f"{prefix}{key}:"]
        for subkey, subval in value.items():
            lines.append(format_debug_parameter(subkey, subval, indent + 1))
        return "\n".join(lines)
    else:
        return f"{prefix}{key}: {value}"

def format_debug_overview(debug_cfg):
    for key, value in debug_cfg.items():
        for line in format_debug_parameter(key, value).splitlines():
            print(colored(line, "yellow"))

def run_cli_sensor_tests(controller, config, key_mappings):
    debug_config = config.get('debugging', {})
    cli_poll_interval = float(debug_config.get('poll_interval', 0.1))

    while True:
        print("\n--- Sensor Test Menü ---")
        print(colored("Hinweis: Der dargestellte Status dient nur zu Debugging-Zwecken und entspricht nicht zwingend dem physikalischen Pin-Zustand.", "red"))
        sensor_ids = list(controller.sensors.keys())
        for idx, sid in enumerate(sensor_ids):
            print(f"{idx + 1}: Live-Poll {sid}")
        print("a: Alle Sensoren live-pollen")
        print("q: Zurück zum Hauptmenü")

        try:
            choice = input("Auswahl: ").strip()
            if choice.lower() == 'q':
                print("\nZurück zum Hauptmenü.")
                print_main_menu(key_mappings)
                break
            elif choice.lower() == 'a':
                run_live_polling_all_sensors(controller, cli_poll_interval)
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(sensor_ids):
                    sensor_id = sensor_ids[idx]
                    sensor = controller.sensors[sensor_id]
                    run_live_polling_single_sensor(sensor_id, sensor, cli_poll_interval)
                else:
                    print("❌ Ungültige Auswahl.")
            else:
                print("❌ Bitte eine Zahl, 'a' oder 'q' eingeben.")
        except KeyboardInterrupt:
            print("\nAbbruch – zurück zum Hauptmenü.")
            print_main_menu(key_mappings)
            break

def run_live_polling_all_sensors(controller, poll_interval):
    """Führt Live-Polling für alle Sensoren durch, beendbar mit 'q'"""
    print("\nLive-Polling aller Sensoren – Gib 'q' ein und drücke Enter zum Beenden")
    print(colored("Polling-Interval: " + str(poll_interval) + " Sekunden", "cyan"))
    
    running = True
    while running:
        # Zeige Sensor-Status
        for sensor_id, sensor in controller.sensors.items():
            if hasattr(sensor, "sync_poll_once"):
                try:
                    raw, state = sensor.sync_poll_once()
                    color = 'green' if state else 'red'
                    print(f"{sensor_id}: Raw={raw}, State=" + colored(str(state), color))
                except Exception as e:
                    print(f"Fehler bei {sensor_id}: {e}")
        
        # Prüfe, ob 'q' eingegeben wurde (ohne zu blockieren)
        # Wir nutzen select um non-blocking I/O zu erreichen
        if select.select([sys.stdin], [], [], 0)[0]:
            key = sys.stdin.readline().strip()
            if key.lower() == 'q':
                print("\nLive-Polling beendet.")
                return
        
        # Warte entsprechend des Poll-Intervalls
        time.sleep(poll_interval)

def run_live_polling_single_sensor(sensor_id, sensor, poll_interval):
    """Führt Live-Polling für einen einzelnen Sensor durch, beendbar mit 'q'"""
    print(f"\nLive-Polling für {sensor_id} – Gib 'q' ein und drücke Enter zum Beenden")
    print(colored("Polling-Interval: " + str(poll_interval) + " Sekunden", "cyan"))
    
    running = True
    while running:
        # Zeige Sensor-Status
        if hasattr(sensor, "sync_poll_once"):
            try:
                raw, state = sensor.sync_poll_once()
                color = 'green' if state else 'red'
                print(f"{sensor_id}: Raw={raw}, State=" + colored(str(state), color))
            except Exception as e:
                print(f"Fehler bei {sensor_id}: {e}")
        
        # Prüfe, ob 'q' eingegeben wurde (ohne zu blockieren)
        if select.select([sys.stdin], [], [], 0)[0]:
            key = sys.stdin.readline().strip()
            if key.lower() == 'q':
                print("\nLive-Polling beendet.")
                return
        
        # Warte entsprechend des Poll-Intervalls
        time.sleep(poll_interval)

def execute_system_command(command, controller, mqtt_handler=None, config=None):
    from mcp2221_io.logging_config import logger, set_debug_mode

    logger.info(f"Führe System-Befehl aus: {command}")
    if command == "test_sensors":
        if config is not None:
            key_mappings = config.get('key_mappings', {})
            run_cli_sensor_tests(controller, config, key_mappings)
            return True

    elif command == "diagnose":
        if mqtt_handler:
            logger.info("Starte Systemdiagnose...")
            board_status = mqtt_handler._board_status
            board_message = mqtt_handler._board_status_message
            logger.info(f"Board-Status: {'Online' if board_status else 'Offline'} - {board_message}")
            mqtt_connected = mqtt_handler.connected.is_set()
            logger.info(f"MQTT-Verbindung: {'Verbunden' if mqtt_connected else 'Nicht verbunden'}")
            if hasattr(mqtt_handler, 'test_sensor_pins'):
                mqtt_handler.test_sensor_pins()
        logger.info("Actor-Status:")
        for actor_id, actor in controller.actors.items():
            if actor:
                state = actor.state
                logger.info(f"  - {actor_id}: {state}")
        logger.info("Systemdiagnose abgeschlossen.")

        while True:
            print("\n--- Diagnose-Menü ---")
            print("c: Konfiguration anzeigen")
            print("l: Live-Logging anzeigen")
            print("q: Zurück zum Hauptmenü")
            sub = input("Auswahl: ").strip().lower()
            if sub == 'q':
                print_main_menu(config.get('key_mappings', {}))
                break
            elif sub == 'c':
                print("\n[Gesamte Konfiguration]")
                pprint.pprint(config)
            elif sub == 'l':
                print("\n[Info] Live-Logging ist aktiviert gemäß 'debugging.level' in config.yaml.")
                
                # Aktiviere manuell die Debug-Flags für die Übersicht, ohne die Original-Konfiguration zu ändern
                # Erstelle eine tiefe Kopie der Konfiguration
                display_config = copy.deepcopy(config.get("debugging", {}))
                
                # Sicherstellen, dass System-Debugging jetzt aktiviert ist (für die Anzeige)
                if 'system' not in display_config:
                    display_config['system'] = {}
                if 'process' not in display_config['system']:
                    display_config['system']['process'] = True
                else:
                    display_config['system']['process'] = True
                
                if 'entities' not in display_config['system']:
                    display_config['system']['entities'] = {}
                
                # Explizit Actors und Sensors aktivieren
                display_config['system']['entities']['actors'] = True
                display_config['system']['entities']['sensors'] = True
                
                print(colored("Hinweis: Folgende Debug-Konfiguration wird für das Live-Logging verwendet:", "cyan"))
                format_debug_overview(display_config)
                
                print("\nLive-Logging gestartet. Gib 'q' ein und drücke Enter zum Beenden...")
                
                # Temporär Debug-Modus aktivieren - wirklich auf True setzen
                from mcp2221_io.logging_config import set_debug_mode, logger
                old_debug = os.environ.get('MCP2221_DEBUG', '0')
                os.environ['MCP2221_DEBUG'] = '1'  # Direkt setzen
                set_debug_mode(True)
                
                # Die bestehenden Logger neu konfigurieren, um alle Nachrichten anzuzeigen
                import logging
                root_logger = logging.getLogger()
                old_level = root_logger.level
                root_logger.setLevel(logging.DEBUG)
                
                # Sicherstellen, dass die Sensoren und Aktoren jetzt auch wirklich Debug-Logs senden
                # Wir aktivieren hier direkt die Debug-Konfiguration in allen Komponenten
                for _, actor in controller.actors.items():
                    if hasattr(actor, 'debug_actors'):
                        actor.debug_actors = True
                
                for _, sensor in controller.sensors.items():
                    if hasattr(sensor, 'debug_sensors'):
                        sensor.debug_sensors = True
                    if hasattr(sensor, '_init_system_debug_config'):
                        # Sensor-Debug-Konfiguration neu initialisieren
                        temp_debug_config = copy.deepcopy(config.get('debugging', {}))
                        if 'system' in temp_debug_config:
                            if 'entities' in temp_debug_config['system']:
                                temp_debug_config['system']['entities']['sensors'] = True
                        sensor._init_system_debug_config(temp_debug_config)
                
                # Auch Controller-Debug-Konfiguration aktualisieren
                if hasattr(controller, 'debug_actors'):
                    controller.debug_actors = True
                if hasattr(controller, 'debug_sensors'):
                    controller.debug_sensors = True
                if hasattr(controller, 'debug_process'):
                    controller.debug_process = True
                
                # MQTT-Callback für die Nachrichtenverfolgung aktivieren, wenn MQTT verbunden ist
                original_on_message = None
                original_on_publish = None
                
                if mqtt_handler and mqtt_handler.connected.is_set():
                    print(colored("MQTT verbunden - Ereignisse werden angezeigt", "green"))
                    
                    # Original-Callbacks speichern
                    if hasattr(mqtt_handler.mqtt_client, 'on_message'):
                        original_on_message = mqtt_handler.mqtt_client.on_message
                    
                    if hasattr(mqtt_handler.mqtt_client, 'on_publish'):
                        original_on_publish = mqtt_handler.mqtt_client.on_publish
                    
                    # Debug-Callbacks installieren
                    def debug_on_message(client, userdata, message):
                        topic = message.topic
                        payload = message.payload.decode()
                        
                        # Verbesserte Debug-Ausgabe mit Nachrichtentyp-Identifikation
                        topic_parts = topic.split('/')
                        msg_type = ""
                        if len(topic_parts) >= 3:
                            if topic_parts[-1] == "set":
                                msg_type = " [COMMAND]"
                            elif topic_parts[-1] == "state":
                                msg_type = " [STATE]"
                            elif "status" in topic_parts[-1]:
                                msg_type = " [STATUS]"
                                
                        # Target-Gerät identifizieren (wenn vorhanden)
                        target = ""
                        if len(topic_parts) >= 2 and topic_parts[0] == mqtt_handler.base_topic:
                            target = f" [Device={topic_parts[1]}]"
                        
                        logger.debug(f"[MQTT RECV] Topic={topic}{msg_type}{target} Payload={payload}")
                        
                        # Original-Callback trotzdem ausführen
                        if original_on_message:
                            original_on_message(client, userdata, message)
                    
                    def debug_on_publish(client, userdata, mid):
                        # Reduzierte Ausgabe für Message IDs, da diese bereits bei publish detaillierter geloggt werden
                        if mqtt_handler.debug_mode and mqtt_handler.debug_send:
                            logger.debug(f"[MQTT SEND] Message ID={mid}")
                        # Original-Callback trotzdem ausführen
                        if original_on_publish:
                            original_on_publish(client, userdata, mid)
                    
                    # Debug-Callbacks aktivieren
                    mqtt_handler.mqtt_client.on_message = debug_on_message
                    mqtt_handler.mqtt_client.on_publish = debug_on_publish
                    
                    # Ein paar MQTT-Test-Nachrichten senden, um zu zeigen, dass das Logging funktioniert
                    logger.info("MQTT-Debug aktiviert. Sende Test-Nachrichten...")
                    try:
                        mqtt_handler.publish_debug_message("Live-Logging aktiviert")
                        # Teste jeden Aktor mit einer Status-Abfrage
                        for actor_id in controller.actors:
                            logger.debug(f"Frage Status von {actor_id} ab")
                            if mqtt_handler:
                                state_topic = f"{mqtt_handler.base_topic}/{actor_id}/state"
                                mqtt_handler.mqtt_client.publish(
                                    state_topic,
                                    "",  # Leere Nachricht, um nur das Logging zu testen
                                    qos=0,
                                    retain=False
                                )
                    except Exception as e:
                        logger.error(f"Fehler beim Senden der MQTT-Test-Nachrichten: {e}")
                else:
                    print(colored("MQTT nicht verbunden - keine MQTT-Ereignisse verfügbar", "red"))
                
                # Aktiviere explizit Sensor-Polling für Debug-Ausgaben
                logger.info("Starte Sensor-Polling für Debug-Ausgaben...")
                # Führe einen Test für alle Sensoren durch, um Debug-Ausgaben zu generieren
                for sensor_id, sensor in controller.sensors.items():
                    if hasattr(sensor, "sync_poll_once"):
                        try:
                            logger.debug(f"[Sensor] Polling {sensor_id}")
                            raw, state = sensor.sync_poll_once()
                            logger.debug(f"[Sensor] {sensor_id}: Raw={raw}, State={state}")
                        except Exception as e:
                            logger.error(f"[Sensor] Fehler beim Polling von {sensor_id}: {e}")
                
                # Aktivere Polling-Schleife, die auch MQTT-Events und Controller-Status prüft
                print(colored("Drücke q + Enter zum Beenden, eine andere Taste für eine Log-Nachricht", "cyan"))
                try:
                    # Aktive Polling-Schleife mit regelmäßigen Status-Updates
                    count = 0
                    running = True
                    while running:
                        time.sleep(0.1)
                        
                        # Regelmäßig Log-Status ausgeben, um zu zeigen dass das Logging funktioniert
                        count += 1
                        if count % 100 == 0:  # Alle 10 Sekunden
                            logger.debug(f"Live-Logging aktiv seit {count/10:.1f} Sekunden")
                            
                            # Prüfe MQTT-Status, falls verbunden
                            if mqtt_handler and mqtt_handler.connected.is_set():
                                logger.debug(f"MQTT verbunden zu {mqtt_handler.config.get('broker')}")
                                
                            # Prüfe Controller-Status
                            actor_states = {aid: actor.state for aid, actor in controller.actors.items()}
                            logger.debug(f"Aktor-Status: {actor_states}")
                            
                            # Aktives Polling aller Sensoren alle 10 Sekunden
                            for sensor_id, sensor in controller.sensors.items():
                                if hasattr(sensor, "sync_poll_once"):
                                    try:
                                        logger.debug(f"[Sensor] Polling {sensor_id}")
                                        raw, state = sensor.sync_poll_once()
                                        logger.debug(f"[Sensor] {sensor_id}: Raw={raw}, State={state}")
                                    except Exception as e:
                                        logger.error(f"[Sensor] Fehler beim Polling von {sensor_id}: {e}")
                        
                        # Prüfe, ob eine Taste gedrückt wurde (ohne zu blockieren)
                        if select.select([sys.stdin], [], [], 0)[0]:
                            key = sys.stdin.readline().strip()
                            if key.lower() == 'q':
                                logger.info("Live-Logging wird beendet...")
                                running = False
                            else:
                                logger.info(f"Taste gedrückt: {key}")
                                print(colored(f"Log-Nachricht für Taste '{key}' erzeugt", "cyan"))
                
                except Exception as e:
                    logger.error(f"Fehler im Live-Logging: {e}")
                    print(f"\nFehler im Live-Logging: {e}")
                
                # Ursprüngliche MQTT-Callbacks wiederherstellen
                if mqtt_handler and mqtt_handler.connected.is_set():
                    if original_on_message:
                        mqtt_handler.mqtt_client.on_message = original_on_message
                    if original_on_publish:
                        mqtt_handler.mqtt_client.on_publish = original_on_publish
                
                # Debug-Modus und Logger-Level zurücksetzen
                root_logger.setLevel(old_level)
                os.environ['MCP2221_DEBUG'] = old_debug
                set_debug_mode(old_debug == '1')
                
                print("\nLive-Logging beendet.")
            else:
                print("❌ Ungültige Eingabe. Bitte c, l oder q drücken.")

        return True

    return False

def print_main_menu(key_mappings):
    print("System gestartet. Steuerung:")
    for key, value in key_mappings.items():
        if isinstance(value, dict):
            print(f"  {key}: {value.get('action', '?').capitalize()} {value.get('target', '?')}")
        elif isinstance(value, tuple) and len(value) >= 2:
            print(f"  {key}: {value[1].capitalize()} {value[0]}")
    print("\nBitte Taste eingeben und Enter drücken:")

def custom_event_handler(event, controller, mqtt_handler, config, key_mappings):
    if event.target == 'system' and event.action == 'quit':
        print("Beende das System...")
        controller.running = False
        return

    if event.target == 'system' and event.action in ['test_sensors', 'diagnose']:
        execute_system_command(event.action, controller, mqtt_handler, config=config)

    elif event.target == 'system' and event.action == 'control':
        toggle_actors = [
            aid for aid, cfg in config['actors'].items()
            if cfg.get('entity_type', 'switch').lower() in ['switch', 'lock']
        ]
        if not toggle_actors:
            print("Keine Aktoren mit toggle-Funktion vorhanden.")
            return

        while True:
            print("\n--- Control Menü: Toggle-Aktoren ---")
            for idx, aid in enumerate(toggle_actors):
                print(f"{idx + 1}: Toggle {aid}")
            print("q: Zurück zum Hauptmenü")

            try:
                choice = input("Nummer eingeben: ").strip()
                if choice.lower() == 'q':
                    print("Zurück zum Hauptmenü.\n")
                    print_main_menu(key_mappings)
                    break
                if choice.isdigit():
                    index = int(choice) - 1
                    if 0 <= index < len(toggle_actors):
                        selected = toggle_actors[index]
                        controller._handle_event(InputEvent('input', 'toggle', selected))
                        print(f"[OK] {selected} getoggelt.")
                    else:
                        print("❌ Ungültige Auswahl.")
                else:
                    print("❌ Bitte eine gültige Zahl oder 'q' eingeben.")
            except KeyboardInterrupt:
                print("\nAbbruch – zurück zum Hauptmenü.")
                print_main_menu(key_mappings)
                break
    else:
        controller._handle_event(event)