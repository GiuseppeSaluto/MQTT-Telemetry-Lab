FROM rust:1.97.1-slim-trixie AS build

WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:trixie-slim

COPY --from=build /app/target/release/ingestion /usr/local/bin/ingestion

CMD ["ingestion"]
