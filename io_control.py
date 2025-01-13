from abc import ABC, abstractmethod
from typing import Dict, List, Callable
import threading
import time
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
            self._thread.join()

    def _run(self):
        while self._running:
            self._handle_input()
            time.sleep(0.01)

class SimpleInputHandler(InputHandler):
    """Einfacher Input Handler basierend auf input()"""
    def __init__(self, key_mappings: Dict[str, tuple]):
        super().__init__()
        self.key_mappings = key_mappings

    def _handle_input(self):
        if not self._running:
            return
            
        try:
            key = input().strip()
            print(f"[DEBUG] Taste empfangen: {key}")  # Debug-Ausgabe
            if key in self.key_mappings:
                print(f"[DEBUG] Taste {key} ist in key_mappings")  # Debug-Ausgabe
                target, action, value = self.key_mappings[key]
                print(f"[DEBUG] Erzeuge Event: target={target}, action={action}, value={value}")  # Debug-Ausgabe
                event = InputEvent('input', action, target, value)
                self.notify_observers(event)
                print("[DEBUG] Event wurde an Observer gesendet")  # Debug-Ausgabe
                
                # Wenn es ein Quit-Command war, beenden wir den Handler
                if target == 'system' and action == 'quit':
                    self._running = False
            else:
                print(f"[DEBUG] Taste {key} nicht in key_mappings!")  # Debug-Ausgabe
        except EOFError:
            self._running = False
            print("[DEBUG] EOFError aufgetreten")  # Debug-Ausgabe

class IOController:
    """Zentrale Steuerungsklasse für das IO-System"""
    def __init__(self):
        self.actors: Dict[str, Actor] = {}
        self.sensors: Dict[str, Sensor] = {}
        self.input_handlers: List[InputHandler] = []
        self.running = False  # Flag für den Programmzustand

    def add_actor(self, name: str, actor: Actor):
        print(f"[DEBUG] Actor {name} hinzugefügt")  # Debug-Ausgabe
        self.actors[name] = actor

    def add_sensor(self, name: str, sensor: Sensor):
        print(f"[DEBUG] Sensor {name} hinzugefügt")  # Debug-Ausgabe
        self.sensors[name] = sensor

    def add_input_handler(self, handler: InputHandler):
        print("[DEBUG] Input Handler wird hinzugefügt")  # Debug-Ausgabe
        handler.add_observer(self._handle_event)
        self.input_handlers.append(handler)
        handler.start()
        print("[DEBUG] Input Handler wurde gestartet")  # Debug-Ausgabe

    def _handle_event(self, event: InputEvent):
        print(f"[DEBUG] Event empfangen: {event.source} -> {event.target}:{event.action}")  # Debug-Ausgabe
        
        # Spezialbehandlung für System-Events
        if event.target == 'system':
            if event.action == 'quit':
                print("[DEBUG] Quit-Command empfangen, beende Programm...")
                self.running = False
            return
        
        # Normale Actor-Events
        if event.target in self.actors:
            print(f"[DEBUG] Actor {event.target} gefunden")  # Debug-Ausgabe
            actor = self.actors[event.target]
            if event.action == 'toggle':
                print(f"[DEBUG] Führe toggle() für {event.target} aus")  # Debug-Ausgabe
                actor.toggle()
            elif event.action == 'set':
                print(f"[DEBUG] Führe set({event.value}) für {event.target} aus")  # Debug-Ausgabe
                actor.set(event.value)
        else:
            print(f"[DEBUG] Actor {event.target} nicht gefunden!")  # Debug-Ausgabe

    def start(self):
        """Startet alle Input Handler"""
        print("[DEBUG] Starte alle Input Handler")  # Debug-Ausgabe
        for handler in self.input_handlers:
            handler.start()
        print("[DEBUG] Alle Input Handler gestartet")  # Debug-Ausgabe

    def stop(self):
        """Stoppt alle Input Handler"""
        print("[DEBUG] Stoppe alle Input Handler")  # Debug-Ausgabe
        for handler in self.input_handlers:
            handler.stop()
        print("[DEBUG] Alle Input Handler gestoppt")  # Debug-Ausgabe