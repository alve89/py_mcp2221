# logging_config.py
# Version: 1.4.0

import logging
import sys
import os

class NoTimestampInfoFilter(logging.Filter):
    """Filter, der bei INFO-Nachrichten den Zeitstempel entfernt"""
    def filter(self, record):
        # Für INFO-Level Nachrichten entfernen wir die Formatierungsdetails
        if record.levelno == logging.INFO:
            # Setze diese Attribute, damit sie bei der Formatierung ignoriert werden
            record.asctime = ""
            record.name = ""
            record.levelname = ""
            # Spezielle Variable, die vom Formatter erkannt wird
            record.no_timestamp = True
        return True

class CustomFormatter(logging.Formatter):
    """Eigener Formatter, der bei INFO-Nachrichten nur die Nachricht ausgibt"""
    def format(self, record):
        if hasattr(record, 'no_timestamp') and record.no_timestamp:
            # Für INFO-Level: Nur die Nachricht
            return record.getMessage()
        # Für andere Level: Vollständiges Format
        return super().format(record)

def setup_logger(name='mcp2221_io', level=logging.DEBUG):
    """Richtet den Logger ein"""
    # Logger erstellen
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Alle vorhandenen Handler löschen (um doppelte Ausgaben zu vermeiden)
    for hdlr in logger.handlers[:]:
        logger.removeHandler(hdlr)
    
    # Handler für stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Überprüfen, ob wir im Debug-Modus sind (durch Umgebungsvariable steuerbar)
    debug_mode = os.environ.get('MCP2221_DEBUG', '0') == '1'
    
    if debug_mode:
        # Im Debug-Modus immer vollständige Informationen anzeigen
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    else:
        # Im normalen Modus den benutzerdefinierten Formatter verwenden
        formatter = CustomFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        # Filter hinzufügen, der die Attribute für INFO-Nachrichten modifiziert
        logger.addFilter(NoTimestampInfoFilter())
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Filter für MQTT-Nachrichten im Nicht-Debug-Modus
    if not debug_mode:
        class LogFilter(logging.Filter):
            def filter(self, record):
                # Filtere MQTT Debug-Nachrichten im Nicht-Debug-Modus
                if record.levelno <= logging.DEBUG and any(x in record.getMessage() for x in ["[MQTT]", "[Sensor ", "[Actor "]):
                    return False
                # Auch INFO-Nachrichten für Sensor-Tests filtern
                if record.levelno <= logging.INFO and "[Sensor Test]" in record.getMessage():
                    return False
                return True
        
        console_handler.addFilter(LogFilter())
    
    return logger

# Globaler Logger
logger = setup_logger()

def set_debug_mode(enabled=False):
    """Setzt den Debug-Modus für den Logger"""
    os.environ['MCP2221_DEBUG'] = '1' if enabled else '0'
    
    # Logger zurücksetzen
    global logger
    for handler in logger.handlers:
        logger.removeHandler(handler)
    
    logger = setup_logger(level=logger.level)
    
    return logger

# Patch für die vorhandenen Logs - Monkey-Patching des info-Methode
original_info = logger.info

def patched_info(msg, *args, **kwargs):
    # Wenn wir nicht im Debug-Modus sind, nur die Nachricht ohne Präfix ausgeben
    if os.environ.get('MCP2221_DEBUG', '0') != '1':
        # Für direkte Ausgabe an stdout, ohne Logger-Formatierung
        print(msg % args if args else msg)
    else:
        # Im Debug-Modus das normale Logging verwenden
        original_info(msg, *args, **kwargs)

# Logger-Methode ersetzen
logger.info = patched_info