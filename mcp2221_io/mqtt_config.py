# mqtt_config.py
# Version: 1.3.0

class EntityTypeConfig:
    """Konfigurationsklasse für Entity Types"""
    TYPES = {
        'switch': {
            'discovery_type': 'switch',
            'states': {
                True: 'ON',
                False: 'OFF'
            },
            'commands': {
                'ON': True,
                'OFF': False
            },
            'discovery_config': {
                'state_topic': True,
                'command_topic': True,
                'payload_on': 'ON',
                'payload_off': 'OFF',
                'state_on': 'ON',
                'state_off': 'OFF',
                'optimistic': False
            },
            'startup_state_map': {
                'on': True,
                'off': False
            }
        },
        'button': {
            'discovery_type': 'button',
            'states': {},  # Buttons haben keinen State
            'commands': {
                'ON': True,
                'PRESS': True  # Alternative Command
            },
            'discovery_config': {
                'command_topic': True,
                'payload_press': 'ON'
            },
            'startup_state_map': {
                'on': True,
                'off': False
            }
        },
        'lock': {
            'discovery_type': 'lock',
            'states': {
                True: 'UNLOCKED',
                False: 'LOCKED'
            },
            'commands': {
                'LOCK': False,      # LOCK Kommando setzt den internen State auf False
                'UNLOCK': True,     # UNLOCK Kommando setzt den internen State auf True
                # Zusätzliche Kommandos für Home Assistant Kompatibilität
                'LOCK': False,
                'UNLOCK': True
            },
            'discovery_config': {
                'state_topic': True,
                'command_topic': True,
                'payload_lock': 'LOCK',
                'payload_unlock': 'UNLOCK',
                'state_locked': 'LOCKED',
                'state_unlocked': 'UNLOCKED',
                'optimistic': False
            },
            'startup_state_map': {
                'locked': False,    # "LOCKED" Startup-State setzt internen Value auf False
                'unlocked': True,   # "UNLOCKED" Startup-State setzt internen Value auf True
                'LOCKED': False,
                'UNLOCKED': True
            }
        },
        'cover': {
            'discovery_type': 'cover',
            'states': {
                'open': 'open',
                'closed': 'closed',
                'opening': 'opening',
                'closing': 'closing'
            },
            'commands': {
                'OPEN': 'OPEN',
                'CLOSE': 'CLOSE',
                'STOP': 'STOP'
            },
            'discovery_config': {
                'state_topic': True,
                'command_topic': True,
                'state_opening': 'opening',
                'state_closing': 'closing',
                'state_open': 'open',
                'state_closed': 'closed',
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'optimistic': False
            },
            'startup_state_map': {
                'open': 'open',
                'closed': 'closed',
                'opening': 'opening',
                'closing': 'closing'
            }
        },
        'binary_sensor': {
            'discovery_type': 'binary_sensor',
            'states': {
                True: 'ON',
                False: 'OFF'
            },
            'commands': {},  # Sensoren haben keine Commands
            'discovery_config': {
                'state_topic': True,
                'payload_on': 'ON',
                'payload_off': 'OFF'
            },
            'startup_state_map': {
                'on': True,
                'off': False
            }
        }
    }

    @classmethod
    def get_config(cls, entity_type: str) -> dict:
        """Gibt die Konfiguration für einen Entity Type zurück"""
        return cls.TYPES.get(entity_type.lower(), cls.TYPES['switch'])

    @classmethod
    def convert_to_mqtt_state(cls, entity_type: str, internal_state: bool) -> str:
        """Konvertiert einen internen State in einen MQTT State"""
        config = cls.get_config(entity_type)
        return config['states'].get(internal_state, 'OFF')

    @classmethod
    def convert_to_internal_state(cls, entity_type: str, mqtt_command: str) -> bool:
        """Konvertiert einen MQTT Command in einen internen State"""
        config = cls.get_config(entity_type)
        return config['commands'].get(mqtt_command.upper(), False)

    @classmethod
    def convert_startup_state(cls, entity_type: str, startup_state: str) -> bool:
        """Konvertiert einen Startup State String in einen internen Boolean State"""
        config = cls.get_config(entity_type)
        startup_state = startup_state.upper()
        return config['startup_state_map'].get(startup_state.lower(), False)

    @classmethod
    def get_discovery_config(cls, entity_type: str) -> dict:
        """Gibt die Discovery-Konfiguration für einen Entity Type zurück"""
        config = cls.get_config(entity_type)
        return config['discovery_config']

    @classmethod
    def get_discovery_type(cls, entity_type: str) -> str:
        """Gibt den Discovery Type für einen Entity Type zurück"""
        config = cls.get_config(entity_type)
        return config['discovery_type']