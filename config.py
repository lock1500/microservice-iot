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
_bindings_last_modified = 0
_cached_bindings = None

def load_device_config(file_path=None):
    """
    Load device configuration from a JSON file.
    Args:
        file_path (str, optional): Path to the config file. Defaults to ~/Desktop/device_config.json.
    Returns:
        dict: Device configuration with ESP32 and Raspberry Pi URL or host/port.
    """
    global _last_modified, _cached_config
    if not file_path:
        file_path = os.path.normpath(os.path.expanduser("~/Desktop/device_config.json"))
    
    default_config = {
        "esp32": {
            "url": "http://localhost:5010"
        },
        "raspberry_pi": {
            "url": "http://localhost:5011"
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
                        # Support legacy host/port format
                        if "host" in config_data[device] and "port" in config_data[device]:
                            try:
                                config_data[device]["port"] = int(config_data[device]["port"])
                                config_data[device]["url"] = f"http://{config_data[device]['host']}:{config_data[device]['port']}"
                            except (TypeError, ValueError):
                                logger.error(f"Invalid port for '{device}'. Using default values.")
                                config_data = default_config
                                break
                        elif "url" not in config_data[device]:
                            logger.error(f"Missing 'url' or valid 'host/port' for '{device}'. Using default values.")
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

def load_bindings(file_path=None):
    """
    Load bindings from a JSON file.
    Args:
        file_path (str, optional): Path to the bindings file. Defaults to ~/Desktop/bindings.json.
    Returns:
        dict: Bindings data mapping device IDs to lists of user bindings.
    """
    global _bindings_last_modified, _cached_bindings
    if not file_path:
        file_path = os.path.normpath(os.path.expanduser("~/Desktop/bindings.json"))
    
    default_bindings = {}
    
    try:
        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
        with config_lock:
            if mtime > _bindings_last_modified:
                logger.debug(f"Checked bindings file {file_path}, mtime: {mtime}, last_modified: {_bindings_last_modified}")
                logger.info(f"Bindings file {file_path} modified or first load, reloading...")
                if not os.path.exists(file_path):
                    logger.warning(f"Bindings file not found at {file_path}. Creating with default values.")
                    with open(file_path, 'w') as f:
                        json.dump(default_bindings, f, indent=4)
                    logger.info(f"Created default bindings file at {file_path}")
                    bindings_data = default_bindings
                else:
                    with open(file_path, 'r') as f:
                        bindings_data = json.load(f)
                    
                    # Validate bindings data
                    for device_id in bindings_data:
                        if not isinstance(bindings_data[device_id], list):
                            logger.error(f"Invalid bindings format for device {device_id}. Using default values.")
                            bindings_data = default_bindings
                            break
                        for binding in bindings_data[device_id]:
                            if not all(key in binding for key in ["chat_id", "platform"]):
                                logger.error(f"Invalid binding entry for device {device_id}. Using default values.")
                                bindings_data = default_bindings
                                break
                    
                _cached_bindings = bindings_data
                _bindings_last_modified = mtime
                logger.debug(f"Loaded bindings: {_cached_bindings}")
            else:
                if _cached_bindings is None:
                    logger.warning("No cached bindings, loading default...")
                    _cached_bindings = default_bindings
                logger.debug(f"Bindings unchanged: {file_path}, mtime: {mtime}")
        
        return _cached_bindings.copy()
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in {file_path}: {e}. Using default values.")
        with config_lock:
            _cached_bindings = default_bindings
            _bindings_last_modified = mtime
        return default_bindings
    except Exception as e:
        logger.error(f"Error loading bindings from {file_path}: {e}. Using default values.")
        with config_lock:
            _cached_bindings = default_bindings
            _bindings_last_modified = mtime
        return default_bindings

def save_binding(device_id: str, chat_id: str, platform: str, file_path=None):
    """
    Save a new binding to the bindings file.
    Args:
        device_id (str): Device ID to bind to.
        chat_id (str): Chat ID of the user.
        platform (str): Platform (telegram or line).
        file_path (str, optional): Path to the bindings file. Defaults to ~/Desktop/bindings.json.
    Returns:
        bool: True if successful, False otherwise.
    """
    if not file_path:
        file_path = os.path.normpath(os.path.expanduser("~/Desktop/bindings.json"))
    
    try:
        bindings_data = load_bindings(file_path)
        if device_id not in bindings_data:
            bindings_data[device_id] = []
        
        # Check if binding already exists
        for binding in bindings_data[device_id]:
            if binding["chat_id"] == chat_id and binding["platform"] == platform:
                logger.info(f"Binding already exists for device {device_id}, chat_id {chat_id}, platform {platform}")
                return True
        
        bindings_data[device_id].append({"chat_id": chat_id, "platform": platform})
        with config_lock:
            with open(file_path, 'w') as f:
                json.dump(bindings_data, f, indent=4)
            global _bindings_last_modified, _cached_bindings
            _bindings_last_modified = os.path.getmtime(file_path)
            _cached_bindings = bindings_data
        logger.info(f"Saved binding for device {device_id}, chat_id {chat_id}, platform {platform}")
        return True
    except Exception as e:
        logger.error(f"Failed to save binding for device {device_id}, chat_id {chat_id}, platform {platform}: {e}")
        return False

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
                load_bindings(file_path=os.path.expanduser("~/Desktop/bindings.json"))
            except Exception as e:
                logger.error(f"Error in config polling: {e}")
            time.sleep(interval)
    
    polling_thread = threading.Thread(target=poll_config, daemon=True)
    polling_thread.start()
    logger.info(f"Started polling {file_path} every {interval} seconds")

# Initialize configuration
config_file_path = os.getenv('DEVICE_CONFIG_PATH', os.path.expanduser("~/Desktop/device_config.json"))
_cached_config = load_device_config(config_file_path)
_cached_bindings = load_bindings()

# Start polling in a separate thread
start_config_polling(config_file_path)

# LINE and Telegram API configurations
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

LINE_API_URL = os.getenv('LINE_API_URL', 'https://api.line.me/v2/bot/message')
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN', 'YOUR_LINE_ACCESS_TOKEN')

# IOTQueue (MQTT) and RabbitMQ configurations
IOTQUEUE_HOST = os.getenv('IOTQUEUE_HOST', 'localhost')
IOTQUEUE_PORT = int(os.getenv('IOTQUEUE_PORT', 1883))
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_LINE_QUEUE = "IM_Line_Queue"
RABBITMQ_TELEGRAM_QUEUE = "IM_Telegram_Queue"
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