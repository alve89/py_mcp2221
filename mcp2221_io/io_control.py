# io_control.py
# Version: 3.1.0

from abc import ABC, abstractmethod
from typing import Dict, List, Callable, Optional, Any
import threading
import time
import select
import sys

from .io_actor import Actor
from .io_sensor import Sensor
from .io_cover import Cover, CoverState
from .logging_config import logger, LogCategory
from .debug_mixin import DebugMixin

class InputEvent:
    """Repräsentiert ein Eingabe-Event"""
    def __init__(self, source: str, action: str, target: str, value: any = None):
        self.source = source
        self.action = action
        self.target = target
        self.value = value

class InputHandler(ABC):
    """Abstrakte Basisklasse für Input Handler"""
    def __init__(self):
        self.observers: List[Callable[[InputEvent], None]] = []
        self._running = False
        self._thread = None

    def add_observer(self, observer: Callable[[InputEvent], None]):
        self.observers.append(observer)

    def notify_observers(self, event: InputEvent):
        for observer in self.observers:
            observer(event)

    @abstractmethod
    def _handle_input(self):
        pass

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)  # Warte maximal 1 Sekunde

    def _run(self):
        while self._running:
            self._handle_input()

class SimpleInputHandler(InputHandler):
    """Einfacher Input Handler basierend auf input() mit Timeout"""
    def __init__(self, key_mappings: Dict[str, tuple]):
        super().__init__()
        self.key_mappings = key_mappings

    def _handle_input(self):
        try:
            # Prüfe, ob Eingabe verfügbar ist
            if select.select([sys.stdin], [], [], 0.1)[0]:  # 100ms Timeout
                key = sys.stdin.readline().strip()
                if key:  # Ignoriere leere Eingaben
                    logger.debug(f"Taste empfangen: {key}", LogCategory.SYSTEM)
                    if key in self.key_mappings:
                        logger.debug(f"Taste {key} ist in key_mappings", LogCategory.SYSTEM)
                        if isinstance(self.key_mappings[key], tuple) and len(self.key_mappings[key]) >= 2:
                            target, action = self.key_mappings[key][0:2]
                            value = self.key_mappings[key][2] if len(self.key_mappings[key]) > 2 else None
                        elif isinstance(self.key_mappings[key], dict):
                            target = self.key_mappings[key].get('target', 'system')
                            action = self.key_mappings[key].get('action', 'unknown')
                            value = self.key_mappings[key].get('value', None)
                        else:
                            logger.error(f"Ungültiges Format für key_mapping: {self.key_mappings[key]}", LogCategory.SYSTEM)
                            return
                            
                        event = InputEvent('input', action, target, value)
                        self.notify_observers(event)
                    else:
                        logger.debug(f"Taste {key} nicht in key_mappings!", LogCategory.SYSTEM)
        except EOFError:
            self._running = False
        except Exception as e:
            logger.error(f"Fehler beim Lesen der Eingabe: {e}", LogCategory.SYSTEM)
            if not self._running:  # Wenn wir uns im Shutdown befinden
                return

class IOController(DebugMixin):
    """Zentrale Steuerungsklasse für das IO-System"""
    def __init__(self, debug_config={}):
        self._init_debug_config(debug_config)
        self.actors: Dict[str, Actor] = {}
        self.sensors: Dict[str, Sensor] = {}
        self.covers: Dict[str, Cover] = {}  # Neu für Cover-Entitäten
        self.input_handlers: List[InputHandler] = []
        self.running = False
        self.mqtt_handler = None
        self.actor_states = {}  # Speichert den letzten bekannten State jedes Actors
        self.cover_states = {}  # Speichert den letzten bekannten State jedes Covers
        self.sensor_map = {}    # Speichert zugeordnete Sensoren (z.B. für Cover)

    def add_actor(self, name: str, actor: Actor):
        """Fügt einen Actor hinzu"""
        self.debug_system_process(f"Actor {name} hinzugefügt")
        self.actors[name] = actor
        self.actor_states[name] = actor.state  # Initialen Zustand speichern

    def add_sensor(self, name: str, sensor: Sensor):
        """Fügt einen Sensor hinzu"""
        self.debug_system_process(f"Sensor {name} hinzugefügt")
        self.sensors[name] = sensor

    def add_cover(self, name: str, cover: Cover, sensor_open_id: str = None, sensor_closed_id: str = None):
        """Fügt ein Cover hinzu und verknüpft es mit Sensoren"""
        self.debug_system_process(f"Cover {name} hinzugefügt")
        self.covers[name] = cover
        self.cover_states[name] = cover.state  # Initialen Zustand speichern
        
        # Sensoren zum Cover-Mapping hinzufügen für spätere Zustandsaktualisierungen
        if sensor_open_id:
            if sensor_open_id not in self.sensor_map:
                self.sensor_map[sensor_open_id] = []
            self.sensor_map[sensor_open_id].append(("cover_open", name))
            
        if sensor_closed_id:
            if sensor_closed_id not in self.sensor_map:
                self.sensor_map[sensor_closed_id] = []
            self.sensor_map[sensor_closed_id].append(("cover_closed", name))

    def add_input_handler(self, handler: InputHandler):
        """Fügt einen Input Handler hinzu"""
        self.debug_system_process("Input Handler wird hinzugefügt")
        handler.add_observer(self._handle_event)
        self.input_handlers.append(handler)
        handler.start()
        self.debug_system_process("Input Handler wurde gestartet")

    def start(self):
        """Startet den Controller"""
        self.debug_system_process("Starte Controller")
        self.running = True
        for handler in self.input_handlers:
            handler.start()

    def stop(self):
        """Stoppt den Controller"""
        self.debug_system_process("Stoppe Controller")
        self.running = False
        for handler in self.input_handlers:
            handler.stop()

    def initialize_covers(self):
        """Initialisiert alle Cover-Zustände basierend auf aktuellen Sensorzuständen"""
        self.debug_system_process("Initialisiere Cover-Zustände")
        
        for cover_id, cover in self.covers.items():
            # Suche die zugehörigen Sensor-IDs
            sensor_open_id = cover.sensor_open_id
            sensor_closed_id = cover.sensor_closed_id
            
            if sensor_open_id and sensor_closed_id:
                if sensor_open_id in self.sensors and sensor_closed_id in self.sensors:
                    # Führe ein Force-Update für die Sensoren durch
                    if hasattr(self.sensors[sensor_open_id], 'force_update'):
                        self.sensors[sensor_open_id].force_update()
                    if hasattr(self.sensors[sensor_closed_id], 'force_update'):
                        self.sensors[sensor_closed_id].force_update()
                    
                    # Lese aktuelle Zustände
                    sensor_open_state = self.sensors[sensor_open_id].state
                    sensor_closed_state = self.sensors[sensor_closed_id].state
                    
                    # Debug-Ausgabe vor der Aktualisierung mit aktuellem Sensor-Status
                    logger.info(f"Cover {cover_id} initialisiert Sensorzustände: open={sensor_open_state}, closed={sensor_closed_state}", LogCategory.COVER)
                    
                    # Aktualisiere Cover-Zustand
                    cover.update_sensor_states(sensor_open_state, sensor_closed_state)
                    
                    logger.info(f"Cover {cover_id} initialisiert: open={sensor_open_state}, closed={sensor_closed_state}, state={cover.state}", LogCategory.COVER)
                    
                    # MQTT aktualisieren
                    if self.mqtt_handler:
                        self.mqtt_handler.publish_cover_state(cover_id, cover.state)
                else:
                    logger.error(f"Sensor(en) für Cover {cover_id} nicht gefunden: open={sensor_open_id}, closed={sensor_closed_id}", LogCategory.COVER)
            else:
                logger.info(f"Cover {cover_id} hat keine Sensoren konfiguriert", LogCategory.COVER)

    def set_mqtt_handler(self, mqtt_handler):
        """Setzt den MQTT Handler und registriert Callbacks"""
        self.mqtt_handler = mqtt_handler
        
        # Für jeden Actor einen Callback registrieren
        for actor_id, actor in self.actors.items():
            actor_config = mqtt_handler.config['actors'].get(actor_id, {})
            entity_type = actor_config.get('entity_type', 'switch').lower()
            
            self.debug_system_process(f"Registriere MQTT Command Callback für {actor_id}")
            mqtt_handler.register_command_callback(actor_id, self._handle_mqtt_command)
            
            # Reset-Callback registrieren wenn Reset-Delay konfiguriert
            if actor_config.get('auto_reset', False) and float(actor_config.get('reset_delay', 0)) > 0:
                def create_reset_handler(aid, a_type):
                    def on_reset():
                        self.debug_actor_state(aid, "reset", "Reset-Event ausgelöst")
                        
                        # Für Cover keine MQTT-Befehle beim Reset
                        if a_type == 'cover':
                            # Für Cover den Actor direkt zurücksetzen ohne MQTT
                            actor = self.actors[aid]
                            actor.set(False)
                            return
                            
                        # Für andere Typen normales MQTT-Command-Handling
                        if self.mqtt_handler:
                            if a_type == 'lock':
                                # Nach Reset wieder LOCK
                                self._handle_mqtt_command(aid, "LOCK")
                            else:
                                # Nach Reset wieder OFF
                                self._handle_mqtt_command(aid, "OFF")
                    return on_reset
                
                # Callback an Actor binden
                actor.on_reset = create_reset_handler(actor_id, entity_type)
                self.debug_system_process(f"Reset-Handler für {actor_id} registriert (Typ: {entity_type})")
            
            # Startup State setzen
            startup_state = mqtt_handler.get_startup_state(actor_id)
            self.debug_system_process(f"Setze Startup State für {actor_id}: {startup_state}")
            
            # Cover speziell behandeln
            if entity_type == 'cover':
                # Für Cover benötigen wir keine spezielle Startup-State-Behandlung,
                # da der Zustand durch die Sensoren bestimmt wird.
                continue
            
            # State basierend auf Entity-Typ setzen
            if entity_type == 'lock':
                command = "LOCK" if not startup_state else "UNLOCK"
                self.debug_actor_state(actor_id, "startup", f"State={startup_state}, Command={command}")
            elif entity_type == 'switch':
                command = "ON" if startup_state else "OFF"
            elif entity_type == 'button':
                self.debug_actor_state(actor_id, "startup", "Button initialisiert")
                continue
                
            self._execute_actor_command(actor_id, command)
            
        # Für jeden Sensor einen Callback registrieren
        for sensor_id, sensor in self.sensors.items():
            def create_sensor_callback(sid):
                def on_state_changed(state):
                    self.debug_sensor_state(sid, "state_change", f"Neuer Zustand: {state}")
                    
                    # Detaillierte Logging-Ausgabe für Sensor-Zustandsänderungen
                    logger.info(f"{sid} - Zustandsänderung erkannt: {state}", LogCategory.SENSOR)
                    
                    # Aktualisiere verbundene Cover-Entities
                    self._update_related_covers(sid, state)
                    
                    if self.mqtt_handler:
                        self.mqtt_handler.publish_sensor_state(sid, state)
                return on_state_changed
            
            # Callback an Sensor binden
            sensor.set_state_changed_callback(create_sensor_callback(sensor_id))
            self.debug_system_process(f"Sensor-State-Callback für {sensor_id} registriert")
            
        # Für jedes Cover einen Callback registrieren
        for cover_id, cover in self.covers.items():
            def create_cover_callback(cid):
                def on_state_changed(state):
                    self.debug_system_process(f"Cover {cid} Zustandsänderung: {state}")
                    self.cover_states[cid] = state  # Zustand speichern
                    
                    # Detaillierte Logging-Ausgabe für Cover-Zustandsänderungen
                    logger.info(f"{cid} - Zustandsänderung auf: {state}", LogCategory.COVER)
                    
                    if self.mqtt_handler:
                        logger.info(f"Publiziere MQTT State für {cid}: {state}", LogCategory.COVER)
                        self.mqtt_handler.publish_cover_state(cid, state)
                return on_state_changed
            
            # Callback an Cover binden
            cover.set_state_changed_callback(create_cover_callback(cover_id))
            self.debug_system_process(f"Cover-State-Callback für {cover_id} registriert")
        
        # Initialisiere Cover-Zustände nach der Registrierung aller Callbacks
        self.initialize_covers()

    def _update_related_covers(self, sensor_id: str, sensor_state: bool):
        """Aktualisiert die Zustände von Covers, die mit diesem Sensor verbunden sind"""
        if sensor_id not in self.sensor_map:
            return
            
        for sensor_type, cover_id in self.sensor_map[sensor_id]:
            if cover_id in self.covers:
                cover = self.covers[cover_id]
                
                # Aktuelle Sensorzustände direkt aus den Sensoren abrufen
                sensor_open_id = cover.sensor_open_id
                sensor_closed_id = cover.sensor_closed_id
                
                # Beide Sensorzustände direkt abrufen für korrekte Zustandsberechnung
                sensor_open_state = self.sensors[sensor_open_id].state if sensor_open_id in self.sensors else False
                sensor_closed_state = self.sensors[sensor_closed_id].state if sensor_closed_id in self.sensors else False
                
                # Ausführlicheres Logging vor der Aktualisierung
                logger.info(f"Aktualisiere {cover_id} basierend auf Sensor {sensor_id}={sensor_state}", LogCategory.COVER)
                logger.info(f"{cover_id} Sensor-Zustände: open({sensor_open_id})={sensor_open_state}, closed({sensor_closed_id})={sensor_closed_state}", LogCategory.COVER)
                logger.info(f"{cover_id} Aktueller Zustand vor Update: {cover.state}", LogCategory.COVER)
                
                # Cover-Zustand aktualisieren mit aktuellen Sensorwerten
                cover.update_sensor_states(sensor_open_state, sensor_closed_state)
                
                # Debug-Logging nach der Aktualisierung
                self.debug_system_process(
                    f"Cover {cover_id} Sensoren aktualisiert: "
                    f"open={sensor_open_state}, closed={sensor_closed_state}, state={cover.state}"
                )
                
                # Ausführlicheres Logging nach der Aktualisierung
                logger.info(f"{cover_id} Neuer Zustand nach Update: {cover.state}", LogCategory.COVER)

    def _handle_mqtt_command(self, actor_id: str, command: str):
        """Verarbeitet MQTT-Kommandos"""
        self.debug_system_process(f"MQTT Kommando empfangen: {actor_id} -> {command}")
        
        # Cover speziell behandeln
        if actor_id in self.covers:
            self._execute_cover_command(actor_id, command)
            return
        
        if actor_id in self.actors:
            # Explizites Logging vor der Ausführung des Kommandos
            self.debug_actor_state(actor_id, "mqtt_command_received", f"Kommando: {command}")
            self._execute_actor_command(actor_id, command)
        else:
            self.debug_system_error(f"Unbekannter Actor: {actor_id}")

    def _execute_cover_command(self, cover_id: str, command: str):
        """Führt ein Kommando für ein Cover aus"""
        if cover_id not in self.covers:
            self.debug_system_error(f"Unbekanntes Cover: {cover_id}")
            return
            
        cover = self.covers[cover_id]
        command = command.upper()
        
        self.debug_system_process(f"Cover-Kommando: {cover_id} -> {command}")
        logger.info(f"Führe Kommando aus für {cover_id}: {command}", LogCategory.COVER)
        
        if command == "OPEN":
            cover.open()
        elif command == "CLOSE":
            cover.close()
        elif command == "STOP":
            cover.stop()
        elif command == "TOGGLE":
            # Immer einen neuen Impuls senden, unabhängig vom aktuellen Zustand
            # Das ist wichtig für Garagentore, die über einen einfachen Impuls gesteuert werden
            cover.toggle()
        else:
            self.debug_system_error(f"Unbekanntes Cover-Kommando: {command}")

    def _execute_actor_command(self, actor_id: str, command: str):
        """Führt ein Kommando für einen Actor aus"""
        if actor_id not in self.actors:
            self.debug_system_error(f"Unbekannter Actor: {actor_id}")
            return

        actor = self.actors[actor_id]
        if not self.mqtt_handler or 'actors' not in self.mqtt_handler.config:
            self.debug_system_error(f"MQTT Handler nicht konfiguriert - Kommando für {actor_id} kann nicht ausgeführt werden")
            return
            
        actor_config = self.mqtt_handler.config['actors'].get(actor_id, {})
        entity_type = actor_config.get('entity_type', 'switch').lower()
        
        self.debug_actor_state(actor_id, "execute_command", f"Kommando: {command}, Typ: {entity_type}")
        
        # Prüfen, ob sich der Zustand wirklich ändern würde
        current_state = actor.state
        new_state = False  # Standardwert
        
        if entity_type == 'switch':
            new_state = (command == "ON")
        elif entity_type == 'lock':
            new_state = (command == "UNLOCK")
        elif entity_type == 'button':
            new_state = True  # Buttons ändern ihren internen Zustand immer
        
        # Prüfen, ob der Zustand sich tatsächlich ändern würde
        if current_state == new_state and entity_type != 'button':
            self.debug_actor_state(
                actor_id, 
                "unchanged_state", 
                f"Zustand unverändert: {current_state}, keine Aktion notwendig"
            )
            return
        
        # Ab hier normaler Ablauf für Zustandsänderungen
        if entity_type == 'switch':
            # Physischen Zustand setzen
            self.debug_actor_state(actor_id, "set_state", f"Kommando={command}, new_state={new_state}")
            actor.set(new_state)
            self.actor_states[actor_id] = new_state  # Zustand merken
            
            # MQTT updaten
            if self.mqtt_handler:
                # State Topic aktualisieren mit retain=True
                self.mqtt_handler.mqtt_client.publish(
                    f"{self.mqtt_handler.base_topic}/{actor_id}/state",
                    command,
                    qos=1,
                    retain=True
                )
                self.debug_actor_state(actor_id, "mqtt_state", f"MQTT State: {command} (retained)")
                
        elif entity_type == 'lock':
            # Analog zu switch: UNLOCK = ON (True)
            self.debug_actor_state(actor_id, "set_state", f"Kommando={command}, new_state={new_state}")
            actor.set(new_state)
            self.actor_states[actor_id] = new_state  # Zustand merken
            
            # MQTT updaten
            if self.mqtt_handler:
                # State Topic aktualisieren mit retain=True
                state = "UNLOCKED" if new_state else "LOCKED"
                self.mqtt_handler.mqtt_client.publish(
                    f"{self.mqtt_handler.base_topic}/{actor_id}/state",
                    state,
                    qos=1,
                    retain=True
                )
                self.debug_actor_state(actor_id, "mqtt_state", f"MQTT State: {state} (retained)")
        
        elif entity_type == 'button':
            # Buttons haben kein MQTT-State-Topic, nur Command
            self.debug_actor_state(actor_id, "button_press", "Button gedrückt")
            actor.set(True)  # Button ist nur kurz aktiv
            self.actor_states[actor_id] = True  # Zustand merken

    def _handle_event(self, event: InputEvent):
        """Verarbeitet Events von Input Handlern"""
        self.debug_system_process(f"Event empfangen: {event.source} -> {event.target}:{event.action}")
        
        # Spezialbehandlung für System-Events
        if event.target == 'system':
            if event.action == 'quit':
                self.debug_system_process("Quit-Command empfangen, beende Programm...")
                self.running = False
            return
        
        # Cover-Events speziell behandeln
        if event.target in self.covers:
            self.debug_system_process(f"Cover-Event verarbeiten: {event.target} -> {event.action}")
            logger.info(f"Event empfangen: {event.target} -> {event.action}", LogCategory.COVER)
            
            # Kommando über MQTT set senden
            if self.mqtt_handler:
                if event.action == 'toggle':
                    command = "TOGGLE"
                elif event.action == 'open':
                    command = "OPEN"
                elif event.action == 'close':
                    command = "CLOSE"
                elif event.action == 'stop':
                    command = "STOP"
                else:
                    command = "TOGGLE"  # Fallback
                
                # Direktes Logging, um die Ausführung zu verfolgen
                logger.info(f"Sende Cover-Kommando an MQTT: {event.target} -> {command}", LogCategory.COVER)
                self.mqtt_handler.publish_command(event.target, command)
            else:
                # Wenn kein MQTT-Handler verfügbar ist, führe das Kommando direkt aus
                logger.info(f"Führe Cover-Kommando direkt aus: {event.target} -> {event.action}", LogCategory.COVER)
                if event.action == 'toggle':
                    self.covers[event.target].toggle()
                elif event.action == 'open':
                    self.covers[event.target].open()
                elif event.action == 'close':
                    self.covers[event.target].close()
                elif event.action == 'stop':
                    self.covers[event.target].stop()
                else:
                    self.covers[event.target].toggle()  # Fallback
            return
        
        # Normale Actor-Events über MQTT-Set routen
        if event.target in self.actors:
            self.debug_actor_state(event.target, "input_event", f"Action: {event.action}")
            
            if not self.mqtt_handler:
                self.debug_system_error("MQTT Handler nicht verfügbar - Kommando kann nicht gesendet werden")
                return
                
            actor_config = self.mqtt_handler.config['actors'].get(event.target, {})
            entity_type = actor_config.get('entity_type', 'switch').lower()
            
            # Kommando über MQTT set senden
            if entity_type == 'switch':
                if event.action == 'toggle':
                    current_state = self.actors[event.target].state
                    command = "OFF" if current_state else "ON"
                else:
                    command = "ON" if event.value else "OFF"
            elif entity_type == 'button':
                command = "ON"  # Buttons immer ON senden
            elif entity_type == 'lock':
                if event.action == 'toggle':
                    current_state = self.actors[event.target].state
                    command = "LOCK" if current_state else "UNLOCK"
                else:
                    command = "LOCK" if event.value else "UNLOCK"
            else:
                self.debug_system_error(f"Unbekannter Entity-Typ: {entity_type}")
                return
            
            self.mqtt_handler.publish_command(event.target, command)