# microservice
IoT Messaging System
這是一個基於 Python 的 IoT 消息系統，通過 LINE 和 Telegram 與虛擬設備進行交互。
系統使用 MQTT（Mosquitto）進行設備通信，並使用 RabbitMQ 進行消息隊列管理。

swagger ui能進去且顯示 openapi
device_conf 用 configmap掛載，之後要用mount
平台會搶訊息，但本地測試不會 (以解決，不同平台使用不同queue)

待新增功能:
綁定使用者，設置使用者名稱，傳送裝置更動訊息給所有綁定使用者
將電器種類分為light和fan
如何依據chatid回傳訊息
讀取iot device的ip port 而非寫死

