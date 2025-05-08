from flask import Flask, request
import requests
import json
import config
import logging
import IoTQbroker
import IMQbroker
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store chat IDs
chat_ids = set()

def add_chat_id(chat_id: str):
    chat_ids.add(chat_id)

def send_message(chat_id: str, text: str) -> bool:
    url = f"{config.LINE_API_URL}/push"
    headers = {"Authorization": f"Bearer {config.LINE_ACCESS_TOKEN}"}
    payload = {
        "to": chat_id,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            logger.info(f"Message sent successfully: chat_id={chat_id}, text={text}")
            return True
        else:
            logger.error(f"Failed to send message: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False

def send_group_message(group_id: str, text: str) -> bool:
    url = f"{config.LINE_API_URL}/push"
    headers = {"Authorization": f"Bearer {config.LINE_ACCESS_TOKEN}"}
    payload = {
        "to": group_id,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            logger.info(f"Group message sent successfully: group_id={group_id}, text={text}")
            return True
        else:
            logger.error(f"Failed to send group message: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending group message: {e}")
        return False

def send_all_message(text: str) -> bool:
    success = True
    for chat_id in chat_ids:
        if not send_message(chat_id, text):
            success = False
    return success

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data is None:
        logger.error("Webhook request could not be parsed as JSON")
        return {"ok": False, "message": "Invalid JSON"}, 400

    events = data.get("events", [])
    if not events:
        logger.warning("No events in webhook request, ignoring")
        return {"ok": True, "message": "No events in request, ignored"}, 200

    for event in events:
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue

        reply_token = event.get("replyToken")
        user_id = event["source"].get("userId")
        group_id = event["source"].get("groupId") if event["source"].get("type") in ["group"] else None
        message_text = event["message"]["text"]

        logger.info(f"Received message: user_id={user_id}, group_id={group_id}, text={message_text}")

        add_chat_id(user_id)

        # Directly call IoTQbroker to parse message and send to IOTQueue
        device = IoTQbroker.Device("LivingRoomLight", device_id=config.DEVICE_ID, platform="line", chat_id=user_id)
        iot_result = IoTQbroker.IoTParse_Message(message_text, device, user_id, "line")
        if not iot_result["success"]:
            send_message(user_id, "Please enter a valid command")
        else:
            send_message(user_id, f"Command received: {message_text}")

    return {"ok": True}, 200

@app.route('/SendMsg', methods=['GET'])
def send_message_route():
    user_id = request.args.get('user_id')
    message = request.args.get('message')
    if not user_id or not message:
        return {"ok": False, "message": "Missing user_id or message"}, 400

    success = send_message(user_id, message)
    return {"ok": success, "message": "Message sent" if success else "Failed to send message"}, 200 if success else 500

@app.route('/SendGroupMessage', methods=['GET'])
def send_group_message_route():
    group_id = request.args.get('group_id')
    message = request.args.get('message')
    if not group_id or not message:
        return {"ok": False, "message": "Missing group_id or message"}, 400

    success = send_group_message(group_id, message)
    return {"ok": success, "message": "Group message sent" if success else "Failed to send group message"}, 200 if success else 500

@app.route('/SendAllMessage', methods=['GET'])
def send_all_message_route():
    message = request.args.get('message')
    if not message:
        return {"ok": False, "message": "Missing message"}, 400

    success = send_all_message(message)
    return {"ok": success, "message": "All messages sent" if success else "Some messages failed to send"}, 200 if success else 500

if __name__ == "__main__":
    # Start IMQbroker to consume IMQueue in a thread
    imqbroker_thread = threading.Thread(target=IMQbroker.consume_im_queue)
    imqbroker_thread.daemon = True
    imqbroker_thread.start()
    logger.info("IMQbroker started in a separate thread")

    # Start Flask service
    app.run(host="0.0.0.0", port=config.LINE_API_PORT)