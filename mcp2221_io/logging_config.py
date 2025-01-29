import logging
import sys

def setup_logger(name='mcp2221_io', level=logging.DEBUG):
    """Richtet den Logger ein"""
    # Logger erstellen
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Handler für stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    
    # Handler hinzufügen wenn noch nicht vorhanden
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger

# Globaler Logger
logger = setup_logger()