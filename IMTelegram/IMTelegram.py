# IMTelegram.py
from flask import Flask, request, send_from_directory
from flask_swagger_ui import get_swaggerui_blueprint
import requests
import json
import config
import logging
import IoTQbroker
import IMQbroker
import threading
from threading import Lock
import os

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')  # Changed to DEBUG for detailed logging
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store all chat_ids for broadcasting messages, with a lock for thread safety
chat_ids = set()
chat_ids_lock = Lock()

# Function: Add chat_id to the chat_ids set, thread-safe
def add_chat_id(chat_id: str):
    with chat_ids_lock:
        chat_ids.add(chat_id)
        logger.debug(f"Added chat_id={chat_id} to chat_ids set")

# Function: Send message to Telegram user
def send_message(chat_id: str, text: str, user_id: str = None) -> bool:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    logger.debug(f"Sending Telegram message: chat_id={chat_id}, text={text}, user_id={user_id}")
    try:
        response = requests.post(url, json=payload, timeout=5)
        logger.debug(f"Telegram API response: status_code={response.status_code}, text={response.text}")
        if response.status_code == 200 and response.json().get("ok"):
            logger.info(f"Message sent successfully: chat_id={chat_id}, user_id={user_id}, text={text}")
            return True
        else:
            logger.error(f"Failed to send message: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False

# Route: Handle Telegram Webhook request
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data is None:
        logger.error("Webhook request could not be parsed as JSON")
        return {"ok": False, "message": "Invalid JSON"}, 400

    if 'message' not in data:
        logger.warning("No message in webhook request, ignoring")
        return {"ok": True, "message": "No message in request, ignored"}, 200

    message_text = data['message'].get('text', '')
    chat = data['message'].get('chat')
    if not chat:
        logger.error("No chat information in webhook request")
        return {"ok": False, "message": "No chat information in request"}, 400

    chat_id = str(chat.get('id'))
    user_id = str(data['message']['from'].get('id', 'Unknown'))
    username = data['message']['from'].get('username', data['message']['from'].get('first_name', 'User'))
    if username.startswith('@'):
        username = username[1:]
    group_id = str(chat.get('id')) if chat.get('type') in ['group', 'supergroup'] else None

    logger.info(f"Received message: chat_id={chat_id}, group_id={group_id}, user_id={user_id}, username={username}, text={message_text}")

    add_chat_id(chat_id)

    # Call IoTQbroker to parse message and send to IOTQueue
    device = IoTQbroker.Device("LivingRoomLight", device_id=config.DEVICE_ID, platform="telegram", chat_id=chat_id)
    iot_result = IoTQbroker.IoTParse_Message(message_text, device, chat_id, "telegram", user_id=user_id, username=username)
    logger.debug(f"IoTParse_Message result: {iot_result}")
    return {"ok": True}, 200

# Route: Manually send message to specific user
@app.route('/SendMsg', methods=['GET'])
def send_message_route():
    chat_id = request.args.get('chat_id')
    message = request.args.get('message')
    user_id = request.args.get('user_id')
    bot_token = request.args.get('bot_token')
    if not chat_id or not message:
        logger.error("Missing chat_id or message")
        return {"ok": False, "message": "Missing chat_id or message"}, 400

    success = send_message(chat_id, message, user_id)
    return {"ok": success, "message": "Message sent" if success else "Failed to send message"}, 200 if success else 500

# Route: Send message to all users bound to a specific device
@app.route('/SendGroupMessage', methods=['GET'])
def send_group_message_route():
    device_id = request.args.get('device_id')
    message = request.args.get('message')
    user_id = request.args.get('user_id')
    bot_token = request.args.get('bot_token')
    if not device_id or not message:
        logger.error("Missing device_id or message")
        return {"ok": False, "message": "Missing device_id or message"}, 400

    device = IoTQbroker.Device("LivingRoomLight", device_id=device_id)
    bound_users = device.get_bound_users()
    if not bound_users:
        logger.warning(f"No bound users for device {device_id}")
        return {"ok": False, "message": "This device has no bound users"}, 404

    success = True
    for chat_id in bound_users:
        if not send_message(chat_id, message, user_id):
            success = False
            logger.warning(f"Failed to send message to chat_id={chat_id}")

    return {"ok": success, "message": "Group message sent" if success else "Some messages failed to send"}, 200 if success else 500

# Route: Send message to all users who have bound any device
@app.route('/SendAllMessage', methods=['GET'])
def send_all_message_route():
    message = request.args.get('message')
    user_id = request.args.get('user_id')
    bot_token = request.args.get('bot_token')
    if not message:
        logger.error("Missing message")
        return {"ok": False, "message": "Missing message"}, 400

    all_users = IoTQbroker.Device.get_all_bound_users()
    if not all_users:
        logger.warning("No users have bound any device")
        return {"ok": False, "message": "No users have bound any device"}, 404

    success = True
    for chat_id in all_users:
        if not send_message(chat_id, message, user_id):
            success = False
            logger.warning(f"Failed to send message to chat_id={chat_id}")

    return {"ok": success, "message": "All messages sent" if success else "Some messages failed to send"}, 200 if success else 500

# Swagger UI setup
SWAGGER_URL = '/swagger'
API_URL = '/static/openapi.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "IM and IoT Microservices"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Serve openapi.yaml file
@app.route('/static/<path:path>')
def send_swagger(path):
    return send_from_directory('static', path)

# Main entry point
if __name__ == "__main__":
    # Ensure static directory and openapi.yaml exist
    if not os.path.exists('static'):
        os.makedirs('static')
    with open('static/openapi.yaml', 'w') as f:
        with open('openapi.yaml', 'r') as src:
            f.write(src.read())

    # Start IMQbroker to consume IMQueue in a thread
    imqbroker_thread = threading.Thread(target=IMQbroker.consume_im_queue)
    imqbroker_thread.daemon = True
    imqbroker_thread.start()
    logger.info("IMQbroker started in a separate thread (Telegram)")

    # Start Flask service
    app.run(host="0.0.0.0", port=config.TELEGRAM_API_PORT)