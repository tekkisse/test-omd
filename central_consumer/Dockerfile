FROM python:3.12-slim

WORKDIR /app
COPY central_consumer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY central_consumer/ ./central_consumer/

ENV PYTHONPATH=/app

CMD ["python", "-m", "central_consumer.main"]
