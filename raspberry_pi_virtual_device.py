from flask import Flask, request
import logging
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Simulate Raspberry Pi device state array
devices = [
    {"device_id": config.DEVICE_ID, "state": "off"}  # Default Raspberry Pi device
]

# Helper function: Find device by device_id
def find_device(device_id: str):
    for device in devices:
        if device["device_id"] == device_id:
            return device
    # If device not found, add it dynamically
    new_device = {"device_id": device_id, "state": "off"}
    devices.append(new_device)
    logger.info(f"Added new Raspberry Pi device: {device_id}")
    return new_device

# Route: Enable device
@app.route('/Enable', methods=['GET'])
def enable():
    device_id = request.args.get('device_id')
    if not device_id:
        return {"status": "error", "message": "Missing device_id parameter"}, 400

    device = find_device(device_id)
    device["state"] = "on"
    logger.info(f"Raspberry Pi device {device_id} enabled")
    return {"status": "success", "message": "Device enabled", "state": device["state"], "device_id": device_id}, 200

# Route: Disable device
@app.route('/Disable', methods=['GET'])
def disable():
    device_id = request.args.get('device_id')
    if not device_id:
        return {"status": "error", "message": "Missing device_id parameter"}, 400

    device = find_device(device_id)
    device["state"] = "off"
    logger.info(f"Raspberry Pi device {device_id} disabled")
    return {"status": "success", "message": "Device disabled", "state": device["state"], "device_id": device_id}, 200

# Route: Set device status
@app.route('/SetStatus', methods=['GET'])
def set_status():
    device_id = request.args.get('device_id')
    status = request.args.get('status')
    if not device_id:
        return {"status": "error", "message": "Missing device_id parameter"}, 400
    if not status:
        return {"status": "error", "message": "Missing status parameter"}, 400
    if status not in ["on", "off"]:
        return {"status": "error", "message": "Invalid status"}, 400

    device = find_device(device_id)
    device["state"] = status
    logger.info(f"Raspberry Pi device {device_id} status set to: {status}")
    return {"status": "success", "message": f"Device status set to {status}", "state": device["state"], "device_id": device_id}, 200

# Route: Get device status
@app.route('/GetStatus', methods=['GET'])
def get_status():
    device_id = request.args.get('device_id')
    if not device_id:
        return {"status": "error", "message": "Missing device_id parameter"}, 400

    device = find_device(device_id)
    logger.info(f"Raspberry Pi device {device_id} status: {device['state']}")
    return {"status": "success", "message": device["state"], "state": device["state"], "device_id": device_id}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.RASPBERRY_PI_DEVICE_PORT)  # Use config.RASPBERRY_PI_API_PORT