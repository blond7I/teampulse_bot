FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite-файл должен переживать рестарты контейнера — Railway даёт volume под /app/data
ENV DB_PATH=/app/data/teampulse.db
RUN mkdir -p /app/data

CMD ["python", "bot.py"]
