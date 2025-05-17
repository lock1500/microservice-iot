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

# Function: Consume messages from platform-specific IMQueue
def consume_im_queue(platform="telegram"):
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=config.RABBITMQ_HOST, port=config.RABBITMQ_PORT, heartbeat=30, blocked_connection_timeout=60)
        )  # Connect to RabbitMQ
        channel = connection.channel()  # Create channel

        # Declare exchange
        exchange_name = "im_exchange"
        channel.exchange_declare(exchange=exchange_name, exchange_type="direct")

        # Declare platform-specific queue
        queue_name = f"im_queue_{platform}"
        channel.queue_declare(queue=queue_name, durable=True)

        # Bind queue to exchange with platform as routing key
        channel.queue_bind(queue=queue_name, exchange=exchange_name, routing_key=platform)

        # Set prefetch count for fair dispatching
        channel.basic_qos(prefetch_count=1)

        # Callback: Process received messages
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body)  # Parse message
                logger.info(f"Received message from IM Queue ({platform}): {message}")

                # Process only device status messages
                if "device_status" in message:
                    chat_id = message.get("chat_id")  # Get chat ID
                    status = message["device_status"]  # Get device status
                    message_platform = message.get("platform", platform)  # Use message platform or fallback to consumer platform
                    device_id = message.get("device_id", config.DEVICE_ID)  # Get device_id, fallback to config.DEVICE_ID
                    if chat_id:
                        if status == "enabled":
                            send_message(chat_id, f"Device {device_id} enabled", message_platform)  # Notify enabled
                        elif status == "disabled":
                            send_message(chat_id, f"Device {device_id} disabled", message_platform)  # Notify disabled
                        else:
                            send_message(chat_id, f"Device {device_id} status: {status}", message_platform)  # Notify other status
                    else:
                        logger.error(f"No chat_id found in message: {message}")

                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                # Do not requeue failed messages; consider dead letter queue in production
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)  # Start consuming queue
        logger.info(f"Started consuming IM Queue for {platform}...")
        channel.start_consuming()  # Enter consumption loop
    except Exception as e:
        logger.error(f"Error consuming IM Queue for {platform}: {e}")
        time.sleep(5)  # Wait 5 seconds before retry
        consume_im_queue(platform)