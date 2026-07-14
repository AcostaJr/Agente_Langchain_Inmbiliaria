# Pull base image
FROM python:3.11-slim

# cd /app
WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["uvicorn", "main_chatwoot:app", "--host", "0.0.0.0", "--port", "8000"]