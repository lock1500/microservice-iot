
FROM python:3.10-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製必要文件
COPY config.py .
COPY esp32_iot_device.py .
COPY openapi.yaml .


# 設置端口
EXPOSE 5002

# 定義環境變數 (localhost皆須改成service name)
ENV IOTQUEUE_HOST='localhost'
ENV IOTQUEUE_PORT=1883
ENV RABBITMQ_HOST='localhost'
ENV RABBITMQ_PORT=5672


# 啟動命令
CMD ["python", "esp32_iot_device.py"]