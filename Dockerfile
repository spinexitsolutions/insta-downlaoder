FROM python:3.12-slim

# ffmpeg merges Instagram videos that come as separate video/audio streams.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    # Chromium for the automatic Instagram login (see browser_login.py)
    && playwright install --with-deps chromium
COPY . .

# One worker: the Instagram login uses one browser profile and one saved session,
# so a second worker would fight over them. Threads handle concurrent visitors.
ENV PORT=8000
EXPOSE 8000
CMD gunicorn -w 1 --threads 16 -t 180 -b 0.0.0.0:$PORT app:app
