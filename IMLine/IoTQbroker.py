# IoTQbroker.py
import paho.mqtt.client as mqtt
import json
import re
import logging
import config
import time
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global client pool, used to reuse MQTT clients by chat_id
client_pool = {}

# Global bindings dictionary, used to store user-device binding relationships
bindings = {}  # Format: {device_id: set(chat_id)}

class Device:
    def __init__(self, name: str, device_id: str = config.DEVICE_ID, platform: str = "unknown", chat_id: str = None):
        self.name = name
        self.device_id = device_id
        self.chat_id = chat_id
        self.platform = platform
        self.group_id = None  # Initialize group ID
        self.group_members = set()  # Initialize group members set
        self.manufacturer = "raspberrypi" if "raspberrypi" in device_id else "esp32"
        self.device_type = "light" if "light" in device_id else "fan"
        logger.info(f"Initializing device: device_id={device_id}, manufacturer={self.manufacturer}, device_type={self.device_type}")
        try:
            self.message_api = MessageAPI(config.IOTQUEUE_HOST, config.IOTQUEUE_PORT, platform, device_id, chat_id)
        except Exception as e:
            logger.error(f"Failed to initialize MessageAPI for device {device_id}: {e}")
            raise

    def bind_user(self, chat_id: str, platform: str) -> bool:
        try:
            if self.device_id not in bindings:
                bindings[self.device_id] = set()
            bindings[self.device_id].add(chat_id)
            
            if self.group_id is None:
                # Device is not bound to any group, set as group owner
                self.group_id = chat_id
                self.group_members.add(chat_id)
                logger.info(f"User chat_id={chat_id} created group for device {self.device_id}")
            else:
                # Device already has a group, add new member and notify others
                if chat_id not in self.group_members:
                    self.group_members.add(chat_id)
                    logger.info(f"User chat_id={chat_id} joined group for device {self.device_id}")
                    from IMQbroker import send_message
                    for member in self.group_members:
                        if member != chat_id:
                            send_message(member, f"User {chat_id} has joined the group for device {self.device_id}", platform)
            return True
        except Exception as e:
            logger.error(f"Failed to bind user chat_id={chat_id} to device {self.device_id}: {e}")
            return False

    def get_bound_users(self) -> set:
        try:
            bound_users = bindings.get(self.device_id, set())
            logger.info(f"Retrieved bound users for device {self.device_id}: {bound_users}")
            return bound_users
        except Exception as e:
            logger.error(f"Failed to retrieve bound users for device {self.device_id}: {e}")
            return set()

    def enable(self, chat_id: str = None, platform: str = "telegram", user_id: str = None, username: str = None, bot_token: str = None) -> bool:
        topic = f"{self.manufacturer}/{self.device_type}/enable"
        message = {
            "command": "on",
            "chat_id": chat_id,
            "platform": platform,
            "device_id": self.device_id,
            "user_id": user_id,
            "username": username,
            "bot_token": bot_token or (config.TELEGRAM_BOT_TOKEN if platform == "telegram" else config.LINE_ACCESS_TOKEN)
        }
        try:
            logger.info(f"Sending enable command: topic={topic}, message={json.dumps(message)}")
            return self.message_api.send_message(topic, message)
        except Exception as e:
            logger.error(f"Failed to enable device {self.device_id} on topic {topic}: {e}")
            return False

    def disable(self, chat_id: str = None, platform: str = "telegram", user_id: str = None, username: str = None, bot_token: str = None) -> bool:
        topic = f"{self.manufacturer}/{self.device_type}/disable"
        message = {
            "command": "off",
            "chat_id": chat_id,
            "platform": platform,
            "device_id": self.device_id,
            "user_id": user_id,
            "username": username,
            "bot_token": bot_token or (config.TELEGRAM_BOT_TOKEN if platform == "telegram" else config.LINE_ACCESS_TOKEN)
        }
        try:
            logger.info(f"Sending disable command: topic={topic}, message={json.dumps(message)}")
            return self.message_api.send_message(topic, message)
        except Exception as e:
            logger.error(f"Failed to disable device {self.device_id} on topic {topic}: {e}")
            return False

    def get_status(self, chat_id: str = None, platform: str = "telegram", user_id: str = None, username: str = None, bot_token: str = None) -> bool:
        topic = f"{self.manufacturer}/{self.device_type}/get_status"
        message = {
            "command": "get_status",
            "chat_id": chat_id,
            "platform": platform,
            "device_id": self.device_id,
            "user_id": user_id,
            "username": username,
            "bot_token": bot_token or (config.TELEGRAM_BOT_TOKEN if platform == "telegram" else config.LINE_ACCESS_TOKEN)
        }
        try:
            logger.info(f"Sending get status command: topic={topic}, message={json.dumps(message)}")
            return self.message_api.send_message(topic, message)
        except Exception as e:
            logger.error(f"Failed to get status for device {self.device_id} on topic {topic}: {e}")
            return False

class MessageAPI:
    def __init__(self, broker_host: str, broker_port: int, platform: str, device_id: str, chat_id: str):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.device_id = device_id
        self.platform = platform
        self.chat_id = chat_id or "default"
        if self.chat_id in client_pool:
            self.client = client_pool[self.chat_id]
            logger.info(f"Reusing MQTT client, chat_id={self.chat_id}")
        else:
            try:
                client_id = f"iotq_broker_{platform}_{self.chat_id}_{str(uuid.uuid4())[:8]}"
                self.client = mqtt.Client(client_id=client_id)
                self.client.on_connect = self.on_connect
                self.client.on_disconnect = self.on_disconnect
                self.client.reconnect_delay_set(min_delay=1, max_delay=120)
                client_pool[self.chat_id] = self.client
                logger.info(f"Created new MQTT client, chat_id={self.chat_id}, client_id={client_id}")
                self.connect()
            except Exception as e:
                logger.error(f"Failed to create MQTT client, chat_id={self.chat_id}: {e}")
                raise

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Client {client._client_id} connected to IOTQueue broker")
        else:
            logger.error(f"Client {client._client_id} failed to connect to IOTQueue broker, return code: {rc}")

    def on_disconnect(self, client, userdata, rc):
        logger.warning(f"Client {client._client_id} disconnected from IOTQueue broker, attempting to reconnect...")

    def connect(self):
        max_retries = 5
        retry_count = 0
        while retry_count < max_retries:
            try:
                self.client.connect(self.broker_host, self.broker_port)
                self.client.loop_start()
                logger.info(f"Client {self.client._client_id} connected to MQTT broker")
                return
            except Exception as e:
                retry_count += 1
                logger.error(f"Client {self.client._client_id} failed to connect to MQTT broker (attempt {retry_count}/{max_retries}): {e}")
                if retry_count == max_retries:
                    raise
                time.sleep(5)

    def send_message(self, topic: str, message: dict) -> bool:
        try:
            self.client.publish(topic, json.dumps(message))
            logger.info(f"IOTQueue message sent successfully: topic={topic}, message={json.dumps(message)}")
            return True
        except Exception as e:
            logger.error(f"Failed to send IOTQueue message: topic={topic}, error={e}")
            return False

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info(f"Client {self.client._client_id} stopped")
        except Exception as e:
            logger.error(f"Failed to stop MQTT client {self.client._client_id}: {e}")

def IoTParse_Message(message_text: str, device: Device, chat_id: str, platform: str = "telegram", user_id: str = None, username: str = None) -> dict:
    message_text = message_text.lower().strip()
    logger.info(f"Parsing IoT message: {message_text}, username={username}, platform={platform}, user_id={user_id}, chat_id={chat_id}")
    try:
        if not username:
            username = "User"
            logger.warning(f"No username provided, using default: {username}, chat_id={chat_id}")
        if not user_id:
            user_id = "Unknown"
            logger.warning(f"No user_id provided, using default: {user_id}, chat_id={chat_id}")
        bot_token = config.TELEGRAM_BOT_TOKEN if platform == "telegram" else config.LINE_ACCESS_TOKEN
        from IMQbroker import send_message

        if message_text in ["hi", "hello", "/start"]:
            help_text = (
                f"Hi, {username}\n"
                "This is an IoT control bot\n"
                "Use the following commands:\n"
                "turn on {device_id} to enable device\n"
                "turn off {device_id} to disable device\n"
                "get status {device_id} to get device status\n"
                "/Bind {device_id} to bind to device"
            )
            send_message(chat_id, help_text, platform, user_id=user_id, username=username)
            return {"success": True, "action": "Help"}

        bind_match = re.match(r"^/bind\s+([\w_]+)$", message_text)
        if bind_match:
            device_id = bind_match.group(1)
            if device_id not in config.SUPPORTED_DEVICES:
                send_message(chat_id, f"Invalid device ID: {device_id}. Available devices: {', '.join(config.SUPPORTED_DEVICES)}", platform, user_id=user_id, username=username)
                return {"success": False, "message": "Invalid device ID"}
            target_device = Device(device.name, device_id=device_id, platform=platform, chat_id=chat_id)
            if target_device.bind_user(chat_id, platform):
                send_message(chat_id, f"Successfully bound to device {device_id}", platform, user_id=user_id, username=username)
                return {"success": True, "action": "Bind", "device_id": device_id}
            else:
                send_message(chat_id, f"Failed to bind to device {device_id}", platform, user_id=user_id, username=username)
                return {"success": False, "message": "Failed to bind to device"}

        enable_match = re.match(r"^(turn on|/enable)(\s+([\w_]+))?$", message_text)
        disable_match = re.match(r"^(turn off|/disable)(\s+([\w_]+))?$", message_text)
        status_match = re.match(r"^(get status|/status)(\s+([\w_]+))?$", message_text)

        device_id = None
        if enable_match and enable_match.group(3):
            device_id = enable_match.group(3)
        elif disable_match and disable_match.group(3):
            device_id = disable_match.group(3)
        elif status_match and status_match.group(3):
            device_id = status_match.group(3)
        else:
            device_id = device.device_id

        if device_id not in config.SUPPORTED_DEVICES:
            send_message(chat_id, f"Invalid device ID: {device_id}. Available devices: {', '.join(config.SUPPORTED_DEVICES)}", platform, user_id=user_id, username=username)
            return {"success": False, "message": "Invalid device ID"}

        target_device = Device(device.name, device_id=device_id, platform=platform, chat_id=chat_id)

        if enable_match:
            if target_device.enable(chat_id, platform, user_id, username, bot_token):
                send_message(chat_id, f"Command received: Enable {device_id}", platform, user_id=user_id, username=username)
                return {"success": True, "action": "Enable", "device_id": device_id}
            else:
                send_message(chat_id, f"Failed to enable device {device_id}", platform, user_id=user_id, username=username)
                return {"success": False, "message": "Failed to enable device"}
        elif disable_match:
            if target_device.disable(chat_id, platform, user_id, username, bot_token):
                send_message(chat_id, f"Command received: Disable {device_id}", platform, user_id=user_id, username=username)
                return {"success": True, "action": "Disable", "device_id": device_id}
            else:
                send_message(chat_id, f"Failed to disable device {device_id}", platform, user_id=user_id, username=username)
                return {"success": False, "message": "Failed to disable device"}
        elif status_match:
            if target_device.get_status(chat_id, platform, user_id, username, bot_token):
                send_message(chat_id, f"Command received: Get status of {device_id}", platform, user_id=user_id, username=username)
                return {"success": True, "action": "GetStatus", "device_id": device_id}
            else:
                send_message(chat_id, f"Failed to get status of device {device_id}", platform, user_id=user_id, username=username)
                return {"success": False, "message": "Failed to get device status"}
        else:
            send_message(chat_id, "Invalid command. Please use /start to view help.", platform, user_id=user_id, username=username)
            return {"success": False, "message": "Invalid command"}
    except Exception as e:
        logger.error(f"Error parsing message '{message_text}', username={username}, user_id={user_id}, chat_id={chat_id}: {e}", exc_info=True)
        send_message(chat_id, "An error occurred while processing your command. Please try again.", platform, user_id=user_id, username=username)
        return {"success": False, "message": "Error processing command"}