FROM python:3.12-slim

# ffmpeg merges Instagram videos that come as separate video/audio streams.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=8000
EXPOSE 8000
CMD gunicorn -w 2 --threads 4 -t 120 -b 0.0.0.0:$PORT app:app
