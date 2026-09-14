# Woodcroft API. Multi-stage so the runtime image carries no build tooling.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user. A container process that is compromised should not
# also be root inside the container.
RUN useradd --create-home --uid 10001 woodcroft \
    && mkdir -p /app/media \
    && chown -R woodcroft:woodcroft /app
USER woodcroft

EXPOSE 8000

# Migrations run at start, then the app. The background worker is disabled here
# because it must run as exactly one process; see docker-compose for a single
# dedicated worker replica.
# One worker: the rate limiter keeps its buckets in process memory, so multiple
# workers would each enforce the limit separately and multiply it. --proxy-headers
# with a trusted forwarded-allow range lets uvicorn set the real client IP from
# the ingress, which is what client_ip and the IP-keyed limiter rely on. Scale
# out by running more replicas behind the load balancer, or move the limiter to a
# shared store first.
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-*}"]
