FROM python:3.12-slim

WORKDIR /app
COPY webhook_receiver/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY webhook_receiver/ ./webhook_receiver/

ENV PYTHONPATH=/app

CMD ["python", "-m", "webhook_receiver.main"]
