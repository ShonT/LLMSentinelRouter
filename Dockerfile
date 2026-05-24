FROM golang:1.26-bookworm AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/sentinelrouter ./cmd/sentinelrouter

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin sentinel

USER sentinel
WORKDIR /home/sentinel/app

COPY --from=builder --chown=sentinel:sentinel /out/sentinelrouter /usr/local/bin/sentinelrouter
COPY --chown=sentinel:sentinel config ./config
COPY --chown=sentinel:sentinel documentation ./documentation

RUN mkdir -p data logs data/metrics

EXPOSE 8000
EXPOSE 8001

ENV LOG_LEVEL=INFO
ENV DATABASE_URL=sqlite:////home/sentinel/app/data/sentinelrouter.db
ENV MODELS_CONFIG_PATH=/home/sentinel/app/config/models_config.json
ENV SENTINEL_CONFIG_PATH=/home/sentinel/app/config/sentinel_config.json

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["/usr/local/bin/sentinelrouter", "healthcheck"]

CMD ["/usr/local/bin/sentinelrouter"]
