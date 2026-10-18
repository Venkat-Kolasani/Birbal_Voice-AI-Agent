#!/usr/bin/env bash
# Serve Birbal to other devices on the same network (phone hotspot recommended; venue guest wifi often blocks
# device-to-device traffic). Browsers only allow the microphone over HTTPS off localhost, so this makes a
# self-signed certificate for this laptop's LAN IP. On the other device, open the printed URL and accept the
# certificate warning once. Typed interviews work even without the certificate.
set -euo pipefail
cd "$(dirname "$0")/.."
IP="${1:-$(ipconfig getifaddr en0 2>/dev/null || hostname -I | awk '{print $1}')}"
PORT="${PORT:-8443}"
CERTS=data/certs
mkdir -p "$CERTS"
if [ ! -f "$CERTS/$IP.pem" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj "/CN=$IP" \
    -addext "subjectAltName=IP:$IP,DNS:localhost" \
    -keyout "$CERTS/$IP-key.pem" -out "$CERTS/$IP.pem" 2>/dev/null
fi
echo "Birbal on your network: https://$IP:$PORT  (accept the certificate warning on the other device)"
exec uv run uvicorn api:app --app-dir server --host 0.0.0.0 --port "$PORT" \
  --ssl-keyfile "$CERTS/$IP-key.pem" --ssl-certfile "$CERTS/$IP.pem"
