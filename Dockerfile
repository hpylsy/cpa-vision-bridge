FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VISION_BRIDGE_CONFIG=/app/config.yaml

WORKDIR /app

COPY pyproject.toml requirements.txt /app/
COPY src /app/src

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .

EXPOSE 8320

CMD ["python", "-m", "vision_bridge"]
