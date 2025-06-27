# config.py
import os
import json
import logging
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Thread-safe lock for configuration access
config_lock = threading.Lock()

# Cache for last modified time and config
_last_modified = 0
_cached_config = None

def load_device_config(file_path=None):
    """
    Load device configuration from a JSON file.
    Args:
        file_path (str, optional): Path to the config file. Defaults to ~/Desktop/device_config.json.
    Returns:
        dict: Device configuration with ESP32 and Raspberry Pi host/port.
    """
    global _last_modified, _cached_config
    if not file_path:
        file_path = os.path.normpath(os.path.expanduser("~/Desktop/device_config.json"))
    
    default_config = {
        "esp32": {
            "host": "localhost",
            "port": 5010
        },
        "raspberry_pi": {
            "host": "localhost",
            "port": 5011
        }
    }
    
    try:
        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
        with config_lock:
            if mtime > _last_modified:
                logger.debug(f"Checked file {file_path}, mtime: {mtime}, last_modified: {_last_modified}")
                logger.info(f"Config file {file_path} modified or first load, reloading...")
                if not os.path.exists(file_path):
                    logger.warning(f"Config file not found at {file_path}. Creating with default values.")
                    with open(file_path, 'w') as f:
                        json.dump(default_config, f, indent=4)
                    logger.info(f"Created default config file at {file_path}")
                    config_data = default_config
                else:
                    with open(file_path, 'r') as f:
                        config_data = json.load(f)
                    
                    for device in ["esp32", "raspberry_pi"]:
                        if device not in config_data:
                            logger.error(f"Missing '{device}' configuration. Using default values.")
                            config_data = default_config
                            break
                        if "host" not in config_data[device] or "port" not in config_data[device]:
                            logger.error(f"Invalid configuration for '{device}'. Using default values.")
                            config_data = default_config
                            break
                        try:
                            config_data[device]["port"] = int(config_data[device]["port"])
                        except (TypeError, ValueError):
                            logger.error(f"Invalid port for '{device}'. Using default values.")
                            config_data = default_config
                            break
                
                _cached_config = config_data
                _last_modified = mtime
                logger.debug(f"Loaded config: {_cached_config}")
            else:
                if _cached_config is None:
                    logger.warning("No cached config, loading default...")
                    _cached_config = default_config
                logger.debug(f"Config unchanged: {file_path}, mtime: {mtime}")
        
        return _cached_config.copy()
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in {file_path}: {e}. Using default values.")
        with config_lock:
            _cached_config = default_config
            _last_modified = mtime
        return default_config
    except Exception as e:
        logger.error(f"Error loading config from {file_path}: {e}. Using default values.")
        with config_lock:
            _cached_config = default_config
            _last_modified = mtime
        return default_config

def start_config_polling(file_path, interval=1):
    """
    Start a thread to periodically check for config file changes.
    Args:
        file_path (str): Path to the config file.
        interval (int): Polling interval in seconds.
    """
    def poll_config():
        while True:
            try:
                load_device_config(file_path)
            except Exception as e:
                logger.error(f"Error in config polling: {e}")
            time.sleep(interval)
    
    polling_thread = threading.Thread(target=poll_config, daemon=True)
    polling_thread.start()
    logger.info(f"Started polling {file_path} every {interval} seconds")

# Initialize configuration
config_file_path = os.getenv('DEVICE_CONFIG_PATH', os.path.expanduser("~/Desktop/device_config.json"))
_cached_config = load_device_config(config_file_path)

# Start polling in a separate thread
start_config_polling(config_file_path)

# LINE and Telegram API configurations
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

LINE_API_URL = os.getenv('LINE_API_URL', 'https://api.line.me/v2/bot/message')
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN', 'YOUR_LINE_ACCESS_TOKEN_HERE')

# IOTQueue (MQTT) and RabbitMQ configurations
IOTQUEUE_HOST = os.getenv('IOTQUEUE_HOST', 'localhost')
IOTQUEUE_PORT = int(os.getenv('IOTQUEUE_PORT', 1883))
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_QUEUE = "IMQueue"
DEVICE_ID = os.getenv('DEVICE_ID', 'esp32_light_001')

# Flask API configurations
TELEGRAM_API_HOST = os.getenv('TELEGRAM_API_HOST', 'localhost')
TELEGRAM_API_PORT = int(os.getenv('TELEGRAM_API_PORT', 5000))
LINE_API_HOST = os.getenv('LINE_API_HOST', 'localhost')
LINE_API_PORT = int(os.getenv('LINE_API_PORT', 5001))
ESP32_API_HOST = os.getenv('ESP32_API_HOST', 'localhost')
ESP32_API_PORT = int(os.getenv("ESP32_API_PORT", 5002))
RASPBERRY_PI_API_HOST = os.getenv('RASPBERRY_PI_API_HOST', 'localhost')
RASPBERRY_PI_API_PORT = int(os.getenv("RASPBERRY_PI_API_PORT", 5003))

# Device types and platforms
DEVICE_TYPES = ['light', 'fan']
PLATFORMS = ['esp_32', 'pi']

# Supported device IDs
SUPPORTED_DEVICES = [
    "esp32_light_001",
    "esp32_fan_002",
    "raspberrypi_light_001",
    "raspberrypi_fan_002"
]