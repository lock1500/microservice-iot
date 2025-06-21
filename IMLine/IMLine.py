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
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize LineBotApi
try:
    line_bot_api = LineBotApi(config.LINE_ACCESS_TOKEN)
    logger.info("LineBotApi initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize LineBotApi: {e}")
    raise

# Store all user_ids for broadcasting messages, with a lock for thread safety
user_ids = set()
user_ids_lock = Lock()

# Track chat_ids that have received Hi, displayName, with a lock for thread safety
greeted_users = set()
greeted_users_lock = Lock()

# Function: Add user_id to the user_ids set, thread-safe
def add_user_id(user_id: str):
    with user_ids_lock:
        user_ids.add(user_id)
        logger.debug(f"Added user_id={user_id} to user_ids set")

# Function: Check if user has been greeted and add to greeted_users, thread-safe
def check_and_add_greeted_user(chat_id: str) -> bool:
    with greeted_users_lock:
        if chat_id not in greeted_users:
            greeted_users.add(chat_id)
            return True
        return False

# Function: Fetch Line user display name using LineBotApi
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

# Function: Fetch Line group name using HTTP request (LineBotApi does not support this directly)
def get_line_group_name(group_id: str) -> str:
    url = f"{config.LINE_API_URL}/group/{group_id}/summary"
    headers = {
        "Authorization": f"Bearer {config.LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        group_summary = response.json()
        return group_summary.get("groupName", "Group")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch group name for group_id={group_id}: {e}")
        return "Group"

# Function: Send message to Line user or group
def send_message(to: str, text: str, display_name: str = None) -> bool:
    if not config.LINE_ACCESS_TOKEN:
        logger.error("LINE_ACCESS_TOKEN is not set")
        return False
    url = f"{config.LINE_API_URL}/push"
    headers = {
        "Authorization": f"Bearer {config.LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    # Add greeting only if not previously sent
    greeting = f"Hi, {display_name or 'User'}\n" if check_and_add_greeted_user(to) else ""
    message_text = f"{greeting}{text}"
    payload = {
        "to": to,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        response.raise_for_status()
        logger.info(f"Message sent successfully: to={to}, display_name={display_name}, text={message_text}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to {to}: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        return False

# Function: Send message to all known user_ids, thread-safe
def send_all_message(text: str, display_name: str = None) -> bool:
    success = True
    with user_ids_lock:
        for uid in list(user_ids):
            if not send_message(uid, text, display_name):
                success = False
                logger.warning(f"Failed to send message to user_id={uid}")
    return success

# Route: Handle Line Webhook request
@app.route('/webhook', methods=['POST'])
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

            # Fetch display name or group name
            display_name = None
            if source_type == 'user' and user_id:
                display_name = get_line_user_display_name(user_id)
                add_user_id(user_id)
            elif source_type == 'group' and group_id:
                display_name = get_line_group_name(group_id)
            elif source_type == 'room' and room_id:
                display_name = "Room"  # Line rooms don't have a summary API, use default
            else:
                logger.warning(f"Unknown source type: {source_type}, skipping")
                continue

            logger.info(f"Received message: chat_id={chat_id}, source_type={source_type}, display_name={display_name}, text={message_text}")

            # Call IoTQbroker to parse message and send to IOTQueue
            try:
                device = IoTQbroker.Device("LivingRoomLight", device_id=config.DEVICE_ID, platform="line", chat_id=chat_id)
                iot_result = IoTQbroker.IoTParse_Message(
                    message_text,
                    device,
                    chat_id,
                    "line",
                    user_id=user_id if source_type == 'user' else None,
                    username=display_name
                )
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

# Route: Manually send message to specific user
@app.route('/SendMsg', methods=['GET'])
def send_message_route():
    user_id = request.args.get('user_id')
    message = request.args.get('message')
    if not user_id or not message:
        return {"ok": False, "message": "Missing user_id or message"}, 400

    display_name = get_line_user_display_name(user_id)
    success = send_message(user_id, message, display_name)
    return {"ok": success, "message": "Message sent" if success else "Failed to send message"}, 200 if success else 500

# Route: Manually send message to specific group
@app.route('/SendGroupMessage', methods=['GET'])
def send_group_message_route():
    group_id = request.args.get('group_id')
    message = request.args.get('message')
    if not group_id or not message:
        return {"ok": False, "message": "Missing group_id or message"}, 400

    display_name = get_line_group_name(group_id)
    success = send_message(group_id, message, display_name)
    return {"ok": success, "message": "Group message sent" if success else "Failed to send group message"}, 200 if success else 500

# Route: Manually send message to all users
@app.route('/SendAllMessage', methods=['GET'])
def send_all_message_route():
    message = request.args.get('message')
    if not message:
        return {"ok": False, "message": "Missing message"}, 400

    success = send_all_message(message)
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
    try:
        return send_from_directory('static', path)
    except Exception as e:
        logger.error(f"Failed to serve static file {path}: {e}")
        return {"ok": False, "message": "File not found"}, 404

# Main entry point
if __name__ == "__main__":
    # Ensure static directory and openapi.yaml exist
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

    # Start IMQbroker to consume IMQueue in a thread
    try:
        imqbroker_thread = threading.Thread(target=IMQbroker.consume_im_queue)
        imqbroker_thread.daemon = True
        imqbroker_thread.start()
        logger.info("IMQbroker started in a separate thread (Line)")
    except Exception as e:
        logger.error(f"Failed to start IMQbroker thread: {e}")
        raise

    # Start Flask service
    try:
        app.run(host="0.0.0.0", port=config.LINE_API_PORT, threaded=True, debug=False)
    except Exception as e:
        logger.error(f"Failed to start Flask service: {e}")
        raise