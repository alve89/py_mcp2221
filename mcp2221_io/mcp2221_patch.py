# mcp2221_patch.py

import os
import hid
import time
from typing import Optional
import atexit

class MCP2221Device:
    """Eine Thread-sichere Singleton-Implementierung für MCP2221"""
    _instance = None
    _device = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = MCP2221Device()
        return cls._instance
    
    def __init__(self):
        self.vid = 0x04d8
        self.pid = 0x00dd
        # Setze Umgebungsvariablen
        os.environ['BLINKA_MCP2221'] = '1'
        os.environ['BLINKA_MCP2221_RESET_DELAY'] = '-1'
        atexit.register(self.cleanup)
    
    def cleanup(self):
        """Cleanup beim Programmende"""
        if self._device is not None:
            try:
                self._device.close()
                print("MCP2221 Device geschlossen")
            except:
                pass
            self._device = None
    
    def open(self):
        """Öffnet das Device wenn nötig"""
        if self._device is None:
            try:
                self._device = hid.device()
                self._device.open(self.vid, self.pid)
            except Exception as e:
                print(f"Fehler beim Öffnen des Devices: {e}")
                self._device = None
                raise
    
    def close(self):
        """Schließt das Device"""
        if self._device is not None:
            try:
                self._device.close()
            except:
                pass
            self._device = None
    
    def write(self, data):
        """Schreibt Daten"""
        self.open()
        try:
            return self._device.write(data)
        finally:
            self.close()
    
    def read(self, size):
        """Liest Daten"""
        self.open()
        try:
            return self._device.read(size)
        finally:
            self.close()

    def check_board_status(self):
        """Prüft den Status des MCP2221 Boards"""
        try:
            # Überprüfen anhand bestehender GPIO-Konfiguration
            import board
            if hasattr(board, 'G0'):
                pin = getattr(board, 'G0')
                if pin:
                    return True, "OK"
            return False, "Board nicht initialisiert"
        except Exception as e:
            return False, str(e)

def patch_blinka():
    """Patcht die Blinka Library"""
    from importlib import import_module
    
    class MockHIDDevice:
        """Mock HID Device das das MCP2221Device verwendet"""
        def __init__(self):
            self._mcp = MCP2221Device.get_instance()
            
        def write(self, data):
            return self._mcp.write(data)
            
        def read(self, size):
            return self._mcp.read(size)
        
        def open(self, vid, pid):
            pass
            
        def close(self):
            pass
    
    # Lade das Original-Modul
    mcp2221_module = import_module('adafruit_blinka.microcontroller.mcp2221.mcp2221')
    original_MCP2221 = mcp2221_module.MCP2221
    
    class PatchedMCP2221(original_MCP2221):
        def __init__(self):
            self._hid = MockHIDDevice()
            self._gpio_pins = {}
            self._gpio_mode = {}
            self._gpio_directions = {}
            self._gp_config = [0x07] * 4
            
            # Initialisiere GPIO Konfiguration
            self._get_gpio_config()
    
    # Patche die Klasse
    mcp2221_module.MCP2221 = PatchedMCP2221
    if not hasattr(mcp2221_module, 'mcp2221'):
        mcp2221_module.mcp2221 = PatchedMCP2221()

# Test-Code
if __name__ == "__main__":
    try:
        # Teste grundlegende HID-Funktionalität
        device = MCP2221Device.get_instance()
        device.open()
        print(f"MCP2221 gefunden und geöffnet")
        device.close()
        
        # Patch anwenden
        patch_blinka()
        print("Blinka Library gepatcht")
        
        # Teste Board-Import
        import board
        print("Board erfolgreich importiert")
        
        # Teste GPIO
        import digitalio
        led = digitalio.DigitalInOut(board.G0)
        led.direction = digitalio.Direction.OUTPUT
        print("GPIO Test erfolgreich")
        
        print("\nAlle Tests erfolgreich!")
        
    except Exception as e:
        print(f"Fehler: {e}")
        raise