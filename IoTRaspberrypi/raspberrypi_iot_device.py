# raspberrypi_iot_device.py
from flask import Flask, request, send_from_directory, jsonify
from flask_swagger_ui import get_swaggerui_blueprint
import pika
import json
import config
import logging
import threading
import time
import os
import base64

try:
    from Crypto.Signature import DSS
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import ECC
except ImportError:
    DSS = None
    SHA256 = None
    ECC = None
    logging.warning("pycryptodome not installed, signature generation disabled")
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('raspberrypi.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
private_key = None

def load_private_key():
    global private_key
    if ECC is None:
        logger.error("pycryptodome not available, cannot load private key")
        return False
    try:
        if not os.path.exists("/app/keys/ecdsa_private.pem"):
            logger.error("Private key file '/app/keys/ecdsa_private.pem' not found")
            return False
        with open("/app/keys/ecdsa_private.pem", "rt") as f:
            private_key = ECC.import_key(f.read())
        logger.info("Private key loaded successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to load private key: {e}")
        return False

def generate_signature(chat_id: str):
    if not private_key or DSS is None or SHA256 is None:
        logger.error("No private key or pycryptodome not available")
        return {"success": False, "error": "No private key or pycryptodome not available"}
    
    try:
        timestamp = str(int(time.time()))
        message = f"{chat_id}:{timestamp}".encode('utf-8')
        h = SHA256.new(message)
        signer = DSS.new(private_key, 'fips-186-3')
        signature = signer.sign(h)
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        result = {
            "success": True,
            "chat_id": chat_id,
            "timestamp": timestamp,
            "signature": signature_b64,
            "username": "",
            "bot_token": ""
        }
        logger.info(f"Generated signature for chat_id: {chat_id}")
        return result
    except Exception as e:
        logger.error(f"Error generating signature: {e}")
        return {"success": False, "error": str(e)}

class RaspberryPiDevice:
    def __init__(self, name: str, device_id: str):
        self.name = name
        self.device_id = device_id
        self.manufacturer = "raspberrypi"
        self.device_type = "light" if "light" in device_id else "fan"
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        self.rabbitmq_consumer_thread = None
        self.running = False
        self.start_rabbitmq()

    def setup_rabbitmq_connection(self):
        """Setup RabbitMQ connection using BlockingConnection"""
        try:
            parameters = pika.ConnectionParameters(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                heartbeat=30,
                blocked_connection_timeout=60
            )
            self.rabbitmq_connection = pika.BlockingConnection(parameters)
            self.rabbitmq_channel = self.rabbitmq_connection.channel()
            logger.info("RabbitMQ BlockingConnection established successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to establish RabbitMQ BlockingConnection: {e}")
            return False

    def on_rabbitmq_message(self, channel, method, properties, body):
        try:
            payload = json.loads(body.decode('utf-8'))
            logger.info(f"Received RabbitMQ message: {payload}")
            
            command = payload.get("command")
            if command == "on":
                self.handle_enable(payload)
            elif command == "off":
                self.handle_disable(payload)
            elif command == "get_status":
                self.handle_get_status(payload)
                
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in RabbitMQ message: {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Error processing RabbitMQ message: {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def consume_messages(self):
        """Consume messages from RabbitMQ queue using BlockingConnection"""
        while self.running:
            try:
                if not self.rabbitmq_connection or self.rabbitmq_connection.is_closed:
                    logger.info("RabbitMQ connection closed, reconnecting...")
                    if not self.setup_rabbitmq_connection():
                        time.sleep(5)
                        continue

                queue_name = "iot_raspberrypi_queue"
                self.rabbitmq_channel.queue_declare(queue=queue_name, durable=True)
                self.rabbitmq_channel.basic_qos(prefetch_count=1)
                
                logger.info(f"Starting to consume messages from {queue_name}")
                
                for method, properties, body in self.rabbitmq_channel.consume(
                    queue_name, inactivity_timeout=1, auto_ack=False):
                    
                    if not self.running:
                        break
                        
                    if method is None:
                        continue
                        
                    self.on_rabbitmq_message(self.rabbitmq_channel, method, properties, body)
                        
            except (pika.exceptions.ConnectionClosed, 
                   pika.exceptions.ChannelClosed,
                   pika.exceptions.StreamLostError) as e:
                logger.error(f"RabbitMQ connection error: {e}, reconnecting...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error in consume_messages: {e}")
                time.sleep(5)

    def start_rabbitmq(self):
        """Start RabbitMQ consumer thread"""
        self.running = True
        self.rabbitmq_consumer_thread = threading.Thread(target=self.consume_messages)
        self.rabbitmq_consumer_thread.daemon = True
        self.rabbitmq_consumer_thread.start()
        logger.info(f"RabbitMQ consumer started for {self.device_id}")

    def notify_status(self, status: str, chat_id: str, platform: str, username: str, bot_token: str):
        message = {
            "device_status": status,
            "device_id": self.device_id,
            "chat_id": chat_id,
            "platform": platform,
            "username": username,
            "bot_token": bot_token
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not self.rabbitmq_connection or self.rabbitmq_connection.is_closed:
                    logger.info(f"RabbitMQ connection closed, reconnecting (attempt {attempt + 1}/{max_retries})...")
                    if not self.setup_rabbitmq_connection():
                        time.sleep(2)
                        continue
                
                if platform == "line":
                    queue_name = config.RABBITMQ_LINE_QUEUE
                elif platform == "telegram":
                    queue_name = config.RABBITMQ_TELEGRAM_QUEUE
                else:
                    logger.error(f"Unsupported platform: {platform}")
                    return
                
                self.rabbitmq_channel.queue_declare(queue=queue_name, durable=True)
                self.rabbitmq_channel.basic_publish(
                    exchange='',
                    routing_key=queue_name,
                    body=json.dumps(message),
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                    )
                )
                logger.info(f"Status update sent to {queue_name} for device_id: {self.device_id}, status: {status}")
                break
            except (pika.exceptions.StreamLostError, pika.exceptions.ConnectionClosed, 
                    pika.exceptions.ChannelClosed, pika.exceptions.ChannelClosedByBroker, 
                    ConnectionResetError, requests.RequestException) as e:
                logger.error(f"Failed to send status update (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    logger.error("Max retries reached, giving up")

    def handle_enable(self, payload):
        chat_id = payload.get("chat_id")
        platform = payload.get("platform", "telegram")
        username = payload.get("username", "User")
        bot_token = payload.get("bot_token", "")
        device_id = payload.get("device_id")
        
        if device_id != self.device_id:
            logger.error(f"Invalid device_id in payload: {device_id}, expected {self.device_id}")
            return
        
        try:
            signature = generate_signature(chat_id)
            if not signature["success"]:
                logger.error(f"Signature generation failed: {signature['error']}")
                return
            
            device_config = config.load_device_config()
            url = f"{device_config['raspberry_pi']['url']}/Pi/{device_id}/Enable"
            
            data = {
                "device_id": self.device_id,
                "chat_id": chat_id,
                "timestamp": signature["timestamp"],
                "signature": signature["signature"],
                "username": username,
                "bot_token": bot_token
            }
            
            logger.info(f"Sending enable request to {url}")
            response = requests.post(
                url,
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                logger.info(f"Enable request succeeded for device_id: {self.device_id}")
                self.notify_status("on", chat_id, platform, username, bot_token)
            else:
                logger.error(f"Enable request failed: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Error calling enable API: {e}")

    def handle_disable(self, payload):
        chat_id = payload.get("chat_id")
        platform = payload.get("platform", "telegram")
        username = payload.get("username", "User")
        bot_token = payload.get("bot_token", "")
        device_id = payload.get("device_id")
        
        if device_id != self.device_id:
            logger.error(f"Invalid device_id in payload: {device_id}, expected {self.device_id}")
            return
        
        try:
            signature = generate_signature(chat_id)
            if not signature["success"]:
                logger.error(f"Signature generation failed: {signature['error']}")
                return
            
            device_config = config.load_device_config()
            url = f"{device_config['raspberry_pi']['url']}/Pi/{device_id}/Disable"
            
            data = {
                "device_id": self.device_id,
                "chat_id": chat_id,
                "timestamp": signature["timestamp"],
                "signature": signature["signature"],
                "username": username,
                "bot_token": bot_token
            }
            
            logger.info(f"Sending disable request to {url}")
            response = requests.post(
                url,
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                logger.info(f"Disable request succeeded for device_id: {self.device_id}")
                self.notify_status("off", chat_id, platform, username, bot_token)
            else:
                logger.error(f"Disable request failed: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Error calling disable API: {e}")

    def handle_get_status(self, payload):
        chat_id = payload.get("chat_id")
        platform = payload.get("platform", "telegram")
        username = payload.get("username", "User")
        bot_token = payload.get("bot_token", "")
        device_id = payload.get("device_id")
        
        if device_id != self.device_id:
            logger.error(f"Invalid device_id in payload: {device_id}, expected {self.device_id}")
            return
        
        try:
            signature = generate_signature(chat_id)
            if not signature["success"]:
                logger.error(f"Signature generation failed: {signature['error']}")
                return
            
            device_config = config.load_device_config()
            url = f"{device_config['raspberry_pi']['url']}/Pi/{device_id}/GetStatus"
            
            data = {
                "device_id": self.device_id,
                "chat_id": chat_id,
                "timestamp": signature["timestamp"],
                "signature": signature["signature"],
                "username": username,
                "bot_token": bot_token
            }
            
            logger.info(f"Sending get_status request to {url}")
            response = requests.post(
                url,
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                status = response.json().get("state", "unknown")
                logger.info(f"GetStatus request succeeded: {status}")
                self.notify_status(status, chat_id, platform, username, bot_token)
            else:
                logger.error(f"GetStatus request failed: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Error calling GetStatus API: {e}")

    def stop(self):
        """Stop RabbitMQ consumer"""
        self.running = False
        try:
            if self.rabbitmq_connection and not self.rabbitmq_connection.is_closed:
                self.rabbitmq_connection.close()
            logger.info("RabbitMQ connection closed")
        except Exception as e:
            logger.error(f"Error stopping RabbitMQ: {e}")

pi_device = RaspberryPiDevice("LivingRoomLight", "raspberrypi_light_001")

@app.route('/Pi/<device_id>/Enable', methods=['GET', 'POST'])
def api_enable(device_id):
    if not device_id or device_id != pi_device.device_id:
        logger.error(f"Invalid device ID: {device_id}, expected {pi_device.device_id}")
        return jsonify({"status": "error", "message": f"Invalid device ID, expected {pi_device.device_id}"}), 400
    
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
    
    try:
        device_config = config.load_device_config()
        url = f"{device_config['raspberry_pi']['url']}/Pi/{device_id}/Enable"
        logger.info(f"Sending enable API request to {url}")
        
        if request.method == 'POST':
            response = requests.post(
                url,
                json={
                    "device_id": device_id,
                    "chat_id": chat_id,
                    "timestamp": timestamp,
                    "signature": signature_b64,
                    "username": username,
                    "bot_token": bot_token
                },
                timeout=5
            )
        else:
            response = requests.get(
                url,
                params={
                    "device_id": device_id,
                    "chat_id": chat_id,
                    "timestamp": timestamp,
                    "signature": signature_b64,
                    "username": username,
                    "bot_token": bot_token
                },
                timeout=5
            )
            
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error in enable API: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/Pi/<device_id>/Disable', methods=['GET', 'POST'])
def api_disable(device_id):
    if not device_id or device_id != pi_device.device_id:
        logger.error(f"Invalid device ID: {device_id}, expected {pi_device.device_id}")
        return jsonify({"status": "error", "message": f"Invalid device ID, expected {pi_device.device_id}"}), 400
    
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
    
    try:
        device_config = config.load_device_config()
        url = f"{device_config['raspberry_pi']['url']}/Pi/{device_id}/Disable"
        logger.info(f"Sending disable API request to {url}")
        
        if request.method == 'POST':
            response = requests.post(
                url,
                json={
                    "device_id": device_id,
                    "chat_id": chat_id,
                    "timestamp": timestamp,
                    "signature": signature_b64,
                    "username": username,
                    "bot_token": bot_token
                },
                timeout=5
            )
        else:
            response = requests.get(
                url,
                params={
                    "device_id": device_id,
                    "chat_id": chat_id,
                    "timestamp": timestamp,
                    "signature": signature_b64,
                    "username": username,
                    "bot_token": bot_token
                },
                timeout=5
            )
            
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error in disable API: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/Pi/<device_id>/GetStatus', methods=['GET', 'POST'])
def api_get_status(device_id):
    if not device_id or device_id != pi_device.device_id:
        logger.error(f"Invalid device ID: {device_id}, expected {pi_device.device_id}")
        return jsonify({"status": "error", "message": f"Invalid device ID, expected {pi_device.device_id}"}), 400
    
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
    
    try:
        device_config = config.load_device_config()
        url = f"{device_config['raspberry_pi']['url']}/Pi/{device_id}/GetStatus"
        logger.info(f"Sending get_status API request to {url}")
        
        if request.method == 'POST':
            response = requests.post(
                url,
                json={
                    "device_id": device_id,
                    "chat_id": chat_id,
                    "timestamp": timestamp,
                    "signature": signature_b64,
                    "username": username,
                    "bot_token": bot_token
                },
                timeout=5
            )
        else:
            response = requests.get(
                url,
                params={
                    "device_id": device_id,
                    "chat_id": chat_id,
                    "timestamp": timestamp,
                    "signature": signature_b64,
                    "username": username,
                    "bot_token": bot_token
                },
                timeout=5
            )
            
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error in get_status API: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/signature', methods=['POST'])
def api_signature():
    data = request.get_json()
    logger.info(f"Received signature request")
    return jsonify({"status": "received"}), 200

SWAGGER_URL = '/swagger'
API_URL = '/static/openapi.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': "Raspberry Pi IoT Device"}
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

@app.route('/static/<path:path>')
def serve_swagger(path):
    return send_from_directory('static', path)

if __name__ == "__main__":
    try:
        load_private_key()
        if not os.path.exists('static'):
            os.makedirs('static')
        logger.info(f"Starting Flask app on port {config.RASPBERRY_PI_API_PORT}")
        app.run(host="0.0.0.0", port=config.RASPBERRY_PI_API_PORT, debug=False)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        pi_device.stop()