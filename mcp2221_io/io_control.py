# io_control.py
# Version: 1.7.1

from abc import ABC, abstractmethod
from typing import Dict, List, Callable
import threading
import time
import select
import sys
from mcp2221_io.io_actor import Actor
from mcp2221_io.io_sensor import Sensor
from mcp2221_io.logging_config import logger
from mcp2221_io.system_debug import SystemDebugMixin

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
            self._thread.join(timeout=1)

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
            if select.select([sys.stdin], [], [], 0.1)[0]:
                key = sys.stdin.readline().strip()
                if key:
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
            if not self._running:
                return

class IOController(SystemDebugMixin):
    """Zentrale Steuerungsklasse für das IO-System"""
    def __init__(self):
        self.actors: Dict[str, Actor] = {}
        self.sensors: Dict[str, Sensor] = {}
        self.input_handlers: List[InputHandler] = []
        self.running = False
        self.mqtt_handler = None
        self._init_system_debug_config({})  # Leere Debug-Konfiguration als Standard

    def add_actor(self, name: str, actor: Actor):
        """Fügt einen Actor hinzu"""
        self.actors[name] = actor
        self.debug_actor_state(name, "initialized", f"Pin: {actor.pin}")
        self.debug_gpio(f"Actor {name} an Pin {actor.pin} hinzugefügt")

    def add_sensor(self, name: str, sensor: Sensor):
        """Fügt einen Sensor hinzu"""
        self.sensors[name] = sensor
        self.debug_sensor_state(name, "initialized", f"Pin: {sensor.pin}")
        self.debug_gpio(f"Sensor {name} an Pin {sensor.pin} hinzugefügt")

    def add_input_handler(self, handler: InputHandler):
        """Fügt einen Input Handler hinzu"""
        handler.add_observer(self._handle_event)
        self.input_handlers.append(handler)
        handler.start()
        self.debug_system_process("Input Handler hinzugefügt und gestartet")

    def start(self):
        """Startet den Controller"""
        self.debug_startup("Controller wird gestartet")
        self.running = True
        for handler in self.input_handlers:
            handler.start()
        self.debug_startup("Controller erfolgreich gestartet")

    def stop(self):
        """Stoppt den Controller"""
        self.debug_shutdown("Controller wird gestoppt")
        self.running = False
        for handler in self.input_handlers:
            handler.stop()
        self.debug_shutdown("Controller erfolgreich gestoppt")

    def set_mqtt_handler(self, mqtt_handler):
        """Setzt den MQTT Handler"""
        self.mqtt_handler = mqtt_handler
        
        # Debug-Konfiguration aktualisieren
        if hasattr(mqtt_handler, 'config'):
            self._init_system_debug_config(mqtt_handler.config)
        
        self.debug_system_process("MQTT Handler konfiguriert")
        
        # Für jeden Actor einen Callback registrieren
        for actor_id, actor in self.actors.items():
            actor_config = mqtt_handler.config['actors'].get(actor_id, {})
            entity_type = actor_config.get('entity_type', 'switch').lower()
            
            mqtt_handler.register_command_callback(actor_id, self._handle_mqtt_command)
            
            # Reset-Callback registrieren wenn Reset-Delay konfiguriert
            if actor_config.get('auto_reset', False) and float(actor_config.get('reset_delay', 0)) > 0:
                def create_reset_handler(aid):
                    def on_reset():
                        self.debug_actor_state(aid, "reset", "Auto-Reset ausgelöst")
                        if self.mqtt_handler:
                            if actor_config.get('entity_type') == 'lock':
                                self._handle_mqtt_command(aid, "LOCK")
                            else:
                                self._handle_mqtt_command(aid, "OFF")
                    return on_reset
                
                # Callback an Actor binden
                actor.on_reset = create_reset_handler(actor_id)
                self.debug_actor_state(actor_id, "reset_handler", f"Reset-Delay: {actor_config.get('reset_delay')}s")
            
            # Startup State setzen
            startup_state = mqtt_handler.get_startup_state(actor_id)
            self.debug_actor_state(actor_id, "startup", f"State: {startup_state}")
            
            # State basierend auf Entity-Typ setzen
            if entity_type == 'lock':
                command = "LOCK" if startup_state else "UNLOCK"
                self.debug_actor_state(actor_id, "startup_command", f"Command: {command}")
            elif entity_type == 'switch':
                command = "ON" if startup_state else "OFF"
            elif entity_type == 'button':
                self.debug_actor_state(actor_id, "startup", "Button initialisiert")
                continue
                
            self._execute_actor_command(actor_id, command)

    def _handle_mqtt_command(self, actor_id: str, command: str):
        """Verarbeitet MQTT-Kommandos"""
        self.debug_actor_state(actor_id, "mqtt_command", f"Command: {command}")
        if actor_id in self.actors:
            self._execute_actor_command(actor_id, command)
        else:
            self.debug_actor_error(actor_id, f"Unbekannter Actor für Command: {command}")

    def _execute_actor_command(self, actor_id: str, command: str):
        """Führt ein Kommando für einen Actor aus"""
        if actor_id not in self.actors:
            self.debug_actor_error(actor_id, f"Unbekannter Actor")
            return

        actor = self.actors[actor_id]
        actor_config = self.mqtt_handler.config['actors'].get(actor_id, {})
        entity_type = actor_config.get('entity_type', 'switch').lower()
        
        self.debug_actor_state(actor_id, "execute_command", f"Command: {command}, Type: {entity_type}")
        
        if entity_type == 'switch':
            new_state = (command == "ON")
            actor.set(new_state)
            self.debug_actor_state(actor_id, "switch_state", f"New state: {new_state}")
            
            if self.mqtt_handler:
                self.mqtt_handler.mqtt_client.publish(
                    f"{self.mqtt_handler.base_topic}/{actor_id}/state",
                    command,
                    qos=1,
                    retain=True
                )
                self.debug_actor_state(actor_id, "mqtt_publish", f"State: {command}")
                
        elif entity_type == 'lock':
            new_state = (command == "UNLOCK")
            actor.set(new_state)
            self.debug_actor_state(actor_id, "lock_state", f"New state: {new_state}")
            
            if self.mqtt_handler:
                state = "UNLOCKED" if new_state else "LOCKED"
                self.mqtt_handler.mqtt_client.publish(
                    f"{self.mqtt_handler.base_topic}/{actor_id}/state",
                    state,
                    qos=1,
                    retain=True
                )
                self.debug_actor_state(actor_id, "mqtt_publish", f"State: {state}")

    def _handle_event(self, event: InputEvent):
        """Verarbeitet Events von Input Handlern"""
        self.debug_system_process(f"Event empfangen: {event.source} -> {event.target}:{event.action}")
        
        if event.target == 'system':
            if event.action == 'quit':
                self.debug_system_process("Quit-Command empfangen")
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
                        self.debug_actor_state(event.target, "toggle", f"Current: {current_state}, New: {command}")
                    else:
                        command = "ON" if event.value else "OFF"
                elif entity_type == 'button':
                    command = "ON"  # Buttons immer ON senden
                    self.debug_actor_state(event.target, "button_press", "Command: ON")
                elif entity_type == 'lock':
                    if event.action == 'toggle':
                        current_state = self.actors[event.target].state
                        command = "LOCK" if current_state else "UNLOCK"
                        self.debug_actor_state(event.target, "toggle", f"Current: {current_state}, New: {command}")
                    else:
                        command = "LOCK" if event.value else "UNLOCK"
                
                self.mqtt_handler.publish_command(event.target, command)
                self.debug_actor_state(event.target, "mqtt_command_sent", f"Command: {command}")
            else:
                self.debug_system_error("MQTT Handler nicht verfügbar - Kommando kann nicht gesendet werden")