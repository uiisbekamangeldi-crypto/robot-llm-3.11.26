FROM golang:1.24.6-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch RELEASE.2025-09-07T16-13-09Z \
    https://github.com/minio/minio.git . \
    && test "$(git rev-parse HEAD)" = "07c3a429bfed433e49018cb0f78a52145d4bedeb"
RUN CGO_ENABLED=0 go build -trimpath -o /minio .

FROM debian:bookworm-slim
RUN useradd --uid 10001 --create-home minio && mkdir /data && chown 10001:10001 /data
COPY --from=builder /minio /usr/local/bin/minio
USER 10001
VOLUME /data
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
