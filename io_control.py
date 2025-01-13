# mcp2221_io/io_control.py

from abc import ABC, abstractmethod
from typing import Dict, List, Callable
import threading
import time
import select
import sys
from .io_base import Actor, Sensor

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
                    print(f"[DEBUG] Taste empfangen: {key}")
                    if key in self.key_mappings:
                        print(f"[DEBUG] Taste {key} ist in key_mappings")
                        target, action, value = self.key_mappings[key]
                        event = InputEvent('input', action, target, value)
                        self.notify_observers(event)
                    else:
                        print(f"[DEBUG] Taste {key} nicht in key_mappings!")
        except EOFError:
            self._running = False
        except Exception as e:
            print(f"[ERROR] Fehler beim Lesen der Eingabe: {e}")
            if not self._running:  # Wenn wir uns im Shutdown befinden
                return

class IOController:
    """Zentrale Steuerungsklasse für das IO-System"""
    def __init__(self):
        self.actors: Dict[str, Actor] = {}
        self.sensors: Dict[str, Sensor] = {}
        self.input_handlers: List[InputHandler] = []
        self.running = False
        self.mqtt_handler = None

    def add_actor(self, name: str, actor: Actor):
        print(f"[DEBUG] Actor {name} hinzugefügt")
        self.actors[name] = actor

    def add_sensor(self, name: str, sensor: Sensor):
        print(f"[DEBUG] Sensor {name} hinzugefügt")
        self.sensors[name] = sensor

    def add_input_handler(self, handler: InputHandler):
        print("[DEBUG] Input Handler wird hinzugefügt")
        handler.add_observer(self._handle_event)
        self.input_handlers.append(handler)
        handler.start()
        print("[DEBUG] Input Handler wurde gestartet")

    def start(self):
        """Startet den Controller"""
        print("[DEBUG] Starte Controller")
        self.running = True
        for handler in self.input_handlers:
            handler.start()

    def stop(self):
        """Stoppt den Controller"""
        print("[DEBUG] Stoppe Controller")
        self.running = False
        for handler in self.input_handlers:
            handler.stop()

    def set_mqtt_handler(self, mqtt_handler):
        """Setzt den MQTT Handler und registriert Callbacks"""
        self.mqtt_handler = mqtt_handler
        
        # Für jeden Actor einen Callback registrieren
        for actor_id in self.actors.keys():
            self.mqtt_handler.register_command_callback(actor_id, self._handle_mqtt_command)
            
            # Startup State setzen
            startup_state = mqtt_handler.get_startup_state(actor_id)
            print(f"[DEBUG] Setze Startup State für {actor_id}: {startup_state}")
            actor = self.actors[actor_id]
            actor.set(startup_state)
            # State an MQTT melden
            mqtt_handler.publish_state(actor_id, startup_state)

    def _handle_mqtt_command(self, actor_id: str, command: str):
        """Verarbeitet MQTT-Kommandos"""
        print(f"[DEBUG] MQTT Kommando empfangen: {actor_id} -> {command}")
        if actor_id in self.actors:
            actor = self.actors[actor_id]
            if command == "ON":
                actor.set(True)
            elif command == "OFF":
                actor.set(False)
            # State-Update über MQTT senden
            if self.mqtt_handler:
                self.mqtt_handler.publish_state(actor_id, actor.state)
        else:
            print(f"[WARNING] Unbekannter Actor: {actor_id}")

    def _handle_event(self, event: InputEvent):
        print(f"[DEBUG] Event empfangen: {event.source} -> {event.target}:{event.action}")
        
        # Spezialbehandlung für System-Events
        if event.target == 'system':
            if event.action == 'quit':
                print("[DEBUG] Quit-Command empfangen, beende Programm...")
                self.running = False
            return
        
        # Normale Actor-Events
        if event.target in self.actors:
            print(f"[DEBUG] Actor {event.target} gefunden")
            actor = self.actors[event.target]
            if event.action == 'toggle':
                actor.toggle()
                # State-Update über MQTT senden
                if self.mqtt_handler:
                    self.mqtt_handler.publish_state(event.target, actor.state)
            elif event.action == 'set':
                actor.set(event.value)
                # State-Update über MQTT senden
                if self.mqtt_handler:
                    self.mqtt_handler.publish_state(event.target, actor.state)
        else:
            print(f"[DEBUG] Actor {event.target} nicht gefunden!")