# io_control.py
# Version: 1.5.1

from abc import ABC, abstractmethod
from typing import Dict, List, Callable
import threading
import time
import select
import sys
from .io_base import Actor, Sensor
from .logging_config import logger

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

class IOController:
    """Zentrale Steuerungsklasse für das IO-System"""
    def __init__(self):
        self.actors: Dict[str, Actor] = {}
        self.sensors: Dict[str, Sensor] = {}
        self.input_handlers: List[InputHandler] = []
        self.running = False
        self.mqtt_handler = None

    def add_actor(self, name: str, actor: Actor):
        logger.debug(f"Actor {name} hinzugefügt")
        self.actors[name] = actor

    def add_sensor(self, name: str, sensor: Sensor):
        logger.debug(f"Sensor {name} hinzugefügt")
        self.sensors[name] = sensor

    def add_input_handler(self, handler: InputHandler):
        logger.debug("Input Handler wird hinzugefügt")
        handler.add_observer(self._handle_event)
        self.input_handlers.append(handler)
        handler.start()
        logger.debug("Input Handler wurde gestartet")

    def start(self):
        """Startet den Controller"""
        logger.debug("Starte Controller")
        self.running = True
        for handler in self.input_handlers:
            handler.start()

    def stop(self):
        """Stoppt den Controller"""
        logger.debug("Stoppe Controller")
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
            
            mqtt_handler.register_command_callback(actor_id, self._handle_mqtt_command)
            
            # Reset-Callback registrieren wenn Reset-Delay konfiguriert
            if actor_config.get('auto_reset', False) and float(actor_config.get('reset_delay', 0)) > 0:
                def create_reset_handler(aid):
                    def on_reset():
                        logger.debug(f"Reset-Event für {aid}")
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
                logger.debug(f"Reset-Handler für {actor_id} registriert")
            
            # Startup State setzen
            startup_state = mqtt_handler.get_startup_state(actor_id)
            logger.debug(f"Setze Startup State für {actor_id}: {startup_state}")
            
            # State basierend auf Entity-Typ setzen
            if entity_type == 'lock':
                command = "LOCK" if startup_state else "UNLOCK"
                logger.debug(f"Lock {actor_id} Startup: State={startup_state}, Command={command}")
            elif entity_type == 'switch':
                command = "ON" if startup_state else "OFF"
            elif entity_type == 'button':
                logger.debug(f"Button {actor_id} initialisiert")
                continue
                
            self._execute_actor_command(actor_id, command)

    def _handle_mqtt_command(self, actor_id: str, command: str):
        """Verarbeitet MQTT-Kommandos"""
        logger.debug(f"MQTT Kommando empfangen: {actor_id} -> {command}")
        if actor_id in self.actors:
            self._execute_actor_command(actor_id, command)
        else:
            logger.warning(f"Unbekannter Actor: {actor_id}")

    def _execute_actor_command(self, actor_id: str, command: str):
        """Führt ein Kommando für einen Actor aus"""
        if actor_id not in self.actors:
            logger.warning(f"Unbekannter Actor: {actor_id}")
            return

        actor = self.actors[actor_id]
        actor_config = self.mqtt_handler.config['actors'].get(actor_id, {})
        entity_type = actor_config.get('entity_type', 'switch').lower()
        
        logger.debug(f"Führe Kommando {command} für {actor_id} (Typ: {entity_type}) aus")
        
        if entity_type == 'switch':
            # Physischen Zustand setzen
            new_state = (command == "ON")
            logger.debug(f"Switch {actor_id}: Kommando={command}, new_state={new_state}")
            actor.set(new_state)
            logger.debug(f"Physischer Zustand für {actor_id} auf {new_state} gesetzt")
            
            # MQTT updaten
            if self.mqtt_handler:
                # State Topic aktualisieren
                self.mqtt_handler.mqtt_client.publish(
                    f"{self.mqtt_handler.base_topic}/{actor_id}/state",
                    command,
                    qos=1,
                    retain=True
                )
                logger.debug(f"MQTT State für {actor_id} auf {command} gesetzt")
                
        elif entity_type == 'lock':
            # Analog zu switch: UNLOCK = ON (True)
            new_state = (command == "UNLOCK")
            logger.debug(f"Lock {actor_id}: Kommando={command}, new_state={new_state}")
            actor.set(new_state)
            logger.debug(f"Lock {actor_id}: State {new_state} gesetzt (UNLOCK={command=='UNLOCK'})")
            
            # MQTT updaten
            if self.mqtt_handler:
                # State Topic aktualisieren
                state = "UNLOCKED" if new_state else "LOCKED"
                self.mqtt_handler.mqtt_client.publish(
                    f"{self.mqtt_handler.base_topic}/{actor_id}/state",
                    state,
                    qos=1,
                    retain=True
                )
                logger.debug(f"MQTT State für {actor_id} auf {state} gesetzt")

    def _handle_event(self, event: InputEvent):
        """Verarbeitet Events von Input Handlern"""
        logger.debug(f"Event empfangen: {event.source} -> {event.target}:{event.action}")
        
        # Spezialbehandlung für System-Events
        if event.target == 'system':
            if event.action == 'quit':
                logger.debug("Quit-Command empfangen, beende Programm...")
                self.running = False
            return
        
        # Normale Actor-Events über MQTT-Set routen
        if event.target in self.actors:
            logger.debug(f"Actor {event.target} gefunden")
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
                logger.warning("MQTT Handler nicht verfügbar - Kommando kann nicht gesendet werden")