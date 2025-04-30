"""
hardware_wrapper.py - Verbesserte Version mit detaillierter Diagnose
"""

import os
import sys
import time
import logging
import traceback

# Globale Status-Variable für Hardware-Verfügbarkeit
hardware_available = None  # None = nicht getestet, True/False = Ergebnis

# Logger einrichten
logger = logging.getLogger("MCP2221")

# Simulation Flag - kann durch Umgebungsvariable gesteuert werden
SIMULATION_MODE = os.environ.get('MCP2221_SIMULATION', '0') == '1'
FORCE_HARDWARE = os.environ.get('MCP2221_FORCE_HARDWARE', '0') == '1'

# Debug-Flag
DEBUG_HARDWARE = os.environ.get('MCP2221_DEBUG', '0') == '1'

# Klassen für Simulation
class MockDigitalIO:
    """Simulierte Version von digitalio"""
    
    class Direction:
        INPUT = "INPUT"
        OUTPUT = "OUTPUT"
    
    class Pull:
        UP = "UP"
        DOWN = "DOWN"
    
    class DigitalInOut:
        def __init__(self, pin):
            self.pin = pin
            self.direction = None
            self._simulation_state = False
            logger.debug(f"Simulierte DigitalInOut erstellt für Pin {pin}")
        
        @property
        def value(self):
            # Simuliere zufällige Änderungen für Sensor-Pins
            import random
            if self.direction == MockDigitalIO.Direction.INPUT and random.random() < 0.05:
                self._simulation_state = not self._simulation_state
            return self._simulation_state
        
        @value.setter
        def value(self, val):
            self._simulation_state = bool(val)
            if DEBUG_HARDWARE:
                print(f"SIMULATION: Setze Pin {self.pin} auf {'HIGH' if val else 'LOW'}")
        
        def deinit(self):
            logger.debug(f"Simulierte DigitalInOut für Pin {self.pin} deinitialisiert")

class MockBoard:
    """Simulierte Version von board"""
    G0 = "G0"
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"

# Importversuche für echte oder simulierte Hardware
digitalio = None
board = None

def check_hardware_connectivity():
    """
    Überprüft, ob die MCP2221 Hardware angeschlossen und verfügbar ist.
    
    Returns:
        bool: True wenn Hardware verfügbar ist, False wenn nicht
    """
    # USB-Gerät direkt überprüfen
    try:
        # Liste der USB-Geräte abrufen (erfordert PyUSB)
        import usb.core
        import usb.util
        
        # MCP2221 Vendor ID und Product ID
        MCP2221_VID = 0x04D8  # Microchip Vendor ID
        MCP2221_PID = 0x00DD  # MCP2221 Product ID
        
        # Suche nach dem Gerät
        device = usb.core.find(idVendor=MCP2221_VID, idProduct=MCP2221_PID)
        
        if device is not None:
            print(f"MCP2221 Gerät gefunden: {device}")
            return True
        else:
            print("MCP2221 Gerät nicht gefunden")
            return False
    except ImportError:
        print("PyUSB nicht installiert, kann Hardware nicht direkt überprüfen")
        return False
    except Exception as e:
        print(f"Fehler bei der Hardware-Überprüfung: {e}")
        return False

def init_hardware(force_simulation=False, force_hardware=False):
    """
    Initialisiert die Hardware-Module sicher.
    
    Args:
        force_simulation: Wenn True, wird immer der Simulation-Modus verwendet
        force_hardware: Wenn True, wird versucht, die echte Hardware zu verwenden
        
    Returns:
        bool: True wenn Hardware verfügbar ist, False bei Simulation
    """
    global digitalio, board, hardware_available, SIMULATION_MODE, FORCE_HARDWARE
    
    # Priorität der Parameter
    if force_simulation:
        SIMULATION_MODE = True
    if force_hardware:
        FORCE_HARDWARE = True
    
    # Wenn bereits initialisiert, nicht erneut versuchen
    if hardware_available is not None:
        return hardware_available
    
    # Debug-Ausgabe des aktuellen Zustands
    print(f"Hardware-Initialisierung:")
    print(f"  Simulation erzwungen: {SIMULATION_MODE}")
    print(f"  Hardware erzwungen: {FORCE_HARDWARE}")
    
    # Wenn Simulation erzwungen wird und Hardware nicht erzwungen wird
    if SIMULATION_MODE and not FORCE_HARDWARE:
        logger.info("Simulation-Modus ist aktiviert - verwende Mock-Hardware")
        digitalio = MockDigitalIO()
        board = MockBoard()
        hardware_available = False
        return False
    
    # Überprüfe Hardware-Konnektivität
    if not FORCE_HARDWARE and not check_hardware_connectivity():
        logger.warning("MCP2221 Hardware nicht gefunden - verwende Simulation")
        digitalio = MockDigitalIO()
        board = MockBoard()
        hardware_available = False
        return False
    
    # Versuche, echte Hardware zu importieren
    try:
        logger.info("Versuche Hardware-Module zu importieren...")
        
        # Liste der Pfade ausgeben
        print("Python-Pfade:")
        for path in sys.path:
            print(f"  {path}")
        
        # Liste der installierten Pakete ausgeben
        try:
            import pkg_resources
            print("\nInstallierte Pakete, die für Hardware relevant sein könnten:")
            for pkg in pkg_resources.working_set:
                if any(name in pkg.key for name in ["mcp", "adafruit", "circuit", "board", "digital", "usb"]):
                    print(f"  {pkg.key} {pkg.version}")
        except ImportError:
            print("pkg_resources nicht verfügbar")
        
        # Abfrage nach Hardware-Geräten (wenn pyusb installiert ist)
        try:
            import usb.core
            devices = list(usb.core.find(find_all=True))
            print("\nGefundene USB-Geräte:")
            for dev in devices:
                print(f"  VID: 0x{dev.idVendor:04x}, PID: 0x{dev.idProduct:04x}, Hersteller: {dev.manufacturer if hasattr(dev, 'manufacturer') else 'Unbekannt'}")
        except ImportError:
            print("PyUSB nicht installiert, kann keine USB-Geräte auflisten")
        except Exception as e:
            print(f"Fehler beim Auflisten der USB-Geräte: {e}")
        
        # Wichtig: Timeout für Hardware-Initialisierungsversuche
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Timeout bei Hardware-Initialisierung")
        
        # Setze Timeout von 5 Sekunden für den Import
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)
        
        try:
            # Versuche Import mit Timeout
            print("Importiere digitalio und board...")
            import digitalio as real_digitalio
            import board as real_board
            
            # Wenn wir hierher kommen, war der Import erfolgreich
            digitalio = real_digitalio
            board = real_board
            hardware_available = True
            logger.info("Hardware-Module erfolgreich importiert")
            print("Hardware-Module erfolgreich importiert!")
            
        except TimeoutError as e:
            print(f"Timeout beim Importieren der Hardware-Module: {e}")
            logger.error(f"Timeout beim Importieren der Hardware-Module: {e}")
            if FORCE_HARDWARE:
                print("Hardware-Modus erzwungen, aber Import fehlgeschlagen - Abbruch")
                sys.exit(1)
            
            logger.info("Fallback auf Simulation-Modus")
            digitalio = MockDigitalIO()
            board = MockBoard()
            hardware_available = False
            
        except ImportError as e:
            print(f"Hardware-Module konnten nicht importiert werden: {e}")
            logger.error(f"Hardware-Module konnten nicht importiert werden: {e}")
            if FORCE_HARDWARE:
                print("Hardware-Modus erzwungen, aber Import fehlgeschlagen - Abbruch")
                sys.exit(1)
                
            logger.info("Fallback auf Simulation-Modus")
            digitalio = MockDigitalIO()
            board = MockBoard()
            hardware_available = False
            
        finally:
            # Timeout zurücksetzen
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
        
        # Wenn Hardware verfügbar ist, versuchen wir einen einfachen Test
        if hardware_available:
            try:
                print("Führe einfachen Hardware-Test durch...")
                # Versuche, einen Pin zu erstellen (ohne ihn tatsächlich zu konfigurieren)
                pin_attr = getattr(board, "G0", None)
                if pin_attr is None:
                    print("Pin G0 nicht gefunden auf dem Board")
                    if FORCE_HARDWARE:
                        print("Hardware-Modus erzwungen, aber Hardware-Test fehlgeschlagen - Abbruch")
                        sys.exit(1)
                    hardware_available = False
                    digitalio = MockDigitalIO()
                    board = MockBoard()
                else:
                    print(f"Pin G0 gefunden: {pin_attr}")
            except Exception as e:
                print(f"Hardware-Test fehlgeschlagen: {e}")
                traceback.print_exc()
                if FORCE_HARDWARE:
                    print("Hardware-Modus erzwungen, aber Hardware-Test fehlgeschlagen - Abbruch")
                    sys.exit(1)
                hardware_available = False
                digitalio = MockDigitalIO()
                board = MockBoard()
                
        return hardware_available
        
    except Exception as e:
        print(f"Unerwarteter Fehler bei Hardware-Initialisierung: {e}")
        traceback.print_exc()
        logger.error(f"Unerwarteter Fehler bei Hardware-Initialisierung: {e}")
        if FORCE_HARDWARE:
            print("Hardware-Modus erzwungen, aber Initialisierung fehlgeschlagen - Abbruch")
            sys.exit(1)
            
        digitalio = MockDigitalIO()
        board = MockBoard()
        hardware_available = False
        return False

def get_digitalio():
    """Gibt das digitalio-Modul zurück (echt oder simuliert)"""
    global digitalio
    if digitalio is None:
        init_hardware()
    return digitalio

def get_board():
    """Gibt das board-Modul zurück (echt oder simuliert)"""
    global board
    if board is None:
        init_hardware()
    return board

# Testen der Wrapper
if __name__ == "__main__":
    print("Hardware-Wrapper Diagnose-Tool")
    
    # Logging konfigurieren
    logging.basicConfig(level=logging.DEBUG)
    
    print("\n=== Umgebungsvariablen ===")
    print(f"MCP2221_SIMULATION: {os.environ.get('MCP2221_SIMULATION', 'nicht gesetzt')}")
    print(f"MCP2221_FORCE_HARDWARE: {os.environ.get('MCP2221_FORCE_HARDWARE', 'nicht gesetzt')}")
    print(f"MCP2221_DEBUG: {os.environ.get('MCP2221_DEBUG', 'nicht gesetzt')}")
    
    print("\n=== Hardware-Erkennung ===")
    hardware_connected = check_hardware_connectivity()
    print(f"Hardware angeschlossen: {hardware_connected}")
    
    print("\n=== Hardware-Initialisierung ===")
    # Hardware initialisieren
    available = init_hardware()
    print(f"Hardware verfügbar: {available}")
    
    print("\n=== Pin-Test ===")
    # Teste Pins
    try:
        dio = get_digitalio()
        b = get_board()
        
        test_pin = "G0"
        print(f"Teste Pin {test_pin}...")
        
        pin = dio.DigitalInOut(getattr(b, test_pin))
        pin.direction = dio.Direction.OUTPUT
        print(f"Pin {test_pin} erstellt, Richtung: {pin.direction}")
        
        print("Setze Pin auf HIGH")
        pin.value = True
        print(f"Pin-Wert: {pin.value}")
        time.sleep(1)
        
        print("Setze Pin auf LOW")
        pin.value = False
        print(f"Pin-Wert: {pin.value}")
        time.sleep(1)
        
        pin.deinit()
        print(f"Pin {test_pin} deinitialisiert")
        
    except Exception as e:
        print(f"Fehler bei Pin-Test: {e}")
        traceback.print_exc()
    
    print("\n=== Diagnose abgeschlossen ===")
    print("Um den Hardware-Modus zu erzwingen:")
    print("  export MCP2221_FORCE_HARDWARE=1")
    print("  python3 -m mcp2221_io.hardware_wrapper")
    print("\nUm den Simulation-Modus zu erzwingen:")
    print("  export MCP2221_SIMULATION=1")
    print("  python3 -m mcp2221_io.hardware_wrapper")