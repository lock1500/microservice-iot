from flask import Flask, request, jsonify
import logging
import config
import time
import base64
from Crypto.Signature import DSS
from Crypto.Hash import SHA256
from Crypto.PublicKey import ECC
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Simulate Raspberry Pi device state
devices = [
    {"device_id": config.DEVICE_ID, "state": "off"}
]

# ECDSA private key
private_key = None

def load_private_key():
    global private_key
    try:
        if not os.path.exists("ecdsa_private.pem"):
            logger.error("Private key file not found")
            return False
        with open("ecdsa_private.pem", "rt") as f:
            private_key = ECC.import_key(f.read())
        logger.info("Private key loaded successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to load private key: {e}")
        return False

def generate_signature(chat_id: str):
    if not private_key:
        return {"success": False, "error": "No private key"}
    
    try:
        timestamp = str(int(time.time()))
        message = f"{chat_id}:{timestamp}".encode()
        h = SHA256.new(message)
        signer = DSS.new(private_key, 'fips-186-3', encoding='der')
        signature = signer.sign(h)
        return {
            "success": True,
            "chat_id": chat_id,
            "timestamp": timestamp,
            "signature": base64.b64encode(signature).decode()
        }
    except Exception as e:
        logger.error(f"Error generating signature: {e}")
        return {"success": False, "error": str(e)}

def find_device(device_id: str):
    for device in devices:
        if device["device_id"] == device_id:
            return device
    new_device = {"device_id": device_id, "state": "off"}
    devices.append(new_device)
    logger.info(f"Added new device: {device_id}")
    return new_device

@app.route('/Enable', methods=['GET'])
def enable():
    device_id = request.args.get('device_id')
    chat_id = request.args.get('chat_id', "default")
    username = request.args.get('username', "User")
    bot_token = request.args.get('bot_token', "")
    
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400
    
    device = find_device(device_id)
    device["state"] = "on"
    
    # Generate and log signature
    signature = generate_signature(chat_id)
    signature["username"] = username
    signature["bot_token"] = bot_token
    logger.info(f"Generated signature: {signature}")
    
    return jsonify({
        "status": "success",
        "message": "Device enabled",
        "state": device["state"],
        "device_id": device_id,
        "signature_data": signature
    }), 200

@app.route('/Disable', methods=['GET'])
def disable():
    device_id = request.args.get('device_id')
    chat_id = request.args.get('chat_id', "default")
    username = request.args.get('username', "User")
    bot_token = request.args.get('bot_token', "")
    
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400
    
    device = find_device(device_id)
    device["state"] = "off"
    
    signature = generate_signature(chat_id)
    signature["username"] = username
    signature["bot_token"] = bot_token
    logger.info(f"Generated signature: {signature}")
    
    return jsonify({
        "status": "success",
        "message": "Device disabled",
        "state": device["state"],
        "device_id": device_id,
        "signature_data": signature
    }), 200

@app.route('/GetStatus', methods=['GET'])
def get_status():
    device_id = request.args.get('device_id')
    chat_id = request.args.get('chat_id', "default")
    username = request.args.get('username', "User")
    bot_token = request.args.get('bot_token', "")
    
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400
    
    device = find_device(device_id)
    
    signature = generate_signature(chat_id)
    signature["username"] = username
    signature["bot_token"] = bot_token
    logger.info(f"Generated signature: {signature}")
    
    return jsonify({
        "status": "success",
        "message": device["state"],
        "state": device["state"],
        "device_id": device_id,
        "signature_data": signature
    }), 200

if __name__ == "__main__":
    load_private_key()
    app.run(host="0.0.0.0", port=config.RASPBERRY_PI_DEVICE_PORT)