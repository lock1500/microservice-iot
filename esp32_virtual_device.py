# esp32_virtual_device.py
from flask import Flask, request, jsonify
import logging
import time
import base64
try:
    from Crypto.Signature import DSS
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import ECC
except ImportError:
    DSS = None
    SHA256 = None
    ECC = None
    logging.warning("pycryptodome not installed, signature verification disabled")
import os
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

devices = [{"device_id": config.DEVICE_ID, "state": "off"}]
public_key = None

def load_public_key():
    global public_key
    if ECC is None:
        logger.error("pycryptodome not available, cannot load public key")
        return False
    try:
        if not os.path.exists("ecdsa_public.pem"):
            logger.error("Public key file 'ecdsa_public.pem' not found")
            return False
        with open("ecdsa_public.pem", "rt") as f:
            public_key = ECC.import_key(f.read())
        logger.info("Public key loaded successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to load public key: {e}")
        return False

def verify_signature(chat_id: str, timestamp: str, signature_b64: str):
    if not public_key or DSS is None or SHA256 is None:
        logger.error("No public key or pycryptodome not available for verification")
        return False
    
    try:
        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 300:
            logger.error("Timestamp expired")
            return False
            
        message = f"{chat_id}:{timestamp}".encode('utf-8')
        h = SHA256.new(message)
        signature = base64.b64decode(signature_b64)
        verifier = DSS.new(public_key, 'fips-186-3')
        verifier.verify(h, signature)
        logger.info(f"Signature verified for chat_id: {chat_id}")
        return True
    except (ValueError, TypeError) as e:
        logger.error(f"Signature verification failed: {e}")
        return False

def find_device(device_id: str):
    for device in devices:
        if device["device_id"] == device_id:
            return device
    new_device = {"device_id": device_id, "state": "off"}
    devices.append(new_device)
    logger.info(f"Added new device: {device_id}")
    return new_device

@app.route('/signature', methods=['POST'])
def signature():
    data = request.get_json()
    if not data:
        logger.error("Missing JSON data")
        return jsonify({"status": "error", "message": "Missing JSON data"}), 400
    
    chat_id = data.get("chat_id")
    timestamp = data.get("timestamp")
    signature_b64 = data.get("signature")
    
    if not chat_id or not timestamp or not signature_b64:
        logger.error("Missing fields in JSON")
        return jsonify({"status": "error", "message": "Missing fields"}), 400
    
    if verify_signature(chat_id, timestamp, signature_b64):
        return jsonify({"status": "success", "message": "Signature valid"}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid signature"}), 403

@app.route('/Enable', methods=['GET', 'POST'])
def enable():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
    else:
        device_id = request.args.get('device_id')
        chat_id = request.args.get('chat_id', "default")
        timestamp = request.args.get('timestamp')
        signature_b64 = request.args.get('signature')
        username = request.args.get('username', "User")
        bot_token = request.args.get('bot_token', "")
    
    if not verify_signature(chat_id, timestamp, signature_b64):
        return jsonify({"status": "error", "message": "Invalid or expired signature"}), 403
    
    if not device_id or device_id != config.DEVICE_ID:
        logger.error(f"Invalid device_id: {device_id}, expected {config.DEVICE_ID}")
        return jsonify({"status": "error", "message": f"Invalid device_id, expected {config.DEVICE_ID}"}), 400
    
    device = find_device(device_id)
    device["state"] = "on"
    
    return jsonify({
        "status": "success",
        "message": "Device enabled",
        "state": device["state"],
        "device_id": device_id,
        "username": username
    }), 200

@app.route('/Disable', methods=['GET', 'POST'])
def disable():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
    else:
        device_id = request.args.get('device_id')
        chat_id = request.args.get('chat_id', "default")
        timestamp = request.args.get('timestamp')
        signature_b64 = request.args.get('signature')
        username = request.args.get('username', "User")
        bot_token = request.args.get('bot_token', "")
    
    if not verify_signature(chat_id, timestamp, signature_b64):
        return jsonify({"status": "error", "message": "Invalid or expired signature"}), 403
    
    if not device_id or device_id != config.DEVICE_ID:
        logger.error(f"Invalid device_id: {device_id}, expected {config.DEVICE_ID}")
        return jsonify({"status": "error", "message": f"Invalid device_id, expected {config.DEVICE_ID}"}), 400
    
    device = find_device(device_id)
    device["state"] = "off"
    
    return jsonify({
        "status": "success",
        "message": "Device disabled",
        "state": device["state"],
        "device_id": device_id,
        "username": username
    }), 200

@app.route('/GetStatus', methods=['GET', 'POST'])
def get_status():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
    else:
        device_id = request.args.get('device_id')
        chat_id = request.args.get('chat_id', "default")
        timestamp = request.args.get('timestamp')
        signature_b64 = request.args.get('signature')
        username = request.args.get('username', "User")
        bot_token = request.args.get('bot_token', "")
    
    if not verify_signature(chat_id, timestamp, signature_b64):
        return jsonify({"status": "error", "message": "Invalid or expired signature"}), 403
    
    if not device_id or device_id != config.DEVICE_ID:
        logger.error(f"Invalid device_id: {device_id}, expected {config.DEVICE_ID}")
        return jsonify({"status": "error", "message": f"Invalid device_id, expected {config.DEVICE_ID}"}), 400
    
    device = find_device(device_id)
    
    return jsonify({
        "status": "success",
        "message": device["state"],
        "state": device["state"],
        "device_id": device_id,
        "username": username
    }), 200

if __name__ == "__main__":
    try:
        load_public_key()
        logger.info(f"Starting Flask app on port 5010")
        app.run(host="0.0.0.0", port=5010, debug=False)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")