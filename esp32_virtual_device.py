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

# Simulate ESP32 device state array
devices = [
    {"device_id": config.DEVICE_ID, "state": "off"}
]

# ECDSA public key
public_key = None

def load_public_key():
    global public_key
    try:
        if not os.path.exists("ecdsa_public.pem"):
            logger.error("Public key file not found")
            return False
        with open("ecdsa_public.pem", "rt") as f:
            public_key = ECC.import_key(f.read())
        logger.info("Public key loaded successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to load public key: {e}")
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
def verify_signature():
    if not public_key:
        return jsonify({"status": "error", "message": "Public key not loaded"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No data"}), 400

    required_fields = ['chat_id', 'timestamp', 'signature']
    if not all(field in data for field in required_fields):
        return jsonify({"status": "error", "message": "Missing fields"}), 400

    try:
        message = f"{data['chat_id']}:{data['timestamp']}".encode()
        h = SHA256.new(message)
        signature = base64.b64decode(data['signature'])
        verifier = DSS.new(public_key, 'fips-186-3', encoding='der')
        verifier.verify(h, signature)
        return jsonify({"status": "success", "message": "Signature valid"}), 200
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return jsonify({"status": "error", "message": "Invalid signature"}), 403

@app.route('/Enable', methods=['GET'])
def enable():
    device_id = request.args.get('device_id')
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400
    
    device = find_device(device_id)
    device["state"] = "on"
    return jsonify({
        "status": "success",
        "message": "Device enabled",
        "state": device["state"],
        "device_id": device_id
    }), 200

@app.route('/Disable', methods=['GET'])
def disable():
    device_id = request.args.get('device_id')
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400
    
    device = find_device(device_id)
    device["state"] = "off"
    return jsonify({
        "status": "success",
        "message": "Device disabled",
        "state": device["state"],
        "device_id": device_id
    }), 200

@app.route('/GetStatus', methods=['GET'])
def get_status():
    device_id = request.args.get('device_id')
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400
    
    device = find_device(device_id)
    return jsonify({
        "status": "success",
        "message": device["state"],
        "state": device["state"],
        "device_id": device_id
    }), 200

if __name__ == "__main__":
    load_public_key()
    app.run(host="0.0.0.0", port=config.ESP32_DEVICE_PORT)