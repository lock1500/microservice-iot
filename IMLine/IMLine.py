# IMLine.py
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
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

try:
    line_bot_api = LineBotApi(config.LINE_ACCESS_TOKEN)
    logger.info("LineBotApi initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize LineBotApi: {e}")
    raise

user_ids = set()
user_ids_lock = Lock()

greeted_users = set()
greeted_users_lock = Lock()

def add_user_id(user_id: str):
    with user_ids_lock:
        user_ids.add(user_id)
        logger.debug(f"Added user_id={user_id} to user_ids set")

def check_and_add_greeted_user(chat_id: str) -> bool:
    with greeted_users_lock:
        if chat_id not in greeted_users:
            greeted_users.add(chat_id)
            return True
        return False

def get_line_user_display_name(user_id: str) -> str:
    try:
        profile = line_bot_api.get_profile(user_id)
        display_name = profile.display_name or "User"
        logger.debug(f"Fetched display name for user_id={user_id}: {display_name}")
        return display_name
    except LineBotApiError as e:
        logger.warning(f"LineBotApiError fetching display name for user_id={user_id}: {e}")
        return "User"
    except Exception as e:
        logger.error(f"Unexpected error fetching display name for user_id={user_id}: {e}")
        return "User"

def get_line_group_name(group_id: str) -> str:
    url = f"{config.LINE_API_URL}/group/{group_id}/summary"
    headers = {"Authorization": f"Bearer {config.LINE_ACCESS_TOKEN}", "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        group_summary = response.json()
        return group_summary.get("groupName", "Group")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch group name for group_id={group_id}: {e}")
        return "Group"

def send_message(to: str, text: str, display_name: str = None) -> bool:
    if not config.LINE_ACCESS_TOKEN:
        logger.error("LINE_ACCESS_TOKEN is not set")
        return False
    url = f"{config.LINE_API_URL}/push"
    headers = {"Authorization": f"Bearer {config.LINE_ACCESS_TOKEN}", "Content-Type": "application/json"}
    greeting = f"Hi, {display_name or 'User'}\n" if check_and_add_greeted_user(to) else ""
    message_text = f"{greeting}{text}"
    payload = {"to": to, "messages": [{"type": "text", "text": message_text}]}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        response.raise_for_status()
        logger.info(f"Message sent successfully: to={to}, display_name={display_name}, text={message_text}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to {to}: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        return False

def send_all_message(text: str, display_name: str = None) -> bool:
    success = True
    with user_ids_lock:
        for uid in list(user_ids):
            if not send_message(uid, text, display_name):
                success = False
                logger.warning(f"Failed to send message to user_id={uid}")
    return success

@app.route('/IMLine/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if data is None:
            logger.error("Webhook request could not be parsed as JSON")
            return {"ok": False, "message": "Invalid JSON"}, 400
        if 'events' not in data:
            logger.warning("No events in webhook request, ignoring")
            return {"ok": True, "message": "No events in request, ignored"}, 200
        for event in data['events']:
            event_type = event.get('type')
            if event_type != 'message':
                logger.info(f"Ignoring non-message event: type={event_type}")
                continue
            message = event.get('message', {})
            if message.get('type') != 'text':
                logger.info(f"Ignoring non-text message: type={message.get('type')}")
                continue
            message_text = message.get('text', '').strip()
            if not message_text:
                logger.warning("Empty message text, ignoring")
                continue
            source = event.get('source', {})
            source_type = source.get('type')
            user_id = source.get('userId')
            group_id = source.get('groupId')
            room_id = source.get('roomId')
            chat_id = group_id or room_id or user_id
            if not chat_id:
                logger.error("No userId, groupId, or roomId in webhook request")
                continue
            display_name = None
            if source_type == 'user' and user_id:
                display_name = get_line_user_display_name(user_id)
                add_user_id(user_id)
            elif source_type == 'group' and group_id:
                display_name = get_line_group_name(group_id)
            elif source_type == 'room' and room_id:
                display_name = "Room"
            else:
                logger.warning(f"Unknown source type: {source_type}, skipping")
                continue
            logger.info(f"Received message: chat_id={chat_id}, source_type={source_type}, display_name={display_name}, text={message_text}")
            try:
                device = IoTQbroker.Device("LivingRoomLight", device_id=config.DEVICE_ID, platform="line", chat_id=chat_id)
                iot_result = IoTQbroker.IoTParse_Message(message_text, device, chat_id, "line", user_id=user_id if source_type == 'user' else None, username=display_name)
                logger.debug(f"IoTParse_Message result: {iot_result}")
                if not iot_result.get("success"):
                    send_message(chat_id, iot_result.get("message", "Failed to process command"), display_name)
            except Exception as e:
                logger.error(f"Error processing IoT message for chat_id={chat_id}: {e}", exc_info=True)
                send_message(chat_id, "An error occurred while processing your command. Please try again.", display_name)
                continue
        return {"ok": True}, 200
    except Exception as e:
        logger.error(f"Unexpected error in webhook: {e}", exc_info=True)
        return {"ok": False, "message": "Internal server error"}, 500

@app.route('/IMLine/SendMsg', methods=['GET'])
def send_message_route():
    user_id = request.args.get('user_id')
    message = request.args.get('message')
    if not user_id or not message:
        return {"ok": False, "message": "Missing user_id or message"}, 400
    display_name = get_line_user_display_name(user_id)
    success = send_message(user_id, message, display_name)
    return {"ok": success, "message": "Message sent" if success else "Failed to send message"}, 200 if success else 500

@app.route('/IMLine/SendGroupMessage', methods=['GET'])
def send_group_message_route():
    device_id = request.args.get('device_id')
    message = request.args.get('message')
    if not device_id or not message:
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
        if platform == "line":
            if not send_message(chat_id, message):
                success = False
                logger.warning(f"Failed to send message to chat_id={chat_id} on Line")
        else:  # platform == "telegram"
            telegram_url = f"http://{config.TELEGRAM_API_HOST}:{config.TELEGRAM_API_PORT}/SendMsg"
            params = {
                "chat_id": chat_id,
                "message": message,
                "bot_token": config.TELEGRAM_BOT_TOKEN
            }
            try:
                response = requests.get(telegram_url, params=params, timeout=5)
                if response.status_code != 200 or not response.json().get("ok"):
                    success = False
                    logger.warning(f"Failed to send message to chat_id={chat_id} on Telegram")
            except requests.RequestException as e:
                success = False
                logger.error(f"Error sending message to chat_id={chat_id} on Telegram: {e}")

    return {"ok": success, "message": "Group message sent" if success else "Some messages failed to send"}, 200 if success else 500

@app.route('/IMLine/SendAllMessage', methods=['GET'])
def send_all_message_route():
    message = request.args.get('message')
    if not message:
        return {"ok": False, "message": "Missing message"}, 400

    all_bound_users = set()
    bindings = config.load_bindings()
    for device_id in bindings:
        for binding in bindings[device_id]:
            all_bound_users.add((binding["chat_id"], binding["platform"]))

    if not all_bound_users:
        return {"ok": False, "message": "No users have bound any device"}, 404

    success = True
    for chat_id, platform in all_bound_users:
        if platform == "line":
            if not send_message(chat_id, message):
                success = False
                logger.warning(f"Failed to send message to chat_id={chat_id} on Line")
        else:  # platform == "telegram"
            telegram_url = f"http://{config.TELEGRAM_API_HOST}:{config.TELEGRAM_API_PORT}/SendMsg"
            params = {
                "chat_id": chat_id,
                "message": message,
                "bot_token": config.TELEGRAM_BOT_TOKEN
            }
            try:
                response = requests.get(telegram_url, params=params, timeout=5)
                if response.status_code != 200 or not response.json().get("ok"):
                    success = False
                    logger.warning(f"Failed to send message to chat_id={chat_id} on Telegram")
            except requests.RequestException as e:
                success = False
                logger.error(f"Error sending message to chat_id={chat_id} on Telegram: {e}")

    return {"ok": success, "message": "All messages sent" if success else "Some messages failed to send"}, 200 if success else 500

SWAGGER_URL = '/IMLine/swagger'
API_URL = '/IMLine/static/openapi.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL, config={'app_name': "IM and IoT Microservices"})
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

@app.route('/IMLine/static/<path:path>')
def send_swagger(path):
    try:
        return send_from_directory('static', path)
    except Exception as e:
        logger.error(f"Failed to serve static file {path}: {e}")
        return {"ok": False, "message": "File not found"}, 404
# 模擬 Telegram 使用者發送開燈和關燈訊息的測試 API
@app.route('/IMLine/test_esp32', methods=['GET'])
def test_esp32():
    """
    Test API to simulate a Telegram user sending 'turn on' and 'turn off' commands for esp32_light_001.
    Returns:
        JSON response indicating the success or failure of the simulated commands.
    """
    device_id = "esp32_light_001"
    chat_id = "Uf4ff2bc9aa098eef207844288e82b312"  # 模擬的 chat_id
    user_id = "test_user_987654"  # 模擬的 user_id
    username = "TestUser"         # 模擬的 username
    platform = "line"
    
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

@app.route('/IMLine/test_raspberrypi', methods=['GET'])
def test_raspberrypi():
    """
    Test API to simulate a Telegram user sending 'turn on' and 'turn off' commands for raspberrypi_light_001.
    Returns:
        JSON response indicating the success or failure of the simulated commands.
    """
    device_id = "raspberrypi_light_001"
    chat_id = "Uf4ff2bc9aa098eef207844288e82b312"  # 模擬的 chat_id
    user_id = "test_user_987654"  # 模擬的 user_id
    username = "TestUser"         # 模擬的 username
    platform = "line"
    
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
if __name__ == "__main__":
    try:
        if not os.path.exists('static'):
            os.makedirs('static')
            logger.info("Created static directory")
        if os.path.exists('openapi.yaml'):
            with open('static/openapi.yaml', 'w') as f:
                with open('openapi.yaml', 'r') as src:
                    f.write(src.read())
            logger.info("Successfully copied openapi.yaml to static directory")
        else:
            logger.warning("openapi.yaml file not found, Swagger UI may not work")
    except Exception as e:
        logger.error(f"Error setting up static directory or openapi.yaml: {e}")
    try:
        imqbroker_thread = threading.Thread(target=IMQbroker.consume_line_queue)
        imqbroker_thread.daemon = True
        imqbroker_thread.start()
        logger.info("IMQbroker started for LINE queue")
    except Exception as e:
        logger.error(f"Failed to start IMQbroker thread: {e}")
        raise
    try:
        app.run(host="0.0.0.0", port=config.LINE_API_PORT, threaded=True, debug=False)
    except Exception as e:
        logger.error(f"Failed to start Flask service: {e}")
        raise