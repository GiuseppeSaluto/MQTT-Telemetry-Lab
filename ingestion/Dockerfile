FROM rust:1-slim AS build

WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:stable-slim

COPY --from=build /app/target/release/ingestion /usr/local/bin/ingestion

CMD ["ingestion"]
