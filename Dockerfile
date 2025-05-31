FROM python:3.11-slim

WORKDIR /app
COPY test.py .

RUN pip install flask

EXPOSE 5030
CMD ["python", "test.py"]
