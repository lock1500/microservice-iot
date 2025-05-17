import paho.mqtt.client as mqtt
import pika
import json
import config
import logging
import threading
import time
import requests
from flask import Flask, request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

class RaspberryPiDevice:
    def __init__(self, name: str, device_id: str, broker_host: str = config.IOTQUEUE_HOST, broker_port: int = config.IOTQUEUE_PORT):
        self.name = name
        self.device_id = device_id
        self.device_type = "raspberry_pi"
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client = mqtt.Client(client_id=f"pi_device_{name}_{device_id}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.reconnect_delay_set(min_delay=1, max_delay=120)

        # Initialize RabbitMQ connection
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        self.connect_rabbitmq()

    def connect_rabbitmq(self):
        try:
            parameters = pika.ConnectionParameters(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                heartbeat=30,
                blocked_connection_timeout=60
            )
            self.rabbitmq_connection = pika.BlockingConnection(parameters)
            self.rabbitmq_channel = self.rabbitmq_connection.channel()
            self.rabbitmq_channel.queue_declare(queue=config.RABBITMQ_QUEUE, durable=True)
            logger.info(f"Connected to RabbitMQ: host={config.RABBITMQ_HOST}, port={config.RABBITMQ_PORT}")
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            time.sleep(5)
            self.connect_rabbitmq()

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Raspberry Pi {self.name} ({self.device_id}) connected to IOTQueue broker")
            self.client.subscribe(f"raspberry_pi/light/{self.device_id}/message")
        else:
            logger.error(f"Raspberry Pi {self.name} ({self.device_id}) connection failed, return code: {rc}")

    def on_disconnect(self, client, userdata, rc):
        logger.warning(f"Raspberry Pi {self.name} ({self.device_id}) disconnected from IOTQueue broker, attempting to reconnect...")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        logger.info(f"Raspberry Pi {self.name} ({self.device_id}) received message - Topic: {topic}, Payload: {payload}")

        if topic == f"raspberry_pi/light/{self.device_id}/message":
            try:
                payload_dict = json.loads(payload)
                command = payload_dict.get("command")
                chat_id = payload_dict.get("chat_id")
                platform = payload_dict.get("platform", "telegram")
                device_id = payload_dict.get("device_id", self.device_id)
                if device_id != self.device_id:
                    logger.info(f"Ignoring message for device_id {device_id}, this device is {self.device_id}")
                    return
                if command == "on":
                    self.enable(chat_id, platform)
                elif command == "off":
                    self.disable(chat_id, platform)
                elif command == "get_status":
                    self.get_status(chat_id, platform)
                elif command in ["on", "off"]:
                    self.set_status(command, chat_id, platform)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse payload as JSON: {e}, payload: {payload}")
                return

    def notify_status(self, status: str, chat_id: str = None, platform: str = "telegram"):
        message = {"device_status": status, "chat_id": chat_id, "platform": platform, "device_id": self.device_id}
        try:
            # Declare exchange
            self.rabbitmq_channel.exchange_declare(exchange="im_exchange", exchange_type="direct")
            # Publish to exchange with platform as routing key
            self.rabbitmq_channel.basic_publish(
                exchange="im_exchange",
                routing_key=platform,
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2)  # Persistent message
            )
            logger.info(f"Sent device status to IM Queue: {message}")
            self.client.publish(f"raspberry_pi/light/{self.device_id}/status", json.dumps({"status": status}))
        except (pika.exceptions.StreamLostError, pika.exceptions.ConnectionClosed) as e:
            logger.warning(f"RabbitMQ connection lost: {e}, attempting to reconnect...")
            self.connect_rabbitmq()
            # Re-declare exchange after reconnect
            self.rabbitmq_channel.exchange_declare(exchange="im_exchange", exchange_type="direct")
            self.rabbitmq_channel.basic_publish(
                exchange="im_exchange",
                routing_key=platform,
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2)  # Persistent message
            )
            logger.info(f"Sent device status to IM Queue after reconnect: {message}")
            self.client.publish(f"raspberry_pi/light/{self.device_id}/status", json.dumps({"status": status}))

    def get_api_base_url(self):
        return f"http://{config.RASPBERRY_PI_DEVICE_HOST}:{config.RASPBERRY_PI_DEVICE_PORT}"

    def enable(self, chat_id: str = None, platform: str = "telegram"):
        try:
            response = requests.get(f"{self.get_api_base_url()}/Enable", params={"device_id": self.device_id})
            if response.status_code == 200 and response.json().get("status") == "success":
                logger.info(f"Raspberry Pi {self.name} ({self.device_id}) enabled")
                self.notify_status("enabled", chat_id, platform)
                return response.json()
            else:
                logger.error(f"Failed to enable device: {response.text}")
                return {"status": "error", "message": "Failed to enable device"}
        except Exception as e:
            logger.error(f"Failed to call Raspberry Pi Enable API: {e}")
            return {"status": "error", "message": "Failed to call API"}

    def disable(self, chat_id: str = None, platform: str = "telegram"):
        try:
            response = requests.get(f"{self.get_api_base_url()}/Disable", params={"device_id": self.device_id})
            if response.status_code == 200 and response.json().get("status") == "success":
                logger.info(f"Raspberry Pi {self.name} ({self.device_id}) disabled")
                self.notify_status("disabled", chat_id, platform)
                return response.json()
            else:
                logger.error(f"Failed to disable device: {response.text}")
                return {"status": "error", "message": "Failed to disable device"}
        except Exception as e:
            logger.error(f"Failed to call Raspberry Pi Disable API: {e}")
            return {"status": "error", "message": "Failed to call API"}

    def set_status(self, status: str, chat_id: str = None, platform: str = "telegram"):
        try:
            response = requests.get(f"{self.get_api_base_url()}/SetStatus", params={"device_id": self.device_id, "status": status})
            if response.status_code == 200 and response.json().get("status") == "success":
                logger.info(f"Raspberry Pi {self.name} ({self.device_id}) status set to: {status}")
                self.notify_status(status, chat_id, platform)
                return response.json()
            else:
                logger.error(f"Failed to set device status: {response.text}")
                return {"status": "error", "message": "Failed to set device status"}
        except Exception as e:
            logger.error(f"Failed to call Raspberry Pi SetStatus API: {e}")
            return {"status": "error", "message": "Failed to call API"}

    def get_status(self, chat_id: str = None, platform: str = "telegram"):
        try:
            response = requests.get(f"{self.get_api_base_url()}/GetStatus", params={"device_id": self.device_id})
            if response.status_code == 200 and response.json().get("state") is not None:
                state = response.json().get("state")
                logger.info(f"Raspberry Pi {self.name} ({self.device_id}) status: {state}")
                self.notify_status(state, chat_id, platform)
                return response.json()
            else:
                logger.error(f"Failed to get device status: {response.text}")
                return {"status": "error", "message": "Failed to get device status"}
        except Exception as e:
            logger.error(f"Failed to call Raspberry Pi GetStatus API: {e}")
            return {"status": "error", "message": "Failed to call API"}

    def start_mqtt(self):
        try:
            self.client.connect(self.broker_host, self.broker_port)
            self.client.loop_start()
            logger.info(f"Raspberry Pi {self.name} ({self.device_id}) MQTT started, waiting for messages...")
        except Exception as e:
            logger.error(f"Raspberry Pi {self.name} ({self.device_id}) MQTT start failed: {e}")
            time.sleep(5)
            self.start_mqtt()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        if self.rabbitmq_connection and not self.rabbitmq_connection.is_closed:
            self.rabbitmq_connection.close()
        logger.info(f"Raspberry Pi {self.name} ({self.device_id}) stopped")

# Create Raspberry Pi device instance
pi_device = RaspberryPiDevice("LivingRoomLight", device_id="raspberry_pi_001")

# Flask Routes
@app.route('/Enable', methods=['GET'])
def enable_route():
    device_id = request.args.get('device_id')
    chat_id = request.args.get('chat_id')
    platform = request.args.get('platform', 'telegram')
    if not device_id:
        return {"status": "error", "message": "Missing device_id parameter"}, 400
    if device_id != pi_device.device_id:
        return {"status": "error", "message": f"Device {device_id} not found"}, 404

    result = pi_device.enable(chat_id, platform)
    return result, 200 if result.get("status") == "success" else 500

@app.route('/Disable', methods=['GET'])
def disable_route():
    device_id = request.args.get('device_id')
    chat_id = request.args.get('chat_id')
    platform = request.args.get('platform', 'telegram')
    if not device_id:
        return {"status": "error", "message": "Missing device_id parameter"}, 400
    if device_id != pi_device.device_id:
        return {"status": "error", "message": f"Device {device_id} not found"}, 404

    result = pi_device.disable(chat_id, platform)
    return result, 200 if result.get("status") == "success" else 500

@app.route('/GetStatus', methods=['GET'])
def get_status_route():
    device_id = request.args.get('device_id')
    chat_id = request.args.get('chat_id')
    platform = request.args.get('platform', 'telegram')
    if not device_id:
        return {"status": "error", "message": "Missing device_id parameter"}, 400
    if device_id != pi_device.device_id:
        return {"status": "error", "message": f"Device {device_id} not found"}, 404

    result = pi_device.get_status(chat_id, platform)
    return result, 200 if result.get("status") == "success" else 500

@app.route('/SetStatus', methods=['GET'])
def set_status_route():
    device_id = request.args.get('device_id')
    status = request.args.get('status')
    chat_id = request.args.get('chat_id')
    platform = request.args.get('platform', 'telegram')
    if not device_id:
        return {"status": "error", "message": "Missing device_id parameter"}, 400
    if not status:
        return {"status": "error", "message": "Missing status parameter"}, 400
    if status not in ["on", "off"]:
        return {"status": "error", "message": "Invalid status"}, 400
    if device_id != pi_device.device_id:
        return {"status": "error", "message": f"Device {device_id} not found"}, 404

    result = pi_device.set_status(status, chat_id, platform)
    return result, 200 if result.get("status") == "success" else 500

if __name__ == "__main__":
    # Start MQTT client thread
    mqtt_thread = threading.Thread(target=pi_device.start_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    # Start Flask service on Raspberry Pi-specific port
    logger.info(f"Starting Flask API for RaspberryPiDevice on port {config.RASPBERRY_PI_API_PORT}")
    app.run(host="0.0.0.0", port=config.RASPBERRY_PI_API_PORT, threaded=True)