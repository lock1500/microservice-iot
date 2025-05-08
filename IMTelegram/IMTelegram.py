from flask import Flask, request
import requests
import json
import config
import logging
import IoTQbroker
import IMQbroker
import threading


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store all chat IDs for broadcasting messages
chat_ids = set()

# Function: Add chat ID to chat_ids set
def add_chat_id(chat_id: str):
    chat_ids.add(chat_id)

# Function: Send message to Telegram user
def send_message(chat_id: str, text: str) -> bool:
    url = f"{config.TELEGRAM_API_URL}/sendMessage"  # Telegram API send message URL
    payload = {"chat_id": chat_id, "text": text}  # Message parameters
    try:
        response = requests.post(url, json=payload)  # Send HTTP POST request
        if response.status_code == 200:
            logger.info(f"Message sent successfully: chat_id={chat_id}, text={text}")
            return True
        else:
            logger.error(f"Failed to send message: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False

# Function: Send message to Telegram group (same as individual message)
def send_group_message(group_id: str, text: str) -> bool:
    return send_message(group_id, text)  # Telegram group messages are same as individual

# Function: Send message to all known chat IDs
def send_all_message(text: str) -> bool:
    success = True
    for chat_id in chat_ids:  # Iterate over all chat IDs
        if not send_message(chat_id, text):  # Send message to each
            success = False
    return success

# Route: Handle Telegram Webhook requests
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()  # Get JSON data from request
    if data is None:
        logger.error("Webhook request could not be parsed as JSON")
        return {"ok": False, "message": "Invalid JSON"}, 400

    if 'message' not in data:
        logger.warning("No message in webhook request, ignoring")
        return {"ok": True, "message": "No message in request, ignored"}, 200

    message_text = data['message'].get('text', '')  # Get message text
    chat = data['message'].get('chat')  # Get chat info
    if not chat:
        logger.error("No chat info in webhook request")
        return {"ok": False, "message": "No chat info in request"}, 400

    chat_id = str(chat.get('id'))  # Get chat ID
    group_id = str(chat.get('id')) if chat.get('type') in ['group', 'supergroup'] else None  # Get group ID

    logger.info(f"Received message: chat_id={chat_id}, group_id={group_id}, text={message_text}")

    add_chat_id(chat_id)  # Add chat ID to chat_ids

    # Call IoTQbroker to parse message and send to IOTQueue
    device = IoTQbroker.Device("LivingRoomLight", device_id=config.DEVICE_ID, platform="telegram", chat_id=chat_id)
    iot_result = IoTQbroker.IoTParse_Message(message_text, device, chat_id, "telegram")
    if not iot_result["success"]:
        send_message(chat_id, "Please enter a valid command")  # Reply if command is invalid
    else:
        send_message(chat_id, f"Command received: {message_text}")  # Reply if command is valid

    return {"ok": True}, 200

# Route: Manually send message to specific user
@app.route('/SendMsg', methods=['GET'])
def send_message_route():
    chat_id = request.args.get('chat_id')  # Get chat ID
    message = request.args.get('message')  # Get message text
    if not chat_id or not message:
        return {"ok": False, "message": "Missing chat_id or message"}, 400

    success = send_message(chat_id, message)  # Send message
    return {"ok": success, "message": "Message sent" if success else "Failed to send message"}, 200 if success else 500

# Route: Manually send message to specific group
@app.route('/SendGroupMessage', methods=['GET'])
def send_group_message_route():
    group_id = request.args.get('group_id')  # Get group ID
    message = request.args.get('message')  # Get message text
    if not group_id or not message:
        return {"ok": False, "message": "Missing group_id or message"}, 400

    success = send_group_message(group_id, message)  # Send group message
    return {"ok": success, "message": "Group message sent" if success else "Failed to send group message"}, 200 if success else 500

# Route: Manually send message to all users
@app.route('/SendAllMessage', methods=['GET'])
def send_all_message_route():
    message = request.args.get('message')  # Get message text
    if not message:
        return {"ok": False, "message": "Missing message"}, 400

    success = send_all_message(message)  # Send message to all users
    return {"ok": success, "message": "All messages sent" if success else "Some messages failed to send"}, 200 if success else 500

# Main entry point
if __name__ == "__main__":
    # Start IMQbroker to consume IMQueue in a thread
    imqbroker_thread = threading.Thread(target=IMQbroker.consume_im_queue)
    imqbroker_thread.daemon = True  # Set as daemon thread
    imqbroker_thread.start()
    logger.info("IMQbroker started in a separate thread")

    # Start Flask service
    app.run(host="0.0.0.0", port=config.TELEGRAM_API_PORT)