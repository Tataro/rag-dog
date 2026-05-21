# Cloudflare Tunnel setup

The tunnel exposes only `/webhook/telegram` and `/webhook/line` to the public internet. The web UI and `/api/*` stay localhost-only.

## One-time setup

```bash
# 1. Install cloudflared natively (recommended) or use the Docker service.
brew install cloudflared

# 2. Authenticate. Opens a browser to pick a domain you own on Cloudflare.
cloudflared tunnel login

# 3. Create the tunnel.
cloudflared tunnel create rag-dog
# This prints a UUID and writes credentials to ~/.cloudflared/<UUID>.json.

# 4. Copy the credentials into this directory (so the Docker service can find them).
cp ~/.cloudflared/<UUID>.json ./ops/cloudflared/

# 5. Create config.yml from the example.
cp ops/cloudflared/config.yml.example ops/cloudflared/config.yml
# Edit it: replace <TUNNEL-UUID> and <YOUR-SUBDOMAIN>.

# 6. Route DNS for your subdomain to the tunnel.
cloudflared tunnel route dns rag-dog <YOUR-SUBDOMAIN>.example.com
```

## Run

Natively (preferred):

```bash
cloudflared tunnel --config ops/cloudflared/config.yml run
```

Or via Docker Compose:

```bash
docker compose --profile tunnel up -d cloudflared
```

## Configure bot webhooks

- **Telegram**:
  ```bash
  curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -d "url=https://<YOUR-SUBDOMAIN>.example.com/webhook/telegram" \
    -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
  ```
- **Line**: set the webhook URL in the LINE Developers Console to `https://<YOUR-SUBDOMAIN>.example.com/webhook/line`.
