import pika
import json
import requests
import logging
import config
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Function: Send message via IMLine.py or IMTelegram.py API
def send_message(chat_id: str, text: str, platform: str = "telegram") -> bool:
    if platform == "telegram":
        url = f"http://{config.TELEGRAM_API_HOST}:{config.TELEGRAM_API_PORT}/SendMsg"  # Telegram API route
        params = {"chat_id": chat_id, "message": text}
    else:  # platform == "line"
        url = f"http://{config.LINE_API_HOST}:{config.LINE_API_PORT}/SendMsg"  # LINE API route
        params = {"user_id": chat_id, "message": text}

    try:
        response = requests.get(url, params=params)  # Send HTTP GET request
        if response.status_code == 200 and response.json().get("ok"):
            logger.info(f"Message sent successfully via API: platform={platform}, chat_id={chat_id}, text={text}")
            return True
        else:
            logger.error(f"Failed to send message via API: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending message via API: {e}")
        return False

# Function: Consume messages from IMQueue and handle device status
def consume_im_queue():
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=config.RABBITMQ_HOST, port=config.RABBITMQ_PORT, heartbeat=30, blocked_connection_timeout=60)
        )  # Connect to RabbitMQ
        channel = connection.channel()  # Create channel
        channel.queue_declare(queue=config.RABBITMQ_QUEUE, durable=True)  # Declare queue with durable=True

        # Callback: Process received messages
        def callback(ch, method, properties, body):
            message = json.loads(body)  # Parse message
            logger.info(f"Received message from IM Queue: {message}")

            # Process only device status messages
            if "device_status" in message:
                chat_id = message.get("chat_id")  # Get chat ID
                status = message["device_status"]  # Get device status
                platform = message.get("platform", "telegram")  # Get platform
                device_id = message.get("device_id", config.DEVICE_ID)  # Get device_id, fallback to config.DEVICE_ID
                if chat_id:
                    if status == "enabled":
                        send_message(chat_id, f"Device {device_id} enabled", platform)  # Notify enabled
                    elif status == "disabled":
                        send_message(chat_id, f"Device {device_id} disabled", platform)  # Notify disabled
                    else:
                        send_message(chat_id, f"Device {device_id} status: {status}", platform)  # Notify other status

        channel.basic_consume(queue=config.RABBITMQ_QUEUE, on_message_callback=callback, auto_ack=True)  # Start consuming queue
        logger.info("Started consuming IM Queue...")
        channel.start_consuming()  # Enter consumption loop
    except Exception as e:
        logger.error(f"Error consuming IM Queue: {e}")
        time.sleep(5)  # Wait 5 seconds before retry
        consume_im_queue()
