# IMTelegram.py
from flask import Flask, request, send_from_directory, jsonify
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
import time  # Ensure time is imported for the test APIs

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
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
@app.route('/IMTelegram/webhook', methods=['POST'])
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
@app.route('/IMTelegram/SendMsg', methods=['GET'])
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
@app.route('/IMTelegram/SendGroupMessage', methods=['GET'])
def send_group_message_route():
    device_id = request.args.get('device_id')
    message = request.args.get('message')
    user_id = request.args.get('user_id')
    bot_token = request.args.get('bot_token')
    if not device_id or not message:
        logger.error("Missing device_id or message")
        return {"ok": False, "message": "Missing device_id or message"}, 400

    bindings = config.load_bindings()
    bound_users = bindings.get(device_id, [])
    if not bound_users:
        logger.warning(f"No bound users for device {device_id}")
        return {"ok": False, "message": "This device has no bound users"}, 404

    success = True
    for binding in bound_users:
        chat_id = binding["chat_id"]
        platform = binding["platform"]
        if platform == "telegram":
            if not send_message(chat_id, message, user_id):
                success = False
                logger.warning(f"Failed to send message to chat_id={chat_id} on Telegram")
        else:  # platform == "line"
            line_url = f"http://{config.LINE_API_HOST}:{config.LINE_API_PORT}/SendMsg"
            params = {
                "user_id": chat_id,
                "message": message,
                "bot_token": config.LINE_ACCESS_TOKEN
            }
            try:
                response = requests.get(line_url, params=params, timeout=5)
                if response.status_code != 200 or not response.json().get("ok"):
                    success = False
                    logger.warning(f"Failed to send message to chat_id={chat_id} on Line")
            except requests.RequestException as e:
                success = False
                logger.error(f"Error sending message to chat_id={chat_id} on Line: {e}")

    return {"ok": success, "message": "Group message sent" if success else "Some messages failed to send"}, 200 if success else 500

# Route: Send message to all users who have bound any device
@app.route('/IMTelegram/SendAllMessage', methods=['GET'])
def send_all_message_route():
    message = request.args.get('message')
    user_id = request.args.get('user_id')
    bot_token = request.args.get('bot_token')
    if not message:
        logger.error("Missing message")
        return {"ok": False, "message": "Missing message"}, 400

    all_users = set()
    bindings = config.load_bindings()
    for device_id in bindings:
        for binding in bindings[device_id]:
            all_users.add((binding["chat_id"], binding["platform"]))

    if not all_users:
        logger.warning("No users have bound any device")
        return {"ok": False, "message": "No users have bound any device"}, 404

    success = True
    for chat_id, platform in all_users:
        if platform == "telegram":
            if not send_message(chat_id, message, user_id):
                success = False
                logger.warning(f"Failed to send message to chat_id={chat_id} on Telegram")
        else:  # platform == "line"
            line_url = f"http://{config.LINE_API_HOST}:{config.LINE_API_PORT}/SendMsg"
            params = {
                "user_id": chat_id,
                "message": message,
                "bot_token": config.LINE_ACCESS_TOKEN
            }
            try:
                response = requests.get(line_url, params=params, timeout=5)
                if response.status_code != 200 or not response.json().get("ok"):
                    success = False
                    logger.warning(f"Failed to send message to chat_id={chat_id} on Line")
            except requests.RequestException as e:
                success = False
                logger.error(f"Error sending message to chat_id={chat_id} on Line: {e}")

    return {"ok": success, "message": "All messages sent" if success else "Some messages failed to send"}, 200 if success else 500

# Swagger UI setup
SWAGGER_URL = '/IMTelegram/swagger'
API_URL = '/IMTelegram/static/openapi.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "IM and IoT Microservices"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Serve openapi.yaml file
@app.route('/IMTelegram/static/<path:path>')
def send_swagger(path):
    return send_from_directory('static', path)
# 模擬 Telegram 使用者發送開燈和關燈訊息的測試 API
@app.route('/IMTelegram/test_esp32', methods=['GET'])
def test_esp32():
    """
    Test API to simulate a Telegram user sending 'turn on' and 'turn off' commands for esp32_light_001.
    Returns:
        JSON response indicating the success or failure of the simulated commands.
    """
    device_id = "esp32_light_001"
    chat_id = "7734108511"  # 模擬的 chat_id
    user_id = "test_user_987654"  # 模擬的 user_id
    username = "TestUser"         # 模擬的 username
    platform = "telegram"
    
    logger.info(f"Starting test for ESP32 device: {device_id}")
    
    try:
        # 初始化設備
        device = IoTQbroker.Device("LivingRoomLight", device_id=device_id, platform=platform, chat_id=chat_id)
        
        # 模擬發送開燈命令
        logger.info(f"Simulating 'turn on' command for {device_id}")
        enable_result = IoTQbroker.IoTParse_Message(f"turn on {device_id}", device, chat_id, platform, user_id=user_id, username=username)
        if not enable_result.get("success"):
            logger.error(f"Failed to simulate 'turn on' for {device_id}: {enable_result.get('message')}")
            return jsonify({"ok": False, "message": f"Failed to turn on {device_id}: {enable_result.get('message')}"}), 500
        
        
        # 模擬發送關燈命令
        logger.info(f"Simulating 'turn off' command for {device_id}")
        disable_result = IoTQbroker.IoTParse_Message(f"turn off {device_id}", device, chat_id, platform, user_id=user_id, username=username)
        if not disable_result.get("success"):
            logger.error(f"Failed to simulate 'turn off' for {device_id}: {disable_result.get('message')}")
            return jsonify({"ok": False, "message": f"Failed to turn off {device_id}: {disable_result.get('message')}"}), 500
        
        logger.info(f"Test completed successfully for {device_id}")
        return jsonify({
            "ok": True,
            "message": f"Successfully simulated turn on and turn off for {device_id}",
            "enable_result": enable_result,
            "disable_result": disable_result
        }), 200
    
    except Exception as e:
        logger.error(f"Error during ESP32 test for {device_id}: {e}")
        return jsonify({"ok": False, "message": f"Error during test: {str(e)}"}), 500

@app.route('/IMTelegram/test_raspberrypi', methods=['GET'])
def test_raspberrypi():
    """
    Test API to simulate a Telegram user sending 'turn on' and 'turn off' commands for raspberrypi_light_001.
    Returns:
        JSON response indicating the success or failure of the simulated commands.
    """
    device_id = "raspberrypi_light_001"
    chat_id = "7734108511"  # 模擬的 chat_id
    user_id = "test_user_987654"  # 模擬的 user_id
    username = "TestUser"         # 模擬的 username
    platform = "telegram"
    
    logger.info(f"Starting test for Raspberry Pi device: {device_id}")
    
    try:
        # 初始化設備
        device = IoTQbroker.Device("LivingRoomLight", device_id=device_id, platform=platform, chat_id=chat_id)
        
        # 模擬發送開燈命令
        logger.info(f"Simulating 'turn on' command for {device_id}")
        enable_result = IoTQbroker.IoTParse_Message(f"turn on {device_id}", device, chat_id, platform, user_id=user_id, username=username)
        if not enable_result.get("success"):
            logger.error(f"Failed to simulate 'turn on' for {device_id}: {enable_result.get('message')}")
            return jsonify({"ok": False, "message": f"Failed to turn on {device_id}: {enable_result.get('message')}"}), 500
        
        # 模擬發送關燈命令
        logger.info(f"Simulating 'turn off' command for {device_id}")
        disable_result = IoTQbroker.IoTParse_Message(f"turn off {device_id}", device, chat_id, platform, user_id=user_id, username=username)
        if not disable_result.get("success"):
            logger.error(f"Failed to simulate 'turn off' for {device_id}: {disable_result.get('message')}")
            return jsonify({"ok": False, "message": f"Failed to turn off {device_id}: {disable_result.get('message')}"}), 500
        
        logger.info(f"Test completed successfully for {device_id}")
        return jsonify({
            "ok": True,
            "message": f"Successfully simulated turn on and turn off for {device_id}",
            "enable_result": enable_result,
            "disable_result": disable_result
        }), 200
    
    except Exception as e:
        logger.error(f"Error during Raspberry Pi test for {device_id}: {e}")
        return jsonify({"ok": False, "message": f"Error during test: {str(e)}"}), 500
# Main entry point
if __name__ == "__main__":
    # Ensure static directory and openapi.yaml exist
    if not os.path.exists('static'):
        os.makedirs('static')
    with open('static/openapi.yaml', 'w') as f:
        with open('openapi.yaml', 'r') as src:
            f.write(src.read())

    # Start IMQbroker to consume IMQueue in a thread
    imqbroker_thread = threading.Thread(target=IMQbroker.consume_telegram_queue)
    imqbroker_thread.daemon = True
    imqbroker_thread.start()
    logger.info("IMQbroker started for Telegram queue")

    # Start Flask service
    app.run(host="0.0.0.0", port=config.TELEGRAM_API_PORT)