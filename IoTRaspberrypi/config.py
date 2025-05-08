import os

# LINE and Telegram API configurations
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')  # Telegram Bot Token
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"  # Telegram API URL
LINE_API_URL = os.getenv('LINE_API_URL', 'https://api.line.me/v2/bot/message')  # LINE API URL
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN', 'YOUR_LINE_ACCESS_TOKEN')  # LINE Bot Access Token

# IOTQueue (MQTT) and RabbitMQ configurations
IOTQUEUE_HOST = os.getenv('IOTQUEUE_HOST', 'localhost')  # IOTQueue host address
IOTQUEUE_PORT = int(os.getenv('IOTQUEUE_PORT', 1883))  # IOTQueue port
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')  # RabbitMQ host address
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))  # RabbitMQ port
RABBITMQ_QUEUE = "IMQueue"  # RabbitMQ queue name
DEVICE_ID = os.getenv('DEVICE_ID', 'esp_32_001')  # Default device ID

# Flask API configurations
TELEGRAM_API_HOST = os.getenv('TELEGRAM_API_HOST', 'localhost')  # Telegram Flask API host
TELEGRAM_API_PORT = int(os.getenv('TELEGRAM_API_PORT', 5000))  # Telegram Flask API port

LINE_API_HOST = os.getenv('LINE_API_HOST', 'localhost')  # LINE Flask API host
LINE_API_PORT = int(os.getenv('LINE_API_PORT', 5001))  # LINE Flask API port

# Add these new port configurations to your config.py:
ESP32_API_HOST = os.getenv('ESP32_API_HOST', 'localhost')  # ESP32 Flask API host
ESP32_API_PORT = int(os.getenv("ESP32_API_PORT", 5002))  # Port for ESP32 IoT Device service
RASPBERRY_PI_API_HOST = os.getenv('RASPBERRY_PI_API_HOST', 'localhost')  # Raspberry Pi Flask API host
RASPBERRY_PI_API_PORT = int(os.getenv("RASPBERRY_PI_API_PORT", 5003))  # Port for Raspberry Pi IoT Device service

#這裡是virtual
ESP32_DEVICE_HOST = os.getenv('ESP32_DEVICE_HOST', 'localhost')  # ESP32 Flask API host
ESP32_DEVICE_PORT = int(os.getenv('ESP32_DEVICE_PORT', 5010))  # ESP32 Flask API port
RASPBERRY_PI_DEVICE_HOST = os.getenv('RASPBERRY_PI_DEVICE_HOST', 'localhost')  # Raspberry Pi Flask API host
RASPBERRY_PI_DEVICE_PORT = int(os.getenv("RASPBERRY_PI_DEVICE_PORT", 5011))


# Device types and platforms
DEVICE_TYPES = ['light', 'fan']  # Supported device types
PLATFORMS = ['esp_32', 'pi']  # Supported platforms