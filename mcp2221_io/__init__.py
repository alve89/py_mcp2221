# mcp2221_io/__init__.py

# Zuerst werden nur die grundlegenden Module importiert, die keine hardware-abhängigen Importe enthalten
from mcp2221_io.new_core import get_logger, get_config
from mcp2221_io.const import MCP2221, FT232H, setup_hardware

# Hardware-Konfiguration laden und konstanten setzen
config = get_config()
logger = get_logger()
hw_str = setup_hardware(config.get_value("hardware", {}), logger)

# Nun können hardware-abhängige Module importiert werden
from mcp2221_io.new_io_device import IODevice
from mcp2221_io.new_io_actor import IOActor
from mcp2221_io.new_io_sensor import IOSensor
from mcp2221_io.new_io_controller import IOController
from mcp2221_io.new_mqtt import MQTTClient

# Export des aktuellen Hardware-Typs für externe Module
__hw_type__ = hw_str