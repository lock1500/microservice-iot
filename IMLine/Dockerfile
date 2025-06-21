FROM python:3.10-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製必要文件
COPY config.py .
COPY IMLine.py .
COPY IMQbroker.py .
COPY IoTQbroker.py .
COPY openapi.yaml .

# 設置端口
EXPOSE 5001

# 定義環境變數
ENV IOTQUEUE_HOST='localhost'
ENV IOTQUEUE_PORT=1883
ENV RABBITMQ_HOST='localhost'
ENV RABBITMQ_PORT=5672


# 啟動命令
CMD ["python", "IMLine.py"]