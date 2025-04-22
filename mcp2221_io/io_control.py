# io_control.py
# Version: 1.8.0

from abc import ABC, abstractmethod
from typing import Dict, List, Callable
import threading
import time
import select
import sys
from .io_actor import Actor
from .io_sensor import Sensor
from .logging_config import logger
from .system_debug import SystemDebugMixin

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
                    logger.debug(f"Taste empfangen: {key}")
                    if key in self.key_mappings:
                        logger.debug(f"Taste {key} ist in key_mappings")
                        target, action, value = self.key_mappings[key]
                        event = InputEvent('input', action, target, value)
                        self.notify_observers(event)
                    else:
                        logger.debug(f"Taste {key} nicht in key_mappings!")
        except EOFError:
            self._running = False
        except Exception as e:
            logger.error(f"Fehler beim Lesen der Eingabe: {e}")
            if not self._running:  # Wenn wir uns im Shutdown befinden
                return

class IOController(SystemDebugMixin):
    """Zentrale Steuerungsklasse für das IO-System"""
    def __init__(self, debug_config={}):
        self._init_system_debug_config(debug_config)
        self.actors: Dict[str, Actor] = {}
        self.sensors: Dict[str, Sensor] = {}
        self.input_handlers: List[InputHandler] = []
        self.running = False
        self.mqtt_handler = None
        self.actor_states = {}  # Speichert den letzten bekannten State jedes Actors

    def add_actor(self, name: str, actor: Actor):
        self.debug_system_process(f"Actor {name} hinzugefügt")
        self.actors[name] = actor
        self.actor_states[name] = actor.state  # Initialen Zustand speichern

    def add_sensor(self, name: str, sensor: Sensor):
        self.debug_system_process(f"Sensor {name} hinzugefügt")
        self.sensors[name] = sensor

    def add_input_handler(self, handler: InputHandler):
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
                def create_reset_handler(aid):
                    def on_reset():
                        self.debug_actor_state(aid, "reset", "Reset-Event ausgelöst")
                        if self.mqtt_handler:
                            if actor_config.get('entity_type') == 'lock':
                                # Nach Reset wieder LOCK
                                self._handle_mqtt_command(aid, "LOCK")
                            else:
                                # Nach Reset wieder OFF
                                self._handle_mqtt_command(aid, "OFF")
                    return on_reset
                
                # Callback an Actor binden
                actor.on_reset = create_reset_handler(actor_id)
                self.debug_system_process(f"Reset-Handler für {actor_id} registriert")
            
            # Startup State setzen
            startup_state = mqtt_handler.get_startup_state(actor_id)
            self.debug_system_process(f"Setze Startup State für {actor_id}: {startup_state}")
            
            # State basierend auf Entity-Typ setzen
            if entity_type == 'lock':
                command = "LOCK" if startup_state else "UNLOCK"
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
                    if self.mqtt_handler:
                        self.mqtt_handler.publish_sensor_state(sid, state)
                return on_state_changed
            
            # Callback an Sensor binden
            sensor.set_state_changed_callback(create_sensor_callback(sensor_id))
            self.debug_system_process(f"Sensor-State-Callback für {sensor_id} registriert")

    def _handle_mqtt_command(self, actor_id: str, command: str):
        """Verarbeitet MQTT-Kommandos"""
        self.debug_system_process(f"MQTT Kommando empfangen: {actor_id} -> {command}")
        if actor_id in self.actors:
            # Explizites Logging vor der Ausführung des Kommandos
            self.debug_actor_state(actor_id, "mqtt_command_received", f"Kommando: {command}")
            self._execute_actor_command(actor_id, command)
        else:
            self.debug_system_error(f"Unbekannter Actor: {actor_id}")

    def _execute_actor_command(self, actor_id: str, command: str):
        """Führt ein Kommando für einen Actor aus"""
        if actor_id not in self.actors:
            self.debug_system_error(f"Unbekannter Actor: {actor_id}")
            return

        actor = self.actors[actor_id]
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
        
        # Normale Actor-Events über MQTT-Set routen
        if event.target in self.actors:
            self.debug_actor_state(event.target, "input_event", f"Action: {event.action}")
            actor_config = self.mqtt_handler.config['actors'].get(event.target, {})
            entity_type = actor_config.get('entity_type', 'switch').lower()
            
            # Kommando über MQTT set senden
            if self.mqtt_handler:
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
                
                self.mqtt_handler.publish_command(event.target, command)
            else:
                self.debug_system_error("MQTT Handler nicht verfügbar - Kommando kann nicht gesendet werden")