import os
import yaml
import logging
from typing import Any



# Singleton-Instanzen
config = None
logger = None

def get_config():
    """Gibt die globale Config-Instanz zurück oder erstellt sie, wenn sie nicht existiert."""
    global config
    if config is None:
        # Korrigierter Konfigurationspfad
        current_dir = os.path.dirname(os.path.abspath(__file__))  # /usr/local/bin/mcp2221_io/
        config_path = os.path.join(current_dir, "..", "config.yaml")  # Ein Verzeichnis nach oben
        config = Config(config_path)
    return config

def get_logger():
    """Gibt die globale Logger-Instanz zurück oder erstellt sie, wenn sie nicht existiert."""
    global logger
    if logger is None:
        # Standard-Logging-Level aus Config
        debug_level = config.get_value("logging.level", "WARNING")
        logger = Logger(debug_level).get_logger()
    return logger

class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self) -> bool:
        """Lädt die Konfiguration aus der YAML-Datei."""
        try:
            with open(self.config_path, 'r') as file:
                self.config = yaml.safe_load(file)
            print(f"Konfiguration aus {self.config_path} erfolgreich geladen.")
            return True
        except Exception as e:
            print(f"Fehler beim Laden der Konfiguration: {e}")
            return False
    
    def get_value(self, path: str, default: Any = None) -> Any:
        """Greift auf einen verschachtelten Wert mit Punktnotation zu.
        Beispiel: get_nested_value("debugging.mqtt.process")
        """
        keys = path.split(".")
        current = self.config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def get_config(self):
        return self.config
    
    # Diese Methoden ermöglichen den direkten Zugriff wie auf ein Dictionary
    def __getitem__(self, key):
        """Ermöglicht den direkten Zugriff auf die Konfiguration mit config['key']"""
        return self.config[key]
    
    def __contains__(self, key):
        """Ermöglicht die Verwendung von 'key in config'"""
        return key in self.config
    
    def __iter__(self):
        """Ermöglicht die Iteration über die Konfiguration"""
        return iter(self.config)
    
    def keys(self):
        """Gibt die Schlüssel der Konfiguration zurück"""
        return self.config.keys()
    
    def items(self):
        """Gibt die Schlüssel-Wert-Paare der Konfiguration zurück"""
        return self.config.items()
config = get_config()

class Logger:
    def __init__(self, level: str = "WARNING"):
        # String zu logging-Level konvertieren
        log_level = getattr(logging, level)
            
        # Logger konfigurieren
        self.logger = logging.getLogger("MCP2221")
        self.logger.setLevel(log_level)
        
        # Vorhandene Handler entfernen, um Doppelausgaben zu vermeiden
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Handler erstellen
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # Formatierung hinzufügen
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        
        # Handler zum Logger hinzufügen
        self.logger.addHandler(console_handler)

        self.logger.info("Logging initialisiert und konfiguriert.")
        
    def get_logger(self):
        return self.logger
logger = get_logger()