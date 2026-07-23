# Multi-stage build: a builder stage with compilers available (some of
# chromadb's dependencies need to build native extensions on platforms
# without a prebuilt wheel), and a slim final stage that only carries the
# installed packages and application code — not the compiler toolchain.

FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# --user installs into /root/.local, a self-contained tree that's cheap
# to copy wholesale into the final stage without dragging along apt
# package lists or pip's build caches.
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Final stage ----

FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY app/ app/
COPY scripts/ scripts/
COPY wsgi.py docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Ships in the image so the entrypoint's first-run bootstrap has notes to
# chunk even without a mounted data volume (e.g. a real deployment with
# no host filesystem to mount from). data/chroma and data/processed are
# excluded via .dockerignore — regenerated fresh, or provided by a mounted
# volume in docker-compose for local dev.
COPY data/raw_notes/ data/raw_notes/

EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
