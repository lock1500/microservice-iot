
FROM python:3.10-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN opentelemetry-bootstrap -a install

# 複製必要文件
COPY config.py .
COPY IMTelegram.py .
COPY IMQbroker.py .
COPY IoTQbroker.py .
COPY openapi.yaml .


# 設置端口
EXPOSE 5000

# 定義環境變數
ENV IOTQUEUE_HOST='localhost'
ENV IOTQUEUE_PORT=1883
ENV RABBITMQ_HOST='localhost'
ENV RABBITMQ_PORT=5672

# OpenTelementry 環境變數
ENV OTEL_SERVICE_NAME=im-telegram
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy.monitoring.svc.cluster.local:4318
ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf  
ENV OTEL_METRICS_EXPORTER=none
ENV OTEL_EXPORTER_OTLP_INSECURE=true

# 啟動命令 & auto instrumentation
CMD ["opentelemetry-instrument", "python", "IMTelegram.py"]