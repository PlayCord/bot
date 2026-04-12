FROM python:3.12-slim

# Create app dir
WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Install system deps, fonts and build tools needed for some Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libcairo2 \
        fontconfig \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-color-emoji \
        build-essential \
        libpq-dev \
        libraqm-dev \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f -v || true

# Install Python dependencies. Keep this layer above copying source so rebuilds are faster
RUN pip install --no-cache-dir \
    ruamel.yaml \
    discord \
    cairosvg \
    svg.py \
    trueskill \
    mpmath \
    emoji \
    psutil \
    "psycopg[binary,pool]" \
    matplotlib

# Copy project files (can be overridden by docker-compose bind mount in dev)
COPY . /app

CMD ["python", "bot.py"]

