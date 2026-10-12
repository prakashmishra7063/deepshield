# Deployment

## Local development

Requirements: Python 3.12+, Node 20+. ffmpeg is optional (needed for MP3/M4A/OGG/FLAC).

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000            # SQLite tables are auto-created in dev
pytest -q
```

```bash
cd frontend
npm install
npm run dev               # http://localhost:3000 (use `npx next dev -p 3100` if 3000 is reserved)
npm test && npm run typecheck
```

The frontend proxies `/api/*` to `API_ORIGIN` (default `http://127.0.0.1:8000`).

Browser extension: open `chrome://extensions` (or `edge://extensions`) and enable Developer mode.
Choose **Load unpacked** and select `extension/`. Then open the extension options and enter the API
address and an API token from **Settings → API tokens**.

## Docker Compose (single host)

```bash
cat > .env <<EOF
POSTGRES_PASSWORD=$(openssl rand -hex 24)
DS_SECRET_KEY=$(openssl rand -base64 48)
EOF
docker compose up --build -d
```

The API container runs `alembic upgrade head` on start. Both services bind to 127.0.0.1. Put a TLS-terminating
reverse proxy (Caddy, nginx, Azure Front Door) in front of `web:3000`.

## Azure reference architecture

| Concern | Service |
|---|---|
| Web + API | Azure Container Apps (two apps), with ingress through Front Door + WAF |
| Workers | A separate Container App running the same image with a broker-backed `JobQueue` (Service Bus). No public ingress, and egress only through a NAT gateway or firewall that allows public internet but blocks VNet and metadata ranges (defense in depth beyond the SSRF guard) |
| Database | Azure Database for PostgreSQL Flexible Server (TLS required, private endpoint) |
| Media storage | Azure Blob Storage with encryption at rest (CMK optional), private endpoint, and a lifecycle rule matching `DS_RETENTION_HOURS`. Replace `app/storage.py` with a Blob implementation |
| Secrets | Key Vault references for `DS_SECRET_KEY`, DB and SMTP credentials |
| Identity | Entra ID / Entra External ID via OIDC (replace local password auth or add it alongside) |
| Malware scanning | Microsoft Defender for Storage on the upload container |
| Monitoring | Application Insights + Log Analytics. Alert on detector error rates and queue depth |
| Rate limiting at scale | Azure Cache for Redis behind `app/ratelimit.py` |

## Production checklist

- [ ] `DS_ENV=production`, a random `DS_SECRET_KEY` of 32+ characters (enforced at startup)
- [ ] PostgreSQL, with `alembic upgrade head` run on deploy
- [ ] HTTPS everywhere. HSTS at the proxy
- [ ] `DS_ALLOW_PRIVATE_FETCH=false` (enforced in production)
- [ ] Workers isolated: no access to internal networks or cloud metadata endpoints
- [ ] Encrypted media volume or Blob storage, plus a retention policy
- [ ] Malware scanning on uploads
- [ ] Backups for the database. Media is intentionally short-lived
- [ ] Review `docs/PRIVACY_AND_RESPONSIBLE_USE.md` with counsel for your jurisdictions
- [ ] Before enabling any ML model, run `evaluation/evaluate.py` on an independent dataset with subgroup columns and review the per-group error rates

## Email (required for real customers)

DeepShield sends verification, password-reset, invitation and alert emails over SMTP. Until
`DS_SMTP_HOST` and `DS_SMTP_FROM` are set, development servers **don't send anything**. Each
message is saved to `backend/data/outbox/` instead, and the owner console (**Settings → Email
delivery**) says so. In production (`DS_ENV=production`) nothing is saved; sending fails with a clear error instead.

Add the settings to `backend/.env`, restart the API, then use **Owner console → Settings → Send
test email to me**.

| Provider | Settings |
|---|---|
| **Gmail** (testing or very small volume) | `DS_SMTP_HOST=smtp.gmail.com`, `DS_SMTP_PORT=465`, `DS_SMTP_USER=you@gmail.com`, `DS_SMTP_PASSWORD=<16-character App Password>`, `DS_SMTP_FROM=DeepShield AI <you@gmail.com>`. Create the App Password at myaccount.google.com → Security → 2-Step Verification → App passwords. Your normal Gmail password won't work, and Gmail caps sending at a few hundred messages a day |
| **Resend / SendGrid / Brevo / Amazon SES / Mailgun** (recommended for selling) | Use the SMTP host, port (587 or 465), username and API key they give you, and a `DS_SMTP_FROM` address on **your own domain** with the provider's SPF/DKIM DNS records added, so mail isn't marked as spam |

Also set `DS_APP_URL` to the public address of the web app (e.g. `https://app.yourdomain.com`), so
links in emails open the right site.
