FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        libcairo2 \
        fontconfig \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-color-emoji \
        build-essential \
        libpq-dev \
        libraqm-dev  \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f -v || true

COPY pyproject.toml README.md /app/
COPY playcord /app/playcord
RUN pip install --no-cache-dir ".[dev]"

CMD ["python", "-m", "playcord.presentation.bot"]

