# DeepShield API reference (v1)

Base URL: `http://<host>:8000/api/v1`. Interactive OpenAPI docs: `http://<host>:8000/docs`.

Authentication uses an `Authorization: Bearer <token>` header. The token is either
* a JWT access token from `POST /auth/login` (60 minutes by default), or
* a personal API token (`dsk_…`) created under **Settings → API tokens**. The browser extension uses these.

Errors return `{"detail": "..."}`. Validation errors return the FastAPI list format. `429` responses include `Retry-After`.

## Auth

```http
POST /auth/register   {"email": "a@b.com", "password": "≥10 chars", "accept_terms": true}   → 201 User
POST /auth/login      {"email": "a@b.com", "password": "..."}  → {"access_token", "token_type", "expires_in"}
GET  /auth/me         → User
PATCH /auth/me/settings {"alert_threshold": "potentially_manipulated|high_risk", "email_alerts": bool}
GET  /auth/tokens     → [ApiToken]
POST /auth/tokens     {"name": "Chrome"} → ApiToken + {"token": "dsk_…"}   (shown once)
DELETE /auth/tokens/{id}
```

## Analyses

```http
POST /analyses/upload        multipart/form-data  file=<binary>          → 202 Analysis
POST /analyses/url           {"url": "https://…", "page_url": "https://…"?, "source": "url|extension"} → 202 Analysis
GET  /analyses?page=1&page_size=20&classification=&kind=&status=&q=       → {items, total, page, page_size}
GET  /analyses/{id}                                                        → Analysis (with result)
DELETE /analyses/{id}                                                      → 204 (purges media & evidence)
GET  /analyses/{id}/evidence/{name}                                        → image/png | image/jpeg
POST /analyses/{id}/report-link  {"format": "pdf|json"}                    → {"url": "/api/v1/reports/<token>", "expires_in": 600}
GET  /reports/{token}                                                      → file download (no auth header; token is HMAC-signed)
GET  /dashboard/summary                                                    → counters, by_kind, trend, recent
```

`Analysis.status` moves from `queued` to `running` and ends as `completed` or `failed`. Poll `GET /analyses/{id}`
(the UI polls every 1.5 s). `progress` (0–100) and `stage` describe the current step.

Upload limits: `DS_MAX_UPLOAD_MB` (413 if exceeded), and the type is detected from magic bytes (415 if unsupported).
URL rules: http/https only, ports 80/443, no embedded credentials, public IP addresses only (400 otherwise).

### Result object (`Analysis.result`)

See [ARCHITECTURE.md §4](ARCHITECTURE.md#analysis-result-shape-result_json). Key fields:

| Field | Meaning |
|---|---|
| `assessment.classification` | `likely_authentic` · `uncertain` · `potentially_manipulated` · `high_risk` |
| `assessment.likelihood` | Calibrated probability, or `null` when no calibrated model ran |
| `assessment.reliability` | `low` (heuristics only) · `medium` · `high` |
| `assessment.synthetic_origin` | `declared` · `suspected` · `none_detected` · `unknown`, independent of risk |
| `signals[]` | Indicators: `detector`, `title`, `strength`, `direction`, `detail`, `evidence`, `timestamp_s` |
| `detectors[]` | Every detector considered, with `status` (`ok/unavailable/error/skipped`) and `reason` |
| `evidence[]` | Derived images (`heatmap`, `frame`, `spectrogram`) fetched via the evidence endpoint |
| `limitations[]`, `next_steps[]` | Plain-language caveats and guidance |
| `platform` | Present when the URL belongs to a known social platform, with that integration's status |
| `embedded_media[]` | Child analyses created for media found on a scanned web page |

## Cases & alerts

```http
GET  /cases                               → [CaseSummary]
POST /cases   {"title": "...", "analysis_id": "DS-…"?}  → CaseDetail
GET  /cases/{id}                          → CaseDetail (items, notes)
PATCH /cases/{id}  {"title"?, "status"?: "open|reported|resolved|dismissed"}
DELETE /cases/{id}
POST /cases/{id}/items   {"analysis_id": "DS-…"}
DELETE /cases/{id}/items/{analysis_id}
POST /cases/{id}/notes   {"body": "..."}
GET  /analyses/{id}/cases
GET  /alerts?state=new|acknowledged|dismissed
PATCH /alerts/{id}  {"state": "acknowledged|dismissed|new"}
```

## System & admin

```http
GET /system/health      → detectors with availability, queue depth, ffmpeg presence (no auth)
GET /integrations       → integration registry with status
GET /admin/audit?limit=&action=   (admin)
GET /admin/stats                  (admin)
```

## Example

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"..."}' | jq -r .access_token)
ID=$(curl -s -H "Authorization: Bearer $TOKEN" -F file=@photo.jpg localhost:8000/api/v1/analyses/upload | jq -r .id)
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/analyses/$ID | jq .result.assessment
```
