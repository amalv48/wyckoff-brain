FROM python:3.11-slim

WORKDIR /app

COPY webapp/backend/requirements.txt ./webapp/backend/requirements.txt
RUN pip install --no-cache-dir -r webapp/backend/requirements.txt

COPY . .

EXPOSE 8000

WORKDIR /app/webapp/backend
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
