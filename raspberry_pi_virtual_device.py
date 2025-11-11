from flask import Flask, request, jsonify
import logging
import time
import base64
import os
import sys
import atexit

try:
    from Crypto.Signature import DSS
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import ECC
except ImportError:
    DSS = None
    SHA256 = None
    ECC = None
    logging.warning("pycryptodome not installed, signature verification disabled")

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    RELAY_1 = 17
    RELAY_2 = 27
    GPIO.setup(RELAY_1, GPIO.OUT)
    GPIO.setup(RELAY_2, GPIO.OUT)
    GPIO.output(RELAY_1, GPIO.HIGH)
    GPIO.output(RELAY_2, GPIO.HIGH)
except (ImportError, RuntimeError):
    # 開發環境下使用模擬
    from fake_rpi.RPi import GPIO
    GPIO.setmode(GPIO.BCM)
    RELAY_1 = 17
    RELAY_2 = 27
    # 注意：這些調用在模擬環境下不會有實際效果
    GPIO.setup(RELAY_1, GPIO.OUT)
    GPIO.setup(RELAY_2, GPIO.OUT)
    GPIO.output(RELAY_1, GPIO.HIGH)
    GPIO.output(RELAY_2, GPIO.HIGH)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
devices = [{"device_id": "raspberrypi_light_001", "state": "off"}]
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
    # Check crypto library availability
    if ECC is None or public_key is None:
        logger.warning("Crypto libraries not available, skipping signature verification")
        return True        
    try:
        logger.debug(f"Starting signature verification for chat_id: {chat_id}, timestamp: {timestamp}")
        
        message = f"{chat_id}:{timestamp}"
        logger.debug(f"Original message to verify: '{message}'")
        
        message_bytes = message.encode('utf-8')
        logger.debug(f"Message bytes: {message_bytes.hex()}")
        
        h = SHA256.new(message_bytes)
        logger.debug(f"SHA256 hash: {h.hexdigest()}")
        
        logger.debug(f"Received base64 signature: {signature_b64}")
        try:
            signature = base64.b64decode(signature_b64)
            logger.debug(f"Decoded signature (hex): {signature.hex()}")
            logger.debug(f"Signature length: {len(signature)} bytes")
        except Exception as e:
            logger.error(f"Base64 decoding failed: {str(e)}")
            logger.error(f"Problematic base64 string: {signature_b64}")
            return False
        
        logger.debug("Creating DSS verifier...")
        verifier = DSS.new(public_key, 'fips-186-3')
        
        logger.debug("Starting signature verification...")
        try:
            verifier.verify(h, signature)
            logger.info("Signature verification SUCCESSFUL")
            logger.debug(f"Verified message: '{message}'")
            logger.debug(f"With signature: {signature.hex()}")
            return True
        except ValueError as ve:
            logger.error(f"Signature verification FAILED (ValueError): {str(ve)}")
            logger.debug(f"Failed details - Hash: {h.hexdigest()}, Signature: {signature.hex()}")
            return False
        except TypeError as te:
            logger.error(f"Signature verification FAILED (TypeError): {str(te)}")
            return False
            
    except base64.binascii.Error as be:
        logger.error(f"Base64 decoding error: {str(be)}")
        logger.error(f"Problematic base64 string: {signature_b64}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during signature verification: {str(e)}", exc_info=True)
        return False

def find_device(device_id: str):
    for device in devices:
        if device["device_id"] == device_id:
            return device
    new_device = {"device_id": device_id, "state": "off"}
    devices.append(new_device)
    logger.info(f"Added new device: {device_id}")
    return new_device

def turn_on_light():
    """Turn on both relays to activate the light"""
    GPIO.output(RELAY_1, GPIO.LOW)
    GPIO.output(RELAY_2, GPIO.LOW)
    logger.info("Light turned on (both relays activated)")

def turn_off_light():
    """Turn off both relays to deactivate the light"""
    GPIO.output(RELAY_1, GPIO.HIGH)
    GPIO.output(RELAY_2, GPIO.HIGH)
    logger.info("Light turned off (both relays deactivated)")

def blink_light(times=3, interval=0.5):
    """Blink the light by toggling both relays together"""
    for _ in range(times):
        GPIO.output(RELAY_1, GPIO.LOW)
        GPIO.output(RELAY_2, GPIO.LOW)
        time.sleep(interval)
        GPIO.output(RELAY_1, GPIO.HIGH)
        GPIO.output(RELAY_2, GPIO.HIGH)
        time.sleep(interval)
    logger.info(f"Light blinked {times} times")

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

# 新的 Raspberry Pi API 路徑
@app.route('/Pi/<device_id>/Enable', methods=['GET', 'POST'])
def enable_pi(device_id):
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
    else:
        chat_id = request.args.get('chat_id', "default")
        timestamp = request.args.get('timestamp')
        signature_b64 = request.args.get('signature')
        username = request.args.get('username', "User")
        bot_token = request.args.get('bot_token', "")
    
    if not verify_signature(chat_id, timestamp, signature_b64):
        return jsonify({"status": "error", "message": "Invalid or expired signature"}), 403
    
    if not device_id or device_id != "raspberrypi_light_001":
        logger.error(f"Invalid device_id: {device_id}, expected raspberrypi_light_001")
        return jsonify({"status": "error", "message": "Invalid device_id, expected raspberrypi_light_001"}), 400
    
    device = find_device(device_id)
    device["state"] = "on"
    turn_on_light()
    
    return jsonify({
        "status": "success",
        "message": "Device enabled",
        "state": device["state"],
        "device_id": device_id,
        "username": username
    }), 200

@app.route('/Pi/<device_id>/Disable', methods=['GET', 'POST'])
def disable_pi(device_id):
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
    else:
        chat_id = request.args.get('chat_id', "default")
        timestamp = request.args.get('timestamp')
        signature_b64 = request.args.get('signature')
        username = request.args.get('username', "User")
        bot_token = request.args.get('bot_token', "")
    
    if not verify_signature(chat_id, timestamp, signature_b64):
        return jsonify({"status": "error", "message": "Invalid or expired signature"}), 403
    
    if not device_id or device_id != "raspberrypi_light_001":
        logger.error(f"Invalid device_id: {device_id}, expected raspberrypi_light_001")
        return jsonify({"status": "error", "message": "Invalid device_id, expected raspberrypi_light_001"}), 400
    
    device = find_device(device_id)
    device["state"] = "off"
    turn_off_light()
    
    return jsonify({
        "status": "success",
        "message": "Device disabled",
        "state": device["state"],
        "device_id": device_id,
        "username": username
    }), 200

@app.route('/Pi/<device_id>/GetStatus', methods=['GET', 'POST'])
def get_status_pi(device_id):
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
    else:
        chat_id = request.args.get('chat_id', "default")
        timestamp = request.args.get('timestamp')
        signature_b64 = request.args.get('signature')
        username = request.args.get('username', "User")
        bot_token = request.args.get('bot_token', "")
    
    if not verify_signature(chat_id, timestamp, signature_b64):
        return jsonify({"status": "error", "message": "Invalid or expired signature"}), 403
    
    if not device_id or device_id != "raspberrypi_light_001":
        logger.error(f"Invalid device_id: {device_id}, expected raspberrypi_light_001")
        return jsonify({"status": "error", "message": "Invalid device_id, expected raspberrypi_light_001"}), 400
    
    device = find_device(device_id)
    
    return jsonify({
        "status": "success",
        "message": device["state"],
        "state": device["state"],
        "device_id": device_id,
        "username": username
    }), 200

# 保持向後兼容的舊端點（可選）
@app.route('/Enable', methods=['GET', 'POST'])
def enable_legacy():
    return enable_pi("raspberrypi_light_001")

@app.route('/Disable', methods=['GET', 'POST'])
def disable_legacy():
    return disable_pi("raspberrypi_light_001")

@app.route('/GetStatus', methods=['GET', 'POST'])
def get_status_legacy():
    return get_status_pi("raspberrypi_light_001")

def cleanup():
    """Cleanup GPIO on exit"""
    try:
        GPIO.cleanup()
        logger.info("GPIO cleanup completed")
    except Exception as e:
        logger.error(f"Error during GPIO cleanup: {e}")

atexit.register(cleanup)

if __name__ == "__main__":
    try:
        load_public_key()
        logger.info("Starting Raspberry Pi Virtual Device on port 5011")
        app.run(host="0.0.0.0", port=5011, debug=False)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")