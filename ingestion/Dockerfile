FROM rust:1.97.1-alpine AS build

RUN apk add --no-cache musl-dev
WORKDIR /app
COPY . .
RUN cargo build --release

FROM scratch

COPY --from=build /app/target/release/ingestion /ingestion
# no /etc/passwd in scratch: run as the conventional "nobody" uid/gid
USER 65534:65534

ENTRYPOINT ["/ingestion"]
