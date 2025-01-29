# mqtt_config.py
# Version: 1.0.0

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
                True: 'LOCKED',
                False: 'UNLOCKED'
            },
            'commands': {
                'LOCK': True,
                'UNLOCK': False
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
                'locked': True,
                'unlocked': False
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
        startup_state = startup_state.lower()
        return config['startup_state_map'].get(startup_state, False)

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