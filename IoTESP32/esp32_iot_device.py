# esp32_iot_device.py
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
        logging.FileHandler('esp32.log', mode='a')
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
            logger.error("Private key file 'ecdsa_private.pem' not found")
            return False
        with open("/app/keys/ecdsa_private.pem", "rt") as f:
            private_key = ECC.import_key(f.read())
        logger.info("Private key loaded successfully (私鑰載入成功)")
        return True
    except Exception as e:
        logger.error(f"Failed to load private key (載入私鑰失敗): {e}")
        return False

def generate_signature(chat_id: str):
    if not private_key or DSS is None or SHA256 is None:
        logger.error("No private key or pycryptodome not available (無私鑰或密碼庫不可用)")
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
        logger.info(f"Generated signature for chat_id (為 chat_id 生成簽章): {chat_id}")
        return result
    except Exception as e:
        logger.error(f"Error generating signature (生成簽章錯誤): {e}")
        return {"success": False, "error": str(e)}

class ESP32Device:
    def __init__(self, name: str, device_id: str):
        self.name = name
        self.device_id = device_id
        self.manufacturer = "esp32"
        self.device_type = "light" if "light" in device_id else "fan"
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        self.rabbitmq_consumer_thread = None
        self.running = False
        self.start_rabbitmq()

    def setup_rabbitmq_connection(self):
        # 設置 RabbitMQ 連線
        try:
            parameters = pika.ConnectionParameters(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                heartbeat=30,
                blocked_connection_timeout=60
            )
            self.rabbitmq_connection = pika.BlockingConnection(parameters)
            self.rabbitmq_channel = self.rabbitmq_connection.channel()
            logger.info("RabbitMQ BlockingConnection established successfully (RabbitMQ 連線成功)")
            return True
        except Exception as e:
            logger.error(f"Failed to establish RabbitMQ BlockingConnection (建立 RabbitMQ 連線失敗): {e}")
            return False

    def on_rabbitmq_message(self, channel, method, properties, body):
        # 處理 RabbitMQ 訊息
        try:
            payload = json.loads(body.decode('utf-8'))
            logger.info(f"Received RabbitMQ message (收到 RabbitMQ 訊息): {payload}")
            
            command = payload.get("command")
            if command == "on":
                self.handle_enable(payload)
            elif command == "off":
                self.handle_disable(payload)
            elif command == "get_status":
                self.handle_get_status(payload)
                
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in RabbitMQ message (RabbitMQ 訊息中 JSON 無效): {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Error processing RabbitMQ message (處理 RabbitMQ 訊息錯誤): {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def consume_messages(self):
        # 從 RabbitMQ 隊列消費訊息
        while self.running:
            try:
                if not self.rabbitmq_connection or self.rabbitmq_connection.is_closed:
                    logger.info("RabbitMQ connection closed, reconnecting (RabbitMQ 連線已關閉，正在重新連線)...")
                    if not self.setup_rabbitmq_connection():
                        time.sleep(5)
                        continue

                queue_name = "iot_esp32_queue"
                self.rabbitmq_channel.queue_declare(queue=queue_name, durable=True)
                self.rabbitmq_channel.basic_qos(prefetch_count=1)
                
                logger.info(f"Starting to consume messages from {queue_name} (開始消費訊息)")
                
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
                logger.error(f"RabbitMQ connection error (RabbitMQ 連線錯誤): {e}, reconnecting...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error in consume_messages (consume_messages 中發生意外錯誤): {e}")
                time.sleep(5)

    def start_rabbitmq(self):
        # 啟動 RabbitMQ 消費者線程
        self.running = True
        self.rabbitmq_consumer_thread = threading.Thread(target=self.consume_messages)
        self.rabbitmq_consumer_thread.daemon = True
        self.rabbitmq_consumer_thread.start()
        logger.info(f"RabbitMQ consumer started for {self.device_id} (RabbitMQ 消費者已啟動)")

    def notify_status(self, status: str, chat_id: str, platform: str, username: str, bot_token: str):
        # 發送狀態通知給 IM 系統
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
                    logger.error(f"Unsupported platform (不支援的平台): {platform}")
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
                logger.info(f"Status update sent to {queue_name} for device_id: {self.device_id}, status: {status} (狀態更新已發送)")
                break
            except (pika.exceptions.StreamLostError, pika.exceptions.ConnectionClosed, 
                    pika.exceptions.ChannelClosed, pika.exceptions.ChannelClosedByBroker, 
                    ConnectionResetError, requests.RequestException) as e:
                logger.error(f"Failed to send status update (發送狀態更新失敗) (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    logger.error("Max retries reached, giving up (達到最大重試次數)")

    def handle_enable(self, payload):
        chat_id = payload.get("chat_id")
        platform = payload.get("platform", "telegram")
        username = payload.get("username", "User")
        bot_token = payload.get("bot_token", "")
        device_id = payload.get("device_id")
        
        if device_id != self.device_id:
            logger.error(f"Invalid device_id in payload (payload 中 device_id 無效): {device_id}, expected {self.device_id}")
            return
        
        try:
            signature = generate_signature(chat_id)
            if not signature["success"]:
                logger.error(f"Signature generation failed (簽章生成失敗): {signature['error']}")
                return
            
            device_config = config.load_device_config()
            url = f"{device_config['esp32']['url']}/ESP32/{device_id}/Enable"
            
            # --- 修正: 轉換為 GET 請求並使用 params 傳遞資料 ---
            data = {
                "device_id": self.device_id,
                "chat_id": chat_id,
                "timestamp": signature["timestamp"],
                "signature": signature["signature"],
                "username": username,
                "bot_token": bot_token
            }
            
            logger.info(f"Sending enable GET request to {url} (發送啟用 GET 請求)")
            response = requests.get(
                url,
                params=data, # 使用 params 傳遞資料，作為 URL 查詢字串
                timeout=5
            )
            
            if response.status_code == 200:
                logger.info(f"Enable request succeeded for device_id (啟用請求成功): {self.device_id}")
                self.notify_status("on", chat_id, platform, username, bot_token)
            else:
                logger.error(f"Enable request failed (啟用請求失敗): {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Error calling enable API (呼叫啟用 API 錯誤): {e}")

    def handle_disable(self, payload):
        chat_id = payload.get("chat_id")
        platform = payload.get("platform", "telegram")
        username = payload.get("username", "User")
        bot_token = payload.get("bot_token", "")
        device_id = payload.get("device_id")
        
        if device_id != self.device_id:
            logger.error(f"Invalid device_id in payload (payload 中 device_id 無效): {device_id}, expected {self.device_id}")
            return
        
        try:
            signature = generate_signature(chat_id)
            if not signature["success"]:
                logger.error(f"Signature generation failed (簽章生成失敗): {signature['error']}")
                return
            
            device_config = config.load_device_config()
            url = f"{device_config['esp32']['url']}/ESP32/{device_id}/Disable"
            
            # --- 修正: 轉換為 GET 請求並使用 params 傳遞資料 ---
            data = {
                "device_id": self.device_id,
                "chat_id": chat_id,
                "timestamp": signature["timestamp"],
                "signature": signature["signature"],
                "username": username,
                "bot_token": bot_token
            }
            
            logger.info(f"Sending disable GET request to {url} (發送停用 GET 請求)")
            response = requests.get(
                url,
                params=data, # 使用 params 傳遞資料，作為 URL 查詢字串
                timeout=5
            )
            
            if response.status_code == 200:
                logger.info(f"Disable request succeeded for device_id (停用請求成功): {self.device_id}")
                self.notify_status("off", chat_id, platform, username, bot_token)
            else:
                logger.error(f"Disable request failed (停用請求失敗): {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Error calling disable API (呼叫停用 API 錯誤): {e}")

    def handle_get_status(self, payload):
        chat_id = payload.get("chat_id")
        platform = payload.get("platform", "telegram")
        username = payload.get("username", "User")
        bot_token = payload.get("bot_token", "")
        device_id = payload.get("device_id")
        
        if device_id != self.device_id:
            logger.error(f"Invalid device_id in payload (payload 中 device_id 無效): {device_id}, expected {self.device_id}")
            return
        
        try:
            signature = generate_signature(chat_id)
            if not signature["success"]:
                logger.error(f"Signature generation failed (簽章生成失敗): {signature['error']}")
                return
            
            device_config = config.load_device_config()
            url = f"{device_config['esp32']['url']}/ESP32/{device_id}/GetStatus"
            
            # --- 修正: 轉換為 GET 請求並使用 params 傳遞資料 ---
            data = {
                "device_id": self.device_id,
                "chat_id": chat_id,
                "timestamp": signature["timestamp"],
                "signature": signature["signature"],
                "username": username,
                "bot_token": bot_token
            }
            
            logger.info(f"Sending get_status GET request to {url} (發送狀態查詢 GET 請求)")
            response = requests.get(
                url,
                params=data, # 使用 params 傳遞資料，作為 URL 查詢字串
                timeout=5
            )
            
            if response.status_code == 200:
                status = response.json().get("state", "unknown")
                logger.info(f"GetStatus request succeeded (狀態查詢請求成功): {status}")
                self.notify_status(status, chat_id, platform, username, bot_token)
            else:
                logger.error(f"GetStatus request failed (狀態查詢請求失敗): {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Error calling GetStatus API (呼叫狀態查詢 API 錯誤): {e}")

    def stop(self):
        # 停止 RabbitMQ 消費者
        self.running = False
        try:
            if self.rabbitmq_connection and not self.rabbitmq_connection.is_closed:
                self.rabbitmq_connection.close()
            logger.info("RabbitMQ connection closed (RabbitMQ 連線已關閉)")
        except Exception as e:
            logger.error(f"Error stopping RabbitMQ (停止 RabbitMQ 錯誤): {e}")

esp32_device = ESP32Device("LivingRoomLight", config.DEVICE_ID)

@app.route('/ESP32/<device_id>/Enable', methods=['GET', 'POST'])
def api_enable(device_id):
    # API 代理：將請求轉發給實際設備
    if not device_id or device_id != esp32_device.device_id:
        logger.error(f"Invalid device ID (無效的裝置 ID): {device_id}")
        return jsonify({"status": "error", "message": "Invalid device ID"}), 400
    
    if request.method == 'POST':
        # 註：此處應保持 POST JSON 解析，因為此端點可能被其他微服務呼叫
        data = request.get_json(silent=True) or {}
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
        
        # 由於設備現在只接受 GET，我們需要將 POST 數據轉換為 GET 參數
        params = data
        request_func = requests.get
        
    else: # GET 請求
        params = request.args
        chat_id = params.get('chat_id', "default")
        timestamp = params.get('timestamp')
        signature_b64 = params.get('signature')
        username = params.get('username', "User")
        bot_token = params.get('bot_token', "")
        request_func = requests.get
    
    try:
        device_config = config.load_device_config()
        url = f"{device_config['esp32']['url']}/ESP32/{device_id}/Enable"
        logger.info(f"Sending enable API request (發送啟用 API 請求) (GET) to {url}")
        
        response = request_func(
            url,
            params=params, # 使用 params 傳遞所有查詢字串參數
            timeout=5
        )
            
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error in enable API (啟用 API 錯誤): {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/ESP32/<device_id>/Disable', methods=['GET', 'POST'])
def api_disable(device_id):
    # API 代理：將請求轉發給實際設備
    if not device_id or device_id != esp32_device.device_id:
        logger.error(f"Invalid device ID (無效的裝置 ID): {device_id}")
        return jsonify({"status": "error", "message": "Invalid device ID"}), 400
    
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
        
        params = data
        request_func = requests.get
        
    else: # GET 請求
        params = request.args
        chat_id = params.get('chat_id', "default")
        timestamp = params.get('timestamp')
        signature_b64 = params.get('signature')
        username = params.get('username', "User")
        bot_token = params.get('bot_token', "")
        request_func = requests.get
    
    try:
        device_config = config.load_device_config()
        url = f"{device_config['esp32']['url']}/ESP32/{device_id}/Disable"
        logger.info(f"Sending disable API request (發送停用 API 請求) (GET) to {url}")
        
        response = request_func(
            url,
            params=params,
            timeout=5
        )
            
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error in disable API (停用 API 錯誤): {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/ESP32/<device_id>/GetStatus', methods=['GET', 'POST'])
def api_get_status(device_id):
    # API 代理：將請求轉發給實際設備
    if not device_id or device_id != esp32_device.device_id:
        logger.error(f"Invalid device ID (無效的裝置 ID): {device_id}")
        return jsonify({"status": "error", "message": "Invalid device ID"}), 400
    
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        chat_id = data.get('chat_id', "default")
        timestamp = data.get('timestamp')
        signature_b64 = data.get('signature')
        username = data.get('username', "User")
        bot_token = data.get('bot_token', "")
        
        params = data
        request_func = requests.get
    else: # GET 請求
        params = request.args
        chat_id = params.get('chat_id', "default")
        timestamp = params.get('timestamp')
        signature_b64 = params.get('signature')
        username = params.get('username', "User")
        bot_token = params.get('bot_token', "")
        request_func = requests.get
    
    try:
        device_config = config.load_device_config()
        url = f"{device_config['esp32']['url']}/ESP32/{device_id}/GetStatus"
        logger.info(f"Sending get_status API request (發送狀態查詢 API 請求) (GET) to {url}")
        
        response = request_func(
            url,
            params=params,
            timeout=5
        )
            
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error in get_status API (狀態查詢 API 錯誤): {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/signature', methods=['POST'])
def api_signature():
    data = request.get_json()
    logger.info(f"Received signature request (收到簽章請求)")
    return jsonify({"status": "received"}), 200

SWAGGER_URL = '/swagger'
API_URL = '/static/openapi.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': "ESP32 IoT Device (ESP32 IoT 裝置)"}
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
        logger.info(f"Starting Flask app on port {config.ESP32_API_PORT} (在埠號 {config.ESP32_API_PORT} 啟動 Flask 應用程式)")
        app.run(host="0.0.0.0", port=config.ESP32_API_PORT, debug=False)
    except KeyboardInterrupt:
        logger.info("Shutting down (正在關機)...")
    except Exception as e:
        logger.error(f"Fatal error (致命錯誤): {e}")
    finally:
        esp32_device.stop()
