import os

# LINE and Telegram API configurations
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

LINE_API_URL = os.getenv('LINE_API_URL', 'https://api.line.me/v2/bot/message')
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN', 'YOUR_LINE_ACCESS_TOKEN')

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
ESP32_DEVICE_HOST = os.getenv('ESP32_DEVICE_HOST', 'localhost')
ESP32_DEVICE_PORT = int(os.getenv('ESP32_DEVICE_PORT', 5010))
RASPBERRY_PI_DEVICE_HOST = os.getenv('RASPBERRY_PI_DEVICE_HOST', 'localhost')
RASPBERRY_PI_DEVICE_PORT = int(os.getenv("RASPBERRY_PI_DEVICE_PORT", 5011))

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