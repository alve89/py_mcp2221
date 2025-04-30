# mcp2221_io/const.py

import logging
from termcolor import colored

# Hardware-Typ-Konstanten
MCP2221 = 1
FT232H = 2

# Standard-Hardware-Wert (wird später gesetzt)
HW = -1

def validate_hardware_config(hw_config):
    """Validiert die Hardware-Konfiguration.
    
    Returns:
        bool: True, wenn genau eine Hardware auf 'true' gesetzt ist, sonst False
    """
    if not hw_config:
        return False
    
    # Zähle, wie viele Hardware-Optionen auf 'true' gesetzt sind
    enabled_hw = 0
    if hw_config.get("mcp2221", False):
        enabled_hw += 1
    if hw_config.get("ft232h", False):
        enabled_hw += 1
    
    # Genau eine Hardware muss aktiviert sein
    return enabled_hw == 1

def setup_hardware(hw_config, logger=None):
    """Setzt die zu verwendende Hardware basierend auf der Konfiguration.
    
    Args:
        hw_config: Der 'hardware' Teil der Konfiguration
        logger: Optional, ein Logger-Objekt
        
    Returns:
        str: Beschreibung der gewählten Hardware
    """
    global HW
    hw_str = "NoHardware"
    
    if not validate_hardware_config(hw_config):
        error_msg = "Die Konfiguration des Punkts 'hardware' ist fehlerhaft. " \
                    "Mögliche Fehler: KEIN Eintrag ODER MEHRERE Einträge sind 'true'."
        if logger:
            logger.critical(colored(error_msg, "red"))
        else:
            print(colored(error_msg, "red"))
        return hw_str
        
    if hw_config.get("mcp2221", False):
        HW = MCP2221
        hw_str = "MCP2221"
    elif hw_config.get("ft232h", False):
        HW = FT232H
        hw_str = "FT232H"
    
    if logger:
        logger.info(f"Hardware {hw_str} ausgewählt (HW={HW})")
    else:
        print(f"Hardware {hw_str} ausgewählt (HW={HW})")
    
    return hw_str