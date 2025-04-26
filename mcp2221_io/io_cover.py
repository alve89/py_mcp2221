# io_cover.py
# Version: 3.1.0

import time
import threading
from enum import Enum
from typing import Optional, Callable, Dict, Any

from .io_actor import Actor
from .logging_config import logger, LogCategory
from .debug_mixin import DebugMixin

class CoverState(str, Enum):
    """Zustände eines Cover-Elements (wie Garagentor, Jalousie, etc.)"""
    OPEN = "open"
    CLOSED = "closed"
    OPENING = "opening"
    CLOSING = "closing"
    UNKNOWN = "unknown"
    ERROR = "error"

class Cover(DebugMixin):
    """
    Repräsentiert ein Cover (Garagentor, Rollladen, etc.), das über einen Aktor gesteuert wird
    und seinen Status mittels Sensoren ermittelt.
    
    Behandelt Sensor-Instabilitäten und Timing-Probleme robust durch:
    - Verifizierung von Sensor-Änderungen
    - Stabilisierungs-Verzögerung
    - Konsistenzprüfung der Sensorwerte
    """
    
    def __init__(
        self,
        actor: Actor,
        sensor_open_id: Optional[str] = None,
        sensor_closed_id: Optional[str] = None,
        inverted: bool = False,
        debug_config: Dict = {}
    ):
        """
        Initialisiert ein Cover-Element.
        
        :param actor: Der Aktor, der zum Steuern verwendet wird
        :param sensor_open_id: ID des Sensors für den geöffneten Zustand
        :param sensor_closed_id: ID des Sensors für den geschlossenen Zustand
        :param inverted: Ob der Aktor-Zustand invertiert werden soll
        :param debug_config: Debug-Konfiguration
        """
        self._init_debug_config(debug_config)
        
        # Komponenten
        self._actor = actor
        self.sensor_open_id = sensor_open_id
        self.sensor_closed_id = sensor_closed_id
        self._inverted = inverted
        
        # Zustandsmanagement
        self._state = CoverState.UNKNOWN
        self._sensor_open_state = False
        self._sensor_closed_state = False
        self._last_action_time = time.monotonic()
        self._movement_timeout = 60.0  # Timeout in Sekunden für Bewegung
        
        # Bewegungsmonitoring
        self._movement_monitor_thread = None
        self._movement_monitor_running = False
        
        # Callbacks
        self._state_changed_callback = None
        
        # Sensordaten-Stabilisierung
        self._verification_count = 0         # Zählt übereinstimmende Lesungen
        self._min_verification_count = 2     # Mindestanzahl gleicher Lesungen für stabile Änderung
        self._last_verified_reading = None   # Letzte verifizierte Sensorlesung (open, closed)
        self._unstable_readings_count = 0    # Zählt instabile Lesungen
        self._stabilization_delay = 0.5      # Verzögerung nach Sensor-Initialisierung (Sekunden)
        self._initialization_time = time.monotonic()
        self._initialized = False
        
        # Debug
        self.debug_cover_state("init", "Cover initialisiert")
    
    @property
    def state(self) -> str:
        """Gibt den aktuellen Zustand des Covers zurück"""
        return self._state
        
    @property
    def sensor_open_state(self) -> bool:
        """Gibt den Zustand des Sensors für den geöffneten Zustand zurück"""
        return self._sensor_open_state
        
    @property
    def sensor_closed_state(self) -> bool:
        """Gibt den Zustand des Sensors für den geschlossenen Zustand zurück"""
        return self._sensor_closed_state
    
    def set_state_changed_callback(self, callback: Callable[[str], None]):
        """
        Setzt den Callback für Zustandsänderungen.
        Der Callback wird mit dem neuen Zustand aufgerufen.
        
        :param callback: Callback-Funktion mit einem Parameter für den neuen Zustand
        """
        self._state_changed_callback = callback
        self.debug_cover_state("callback", "State-Changed-Callback registriert")
    
    def update_sensor_states(self, open_state: bool, closed_state: bool):
        """
        Aktualisiert die Sensorzustände und leitet daraus den Cover-Zustand ab.
        
        Zustandslogik:
        1. Wenn closed=true und open=false, dann ist das Tor geschlossen
        2. Wenn closed=false und open=true, dann ist das Tor geöffnet
        3. Wenn closed=true und open=true, dann ist das ein Fehler
        4. Wenn closed=false und open=false, dann ist das Tor in Bewegung:
           - Vorher open=true => Tor schließt sich
           - Vorher closed=true => Tor öffnet sich
        
        :param open_state: Zustand des Öffnungssensors
        :param closed_state: Zustand des Schließsensors
        """
        # Stabilisierungsverzögerung einhalten, wenn wir uns in der Initialisierungsphase befinden
        current_time = time.monotonic()
        if not self._initialized:
            # Während der Initialisierung nur Sensorwerte zwischenspeichern
            if current_time - self._initialization_time < self._stabilization_delay:
                self.debug_cover_state("init_delay", 
                    f"Verzögere Verarbeitung während Initialisierung ({current_time - self._initialization_time:.2f}s < {self._stabilization_delay}s)")
                return
            else:
                self._initialized = True
                self.debug_cover_state("init_complete", "Initialisierungsverzögerung abgeschlossen")
        
        # Alte Werte merken
        old_state = self._state
        old_open = self._sensor_open_state
        old_closed = self._sensor_closed_state
        
        # Aktuelle Sensorlesung
        current_reading = (open_state, closed_state)
        
        # Prüfen, ob sich die Werte zur letzten Lesung unterscheiden
        reading_changed = current_reading != self._last_verified_reading
        
        # Detaillierte Log-Ausgabe für Sensoränderungen
        if old_open != open_state or old_closed != closed_state:
            logger.info(f"Cover Sensorwerte empfangen: open={open_state}, closed={closed_state} "
                       f"(vorher: open={old_open}, closed={old_closed})", LogCategory.COVER)
        
        # Verifizierungslogik für stabile Lesungen
        if reading_changed:
            # Neue Lesung unterscheidet sich von der letzten verifizierten Lesung
            # Überprüfe, ob diese Lesung bereits zuvor gesehen wurde
            if hasattr(self, '_last_unverified_reading') and current_reading == self._last_unverified_reading:
                # Gleiche Lesung wie beim letzten Mal, erhöhe Verifizierungszähler
                self._verification_count += 1
                self.debug_cover_state("verify", 
                    f"Wiederholte Lesung {self._verification_count}/{self._min_verification_count}: open={open_state}, closed={closed_state}")
                
                # Prüfen, ob die Mindestanzahl an Verifizierungen erreicht ist
                if self._verification_count >= self._min_verification_count:
                    # Wert ist stabil genug, akzeptiere ihn
                    self._last_verified_reading = current_reading
                    self._verification_count = 0
                    self._unstable_readings_count = 0
                    self.debug_cover_state("verify_success", 
                        f"Verifizierte Sensorwerte: open={open_state}, closed={closed_state}")
                else:
                    # Noch nicht genügend Verifizierungen, nicht aktualisieren
                    self._last_unverified_reading = current_reading
                    return
            else:
                # Erste Lesung eines neuen Werts, setze Verifizierungszähler zurück
                self._verification_count = 1
                self._last_unverified_reading = current_reading
                self._unstable_readings_count += 1
                
                self.debug_cover_state("verify", 
                    f"Neue Lesung erkannt: open={open_state}, closed={closed_state}, benötige {self._min_verification_count} Bestätigungen")
                
                # Wenn zu viele instabile Lesungen nacheinander kommen, erhöhe die Verifizierungsschwelle temporär
                if self._unstable_readings_count > 5:
                    old_threshold = self._min_verification_count
                    self._min_verification_count = max(old_threshold, 3)  # Mindestens 3 Verifizierungen
                    self.debug_cover_state("verify_adjust", 
                        f"Viele instabile Lesungen erkannt, erhöhe Verifikationsschwelle von {old_threshold} auf {self._min_verification_count}")
                
                # Noch nicht verifiziert, nicht aktualisieren
                return
        
        # Wenn wir hierher kommen, haben wir verifizierte Sensorwerte
        
        # Sensorzustände aktualisieren
        self._sensor_open_state = open_state
        self._sensor_closed_state = closed_state
        
        # Zustandslogik anwenden
        new_state = self._determine_state(open_state, closed_state, old_state)
        
        # Wenn der Zustand sich geändert hat
        if new_state != old_state:
            self._state = new_state
            self.debug_cover_state("state_change", f"Zustand von {old_state} zu {new_state} geändert")
            logger.info(f"Cover Zustand geändert: {old_state} -> {new_state}", LogCategory.COVER)
            
            # Bewegungs-Monitoring starten/stoppen
            self._manage_movement_monitoring(new_state)
            
            # Callback aufrufen, wenn vorhanden
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(new_state)
                    self.debug_cover_state("callback", f"State-Changed-Callback aufgerufen mit {new_state}")
                except Exception as e:
                    self.debug_cover_error("callback_error", f"Fehler im State-Changed-Callback: {e}", e)
    
    def _determine_state(self, open_state: bool, closed_state: bool, old_state: str) -> str:
        """
        Ermittelt den Cover-Zustand basierend auf den Sensorzuständen und dem vorherigen Zustand.
        
        :param open_state: Zustand des Öffnungssensors
        :param closed_state: Zustand des Schließsensors
        :param old_state: Vorheriger Cover-Zustand
        :return: Neuer Cover-Zustand
        """
        # Fall 1: Tor geschlossen (closed=true, open=false)
        if closed_state and not open_state:
            logger.info(f"Cover Status-Logik: closed={closed_state}, open={open_state} → CLOSED", LogCategory.COVER)
            return CoverState.CLOSED
            
        # Fall 2: Tor geöffnet (closed=false, open=true)
        elif not closed_state and open_state:
            logger.info(f"Cover Status-Logik: closed={closed_state}, open={open_state} → OPEN", LogCategory.COVER)
            return CoverState.OPEN
            
        # Fall 3: Fehlerzustand (beide Sensoren aktiv)
        elif closed_state and open_state:
            logger.error(f"Cover in Fehlerzustand: beide Sensoren sind aktiv!", LogCategory.COVER)
            return CoverState.ERROR
            
        # Fall 4: Tor in Bewegung (beide Sensoren inaktiv)
        else:
            # Wenn beide Sensoren inaktiv sind, leiten wir die Bewegungsrichtung 
            # aus dem vorherigen Zustand ab
            if old_state == CoverState.OPEN or old_state == CoverState.OPENING:
                logger.info(f"Cover Status-Logik: closed={closed_state}, open={open_state}, " 
                          f"vorheriger Zustand={old_state} → CLOSING", LogCategory.COVER)
                return CoverState.CLOSING
            elif old_state == CoverState.CLOSED or old_state == CoverState.CLOSING:
                logger.info(f"Cover Status-Logik: closed={closed_state}, open={open_state}, " 
                          f"vorheriger Zustand={old_state} → OPENING", LogCategory.COVER)
                return CoverState.OPENING
            else:
                # Wenn der vorherige Zustand unbekannt oder Fehler war,
                # bleiben wir bei UNKNOWN
                logger.info(f"Cover Status-Logik: closed={closed_state}, open={open_state}, " 
                          f"vorheriger Zustand={old_state} → UNKNOWN", LogCategory.COVER)
                return CoverState.UNKNOWN
    
    def _manage_movement_monitoring(self, new_state: str):
        """
        Startet oder stoppt das Bewegungs-Monitoring basierend auf dem neuen Zustand.
        
        :param new_state: Neuer Cover-Zustand
        """
        # Monitoring starten, wenn der neue Zustand eine Bewegung ist
        if new_state in [CoverState.OPENING, CoverState.CLOSING]:
            self._last_action_time = time.monotonic()
            
            # Wenn noch kein Monitoring läuft, starten
            if not self._movement_monitor_running:
                self._start_movement_monitoring()
        
        # Monitoring stoppen, wenn der neue Zustand keine Bewegung ist
        elif self._movement_monitor_running:
            self._movement_monitor_running = False
            
            if self._movement_monitor_thread and self._movement_monitor_thread.is_alive():
                # Thread wird sich selbst beenden, wenn _movement_monitor_running auf False gesetzt ist
                pass
    
    def _start_movement_monitoring(self):
        """Startet das Bewegungs-Monitoring in einem separaten Thread"""
        self._movement_monitor_running = True
        
        def monitor_movement():
            self.debug_cover_state("monitor", "Bewegungs-Monitoring gestartet")
            
            while self._movement_monitor_running:
                # Prüfen, ob Timeout überschritten wurde
                current_time = time.monotonic()
                if (current_time - self._last_action_time) > self._movement_timeout:
                    logger.warning(f"Cover Bewegungs-Timeout überschritten! "
                                  f"State={self._state}, Zeit={self._movement_timeout}s", 
                                  LogCategory.COVER)
                    
                    # Zurück zum UNKNOWN-Zustand, wenn Timeout erreicht
                    if self._state in [CoverState.OPENING, CoverState.CLOSING]:
                        old_state = self._state
                        self._state = CoverState.UNKNOWN
                        
                        # Callback aufrufen, wenn vorhanden
                        if self._state_changed_callback:
                            try:
                                self._state_changed_callback(self._state)
                                self.debug_cover_state("callback", 
                                                       f"Timeout Callback: {old_state} -> {self._state}")
                            except Exception as e:
                                self.debug_cover_error("callback_error", 
                                                      f"Fehler im Timeout-Callback: {e}", e)
                    
                    # Monitoring beenden
                    self._movement_monitor_running = False
                    break
                
                # Kurze Pause
                time.sleep(1.0)
            
            self.debug_cover_state("monitor", "Bewegungs-Monitoring beendet")
        
        # Thread starten
        self._movement_monitor_thread = threading.Thread(target=monitor_movement, daemon=True)
        self._movement_monitor_thread.start()
    
    def force_update(self) -> str:
        """
        Erzwingt eine sofortige Aktualisierung des Cover-Zustands basierend auf den aktuellen Sensorwerten.
        Diese Methode setzt die Verifizierung zurück und akzeptiert die aktuellen Sensorwerte direkt.
        
        :return: Der aktuelle Cover-Zustand nach dem Update
        """
        self.debug_cover_state("force_update", "Erzwinge Cover-Update")
        
        # Sensorzustände wurden vor dem Aufruf dieser Methode bereits aktualisiert
        # Jetzt direkt den Zustand neu berechnen
        
        # Verifizierungszustand zurücksetzen und aktuelle Werte als verifiziert markieren
        self._verification_count = 0
        self._unstable_readings_count = 0
        self._last_verified_reading = (self._sensor_open_state, self._sensor_closed_state)
        self._initialized = True
        
        # Zustand neu berechnen
        old_state = self._state
        new_state = self._determine_state(self._sensor_open_state, self._sensor_closed_state, old_state)
        
        # Wenn sich der Zustand geändert hat
        if new_state != old_state:
            self._state = new_state
            self.debug_cover_state("state_change", f"Force-Update: Zustand von {old_state} zu {new_state} geändert")
            logger.info(f"Cover Force-Update: Zustand von {old_state} auf {new_state} geändert", LogCategory.COVER)
            
            # Bewegungs-Monitoring starten/stoppen
            self._manage_movement_monitoring(new_state)
            
            # Callback aufrufen, wenn vorhanden
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(new_state)
                    self.debug_cover_state("callback", f"State-Changed-Callback aufgerufen mit {new_state}")
                except Exception as e:
                    self.debug_cover_error("callback_error", f"Fehler im State-Changed-Callback: {e}", e)
        
        return self._state

    def open(self):
        """Öffnet das Cover durch Aktivierung des Aktors"""
        self.debug_cover_state("action", "Öffne Cover")
        logger.info(f"Befehl: Cover öffnen", LogCategory.COVER)
        
        # Aktor aktivieren
        self._actor.set(True)
        
        # Für Cover in geschlossenem Zustand den Zustand direkt auf OPENING setzen
        if self._state == CoverState.CLOSED:
            # Bei einem direkten Befehl setzen wir die Verifizierung zurück
            self._verification_count = 0
            self._unstable_readings_count = 0
            self._last_verified_reading = (self._sensor_open_state, False)
            
            old_state = self._state
            self._state = CoverState.OPENING
            
            self.debug_cover_state("action_state_change", f"Direkte Zustandsänderung: {old_state} -> {self._state}")
            logger.info(f"Cover direkter Befehl: Zustand von {old_state} auf {self._state} geändert", LogCategory.COVER)
            
            # Bewegungs-Monitoring starten
            self._manage_movement_monitoring(self._state)
            
            # Callback aufrufen, wenn vorhanden
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(self._state)
                except Exception as e:
                    self.debug_cover_error("callback_error", f"Fehler im State-Changed-Callback: {e}", e)
    
    def close(self):
        """Schließt das Cover durch Aktivierung des Aktors"""
        self.debug_cover_state("action", "Schließe Cover")
        logger.info(f"Befehl: Cover schließen", LogCategory.COVER)
        
        # Aktor aktivieren
        self._actor.set(True)
        
        # Für Cover in geöffnetem Zustand den Zustand direkt auf CLOSING setzen
        if self._state == CoverState.OPEN:
            # Bei einem direkten Befehl setzen wir die Verifizierung zurück
            self._verification_count = 0
            self._unstable_readings_count = 0
            self._last_verified_reading = (False, self._sensor_closed_state)
            
            old_state = self._state
            self._state = CoverState.CLOSING
            
            self.debug_cover_state("action_state_change", f"Direkte Zustandsänderung: {old_state} -> {self._state}")
            logger.info(f"Cover direkter Befehl: Zustand von {old_state} auf {self._state} geändert", LogCategory.COVER)
            
            # Bewegungs-Monitoring starten
            self._manage_movement_monitoring(self._state)
            
            # Callback aufrufen, wenn vorhanden
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(self._state)
                except Exception as e:
                    self.debug_cover_error("callback_error", f"Fehler im State-Changed-Callback: {e}", e)
    
    def stop(self):
        """Stoppt das Cover durch Aktivierung des Aktors"""
        self.debug_cover_state("action", "Stoppe Cover")
        logger.info(f"Befehl: Cover stoppen", LogCategory.COVER)
        
        # Aktor aktivieren
        self._actor.set(True)
        
        # Wenn das Cover aktuell in Bewegung ist, setzen wir es zurück auf UNKNOWN
        if self._state in [CoverState.OPENING, CoverState.CLOSING]:
            old_state = self._state
            self._state = CoverState.UNKNOWN
            
            self.debug_cover_state("action_state_change", f"Direkte Zustandsänderung: {old_state} -> {self._state}")
            logger.info(f"Cover Stopp-Befehl: Zustand von {old_state} auf {self._state} geändert", LogCategory.COVER)
            
            # Bewegungs-Monitoring stoppen
            self._manage_movement_monitoring(self._state)
            
            # Callback aufrufen, wenn vorhanden
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(self._state)
                except Exception as e:
                    self.debug_cover_error("callback_error", f"Fehler im State-Changed-Callback: {e}", e)
    
    def toggle(self):
        """
        Schaltet das Cover um: Öffnen, wenn geschlossen, schließen, wenn geöffnet.
        Bei Garagentoren wird meist nur ein Impuls gesendet, unabhängig vom aktuellen Zustand.
        """
        self.debug_cover_state("action", "Toggle Cover")
        logger.info(f"Befehl: Cover toggle", LogCategory.COVER)
        
        # Einen Impuls an den Aktor senden, unabhängig vom aktuellen Zustand
        self._actor.set(True)
        
        # Zustand basierend auf dem aktuellen Status ändern (Vorhersage der nächsten Bewegung)
        old_state = self._state
        
        if self._state == CoverState.CLOSED:
            # Wenn geschlossen, sollte es sich öffnen
            self._state = CoverState.OPENING
            
            # Bei einem direkten Befehl setzen wir die Verifizierung zurück
            self._verification_count = 0
            self._unstable_readings_count = 0
            self._last_verified_reading = (self._sensor_open_state, False)
            
        elif self._state == CoverState.OPEN:
            # Wenn geöffnet, sollte es sich schließen
            self._state = CoverState.CLOSING
            
            # Bei einem direkten Befehl setzen wir die Verifizierung zurück
            self._verification_count = 0
            self._unstable_readings_count = 0
            self._last_verified_reading = (False, self._sensor_closed_state)
            
        elif self._state in [CoverState.OPENING, CoverState.CLOSING]:
            # Wenn bereits in Bewegung, anhalten
            self._state = CoverState.UNKNOWN
            
        elif self._state in [CoverState.UNKNOWN, CoverState.ERROR]:
            # Bei unbekanntem Zustand versuchen wir zu öffnen
            self._state = CoverState.OPENING
            
        # Nur bei Zustandsänderungen
        if old_state != self._state:
            self.debug_cover_state("action_state_change", f"Toggle: {old_state} -> {self._state}")
            logger.info(f"Cover Toggle: Zustand von {old_state} auf {self._state} geändert", LogCategory.COVER)
            
            # Bewegungs-Monitoring anpassen
            self._manage_movement_monitoring(self._state)
            
            # Callback aufrufen, wenn vorhanden
            if self._state_changed_callback:
                try:
                    self._state_changed_callback(self._state)
                except Exception as e:
                    self.debug_cover_error("callback_error", f"Fehler im Toggle-Callback: {e}", e)
                    
    def set_sensor_verification_threshold(self, threshold: int):
        """
        Setzt die Anzahl der benötigten übereinstimmenden Lesungen für eine Verifizierung.
        
        :param threshold: Anzahl der benötigten übereinstimmenden Lesungen
        """
        if threshold < 1:
            threshold = 1
        
        old_threshold = self._min_verification_count
        self._min_verification_count = threshold
        
        self.debug_cover_state("config", f"Verifikationsschwelle von {old_threshold} auf {threshold} geändert")
        logger.info(f"Cover Verifikationsschwelle auf {threshold} gesetzt", LogCategory.COVER)
        
    def set_stabilization_delay(self, delay: float):
        """
        Setzt die Verzögerungszeit für die Initialisierung.
        
        :param delay: Verzögerungszeit in Sekunden
        """
        if delay < 0:
            delay = 0
            
        old_delay = self._stabilization_delay
        self._stabilization_delay = delay
        
        self.debug_cover_state("config", f"Stabilisierungsverzögerung von {old_delay}s auf {delay}s geändert")
        logger.info(f"Cover Stabilisierungsverzögerung auf {delay}s gesetzt", LogCategory.COVER)
        
    def reset_verification(self):
        """
        Setzt die Verifizierungszähler zurück und markiert den aktuellen Zustand als verifiziert.
        Nützlich nach manuellen Zustandsänderungen oder bei bekannten Sensorwertänderungen.
        """
        self._verification_count = 0
        self._unstable_readings_count = 0
        self._last_verified_reading = (self._sensor_open_state, self._sensor_closed_state)
        self._initialized = True
        
        self.debug_cover_state("reset", "Verifikation zurückgesetzt, aktueller Zustand als verifiziert markiert")
        logger.info(f"Cover Verifikation zurückgesetzt für Sensoren: open={self._sensor_open_state}, closed={self._sensor_closed_state}", 
                  LogCategory.COVER)