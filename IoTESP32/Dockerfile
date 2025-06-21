
FROM python:3.10-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製必要文件
COPY config.py .
COPY esp32_iot_device.py .

# 建立 static 目錄（確保存在）
RUN mkdir -p static
# 複製 openapi.yaml 到 static 目錄中（供 Swagger UI 使用）
COPY openapi.yaml ./static/


# 設置端口
EXPOSE 5002

# 定義環境變數 (localhost皆須改成service name)
ENV IOTQUEUE_HOST='localhost'
ENV IOTQUEUE_PORT=1883
ENV RABBITMQ_HOST='localhost'
ENV RABBITMQ_PORT=5672


# 啟動命令
CMD ["python", "esp32_iot_device.py"]