FROM python:3.12-slim

# sounddevice loads libportaudio at import time (server.py imports src.stt),
# so the API won't boot without it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default command: the API. The web (Streamlit) service overrides this.
EXPOSE 8000 8501 8502
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
