
FROM python:3.10-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN opentelemetry-bootstrap -a install

# 複製必要文件
COPY config.py .
COPY raspberrypi_iot_device.py .
COPY openapi.yaml .


# 設置端口
EXPOSE 5003

# 定義環境變數 (localhost皆須改成service name)
ENV IOTQUEUE_HOST='localhost'
ENV IOTQUEUE_PORT=1883
ENV RABBITMQ_HOST='localhost'
ENV RABBITMQ_PORT=5672

# OpenTelementry 環境變數
ENV OTEL_SERVICE_NAME=iot-raspberrypi
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy.monitoring.svc.cluster.local:4318
ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf  
ENV OTEL_EXPORTER_OTLP_INSECURE=true
ENV OTEL_METRICS_EXPORTER=none


# 啟動命令 & auto instrumentation
CMD ["opentelemetry-instrument", "python", "raspberrypi_iot_device.py"]