FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir psycopg2-binary

COPY app.py .

CMD ["python", "app.py"]
