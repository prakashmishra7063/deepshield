# DeepShield AI — Architecture

> *See Beyond the Fake. Protect What's Real.*

This document covers the system architecture, user flows, data model, API contracts and
detection pipeline for the MVP (Phase 1) and how later phases attach to it.
Read [FEATURE_STATUS.md](FEATURE_STATUS.md) to see what is implemented, what needs
configuration and what is planned.

## 1. System overview

```
 ┌──────────────────┐      ┌──────────────────────┐
 │ Next.js frontend │      │ Browser extension    │
 │ (dashboard, scan │      │ (Chrome / Edge, MV3) │
 │  reports, cases) │      └─────────┬────────────┘
 └────────┬─────────┘                │  Bearer API token
          │ JWT (httpOnly-free SPA)  │
          ▼                          ▼
 ┌─────────────────────────────────────────────────┐
 │ FastAPI  /api/v1                                │
 │  auth · analyses · reports · cases · alerts     │
 │  integrations · system · admin                  │
 │  ── rate limiting, RBAC, audit log, size limits │
 └───────┬───────────────┬─────────────────┬───────┘
         │               │                 │
         ▼               ▼                 ▼
  ┌────────────┐  ┌─────────────┐   ┌──────────────┐
  │ SQL DB     │  │ Object store│   │ Job queue    │
  │ (SQLite /  │  │ (local disk,│   │ (DB-backed,  │
  │ PostgreSQL)│  │  originals  │   │  worker pool)│
  └────────────┘  │  kept apart │   └──────┬───────┘
                  │  from       │          │
                  │  derived)   │          ▼
                  └─────────────┘   ┌──────────────────────────┐
                                    │ Detection pipeline       │
                                    │ sniff → detectors →      │
                                    │ ensemble → report        │
                                    └──────────────────────────┘
```

Design choices:

* **Detectors are plugins.** Each detector declares the media types it handles and reports
  its own availability. The API and UI never depend on a specific model, so models can be
  swapped without touching the application.
* **Jobs, not requests.** Uploads and URL scans create an `Analysis` row in `queued`
  state; a worker pool claims jobs from the database. The UI polls progress. Swapping the
  in-process worker for Azure Service Bus / Celery only requires a new `JobQueue`
  implementation.
* **Original media is immutable.** Originals are stored under `originals/` with their
  SHA-256; derived evidence (ELA heatmaps, frames) lives under `derived/`. Originals are
  purged after the configured retention window.
* **No fabricated results.** A detector that is not configured returns status
  `unavailable` with a reason. The ensemble never invents a score, and a numeric
  likelihood is shown only from detectors flagged `calibrated=True`.

## 2. User flows

### 2.1 Register / log in
1. User registers with email and password (scrypt-hashed) and gets a personal workspace on the
   Free plan. A verification email must be confirmed before scanning. The first registered user
   becomes the platform **owner**, with the owner console and an unlimited internal plan.
2. Login returns a short-lived JWT access token. The SPA keeps it in memory plus
   `sessionStorage`.
3. Users can mint **API tokens** (for the browser extension). Only a SHA-256 hash is stored.

### 2.2 Scan a file
1. Drag and drop on the **Scan** page → `POST /analyses/upload` (multipart).
2. The server checks the size limit, sniffs magic bytes (the extension and the client's
   Content-Type are not trusted) and rejects unsupported types. It then stores the original
   and enqueues a job.
3. The UI polls `GET /analyses/{id}` and shows stage-by-stage progress.
4. When the job completes, the UI shows the classification badge, the synthetic-origin
   flag, signals, evidence images, limitations and next steps.
5. Export: `POST /analyses/{id}/report-link` returns a short-lived **signed URL** for the
   PDF or JSON report.

### 2.3 Scan a URL
1. User pastes a URL → `POST /analyses/url`.
2. The worker fetches it through the **SSRF guard**: http/https only, DNS resolved and
   every address checked (private, loopback, link-local, multicast and reserved ranges
   are blocked), the connection pinned to the vetted IP, redirects re-validated hop by
   hop, and size and time limits applied.
3. If the response is media, it is analyzed as an upload. If it is HTML, the page is
   checked for impersonation (lookalike or punycode domains, credential forms, brand
   mismatch). `og:image` and `og:video` media are then fetched (also through the guard)
   and analyzed.
4. Social platforms (Instagram, TikTok, …) show their integration status. A URL that
   needs authenticated platform access is reported as such and is never scraped around
   access controls.

### 2.4 Investigate
* Any analysis can be added to a **Case** with notes and a status
  (`open → reported → resolved / dismissed`).
* **Alerts** are raised when an analysis meets the user's risk threshold. Users can
  acknowledge or dismiss them. Nothing is ever auto-reported or auto-deleted.

### 2.5 Browser extension
1. User pastes the API base URL and an API token in the options page.
2. Hovering over an image or video shows a small **Scan** chip. A context-menu item works
   too.
3. The extension calls `POST /analyses/url` with the media URL and page URL, then polls
   for the result.
4. A warning overlay is shown only when the result is `high_risk` (or reaches the user's
   configured threshold). Otherwise the result appears in the popup panel.

## 3. Data model

See `backend/app/models.py` and the Alembic migration in
`backend/alembic/versions/0001_initial.py`.

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Accounts | id, email (unique), password_hash, role (`owner` = platform owner / `user`), status, email_verified_at, token_version, active_org_id, alert_threshold |
| `plans` | Products | id, name, monthly_scans (-1 = unlimited), max_upload_mb, max_members, price_monthly_cents, public |
| `organizations` | Workspaces (`personal` / `team`) | id, name, kind, plan_id, status, credits, scan_quota_override |
| `memberships` | User ↔ workspace | org_id, user_id, role (`owner`/`admin`/`member`) |
| `invites` / `email_tokens` | Emailed single-use links (hash stored) | token_hash, expires_at, accepted_at / used_at |
| `platform_settings` | Owner switches | signups_open, require_email_verification |
| `api_tokens` | Extension and API access | id, user_id, name, token_hash, last_used_at, revoked |
| `media_objects` | Stored originals | id, sha256, mime, kind (`image`/`video`/`audio`/`html`), size, storage_path, source_url, purged_at |
| `analyses` | One scan (workspace-owned) | id (public `DS-…` id), org_id, user_id (creator), parent_id (embedded media), media_id, source_url, page_url, status (`queued`/`running`/`completed`/`failed`), progress, stage, classification, synthetic_origin, likelihood (nullable, calibrated only), result_json, error, created_at, completed_at |
| `cases` | Investigations (workspace-owned) | id, org_id, user_id, title, status, created_at, updated_at |
| `case_items` | Analyses in a case | case_id, analysis_id |
| `case_notes` | Notes | id, case_id, user_id, body, created_at |
| `alerts` | Notifications | id, user_id, analysis_id, level, title, state (`new`/`acknowledged`/`dismissed`), created_at |
| `audit_logs` | Sensitive actions | id, user_id, action, target, ip, detail, created_at |

## 4. API contracts (v1)

Base path: `/api/v1`. Interactive OpenAPI is at `/docs`. The full reference is in
[API.md](API.md).

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | `{email, password}` → user |
| POST | `/auth/login` | `{email, password}` → `{access_token}` |
| GET | `/auth/me` | current user |
| GET/POST/DELETE | `/auth/tokens` | API tokens (secret shown once) |
| PATCH | `/auth/me/settings` | `{alert_threshold}` |
| POST | `/analyses/upload` | multipart `file` → `AnalysisOut` (202) |
| POST | `/analyses/url` | `{url, page_url?}` → `AnalysisOut` (202) |
| GET | `/analyses` | paginated history, filter by `classification`, `kind` |
| GET | `/analyses/{id}` | full result |
| DELETE | `/analyses/{id}` | deletes the analysis and purges media |
| GET | `/analyses/{id}/evidence/{name}` | derived evidence image (auth) |
| POST | `/analyses/{id}/report-link` | `{format: pdf\|json}` → signed URL (10 min) |
| GET | `/reports/{token}` | download via signed token (no auth header) |
| GET/POST | `/cases`, `/cases/{id}`, `/cases/{id}/items`, `/cases/{id}/notes` | |
| PATCH | `/cases/{id}` | status / title |
| GET | `/alerts`, PATCH `/alerts/{id}` | |
| GET | `/dashboard/summary` | counters, breakdowns, trend |
| GET | `/integrations` | integration registry + status |
| GET | `/system/health` | detector availability |
| GET | `/admin/audit` | admin only |

### Analysis result shape (`result_json`)

```jsonc
{
  "assessment": {
    "classification": "likely_authentic | uncertain | potentially_manipulated | high_risk",
    "label": "Uncertain",
    "summary": "Plain-language explanation",
    "likelihood": null,              // only when a calibrated detector ran
    "likelihood_calibrated": false,
    "reliability": "low | medium | high",
    "synthetic_origin": "declared | suspected | none_detected | unknown",
    "categories": ["ai_generated_declared", "edited_with_software"]
  },
  "signals": [ { "detector": "image_metadata", "id": "...", "title": "...",
                 "strength": "weak | moderate | strong", "direction": "manipulated | synthetic | authentic | neutral",
                 "detail": "...", "evidence": {...}, "timestamp_s": null } ],
  "detectors": [ { "name": "...", "version": "...", "status": "ok | unavailable | error | skipped",
                   "reason": "...", "calibrated": false } ],
  "evidence": [ { "name": "ela.png", "kind": "heatmap", "caption": "..." } ],
  "limitations": ["..."],
  "next_steps": ["..."],
  "media": { "kind": "image", "mime": "image/jpeg", "sha256": "...", "size": 12345, "width": 1024, "height": 768 }
}
```

## 5. Detection pipeline

```
media bytes ──► sniff (magic bytes) ──► kind ∈ {image, video, audio, html}
                    │
                    ▼
         detectors applicable to kind (each: status + signals + evidence)
   image:  image_metadata · provenance(C2PA) · ela · jpeg_compression · ml_image*
   video:  container_metadata · frame_sampling → image detectors per keyframe ·
           temporal_consistency · ml_video*
   audio:  audio_spectral · ml_audio*
   html:   web_impersonation (+ embedded og:media → recursive analysis)
                    │
                    ▼
       ensemble ──► classification · synthetic_origin · reliability · limitations
                    │
                    ▼
        report (JSON + PDF) · alerts (threshold) · audit
   * = pluggable model slot, `unavailable` until configured
```

### Ensemble rules

Signals carry a **strength** (`weak` / `moderate` / `strong`) and a **direction**.
Heuristic forensics such as ELA, compression and spectral statistics are **weak** by
design. They are not calibrated detectors.

| Classification | Rule |
|---|---|
| **High Risk — Possible Deepfake** | ≥2 independent detectors with moderate+ manipulation signals (a calibrated model at or above its high threshold counts as one strong detector, so it needs corroboration) |
| **Potentially Manipulated** | ≥1 moderate+ manipulation signal, or ≥2 weak signals from different detectors |
| **Likely Authentic** | Verified provenance chain with no edit/AI assertions, **or** a calibrated model below its low threshold, *and* no moderate+ manipulation signals |
| **Uncertain** | everything else, including "only weak heuristics ran" |

`synthetic_origin` is reported **separately** from manipulation risk. A self-declared
AI-generated image (for example, C2PA `trainedAlgorithmicMedia`) is labelled *synthetic
origin: declared*. That alone does not make it "High Risk", because AI generation is not
evidence of malicious intent.

`reliability` reflects which detector classes actually ran:
* only heuristics → `low`
* a calibrated model, or verified provenance → `medium`
* both → `high`

### Adding a real model

Implement `app/detection/ml_model.py::ModelBackend` (or point the env variables
`DS_IMAGE_MODEL_PATH` / `DS_AUDIO_MODEL_PATH` to a TorchScript checkpoint with the
documented I/O contract). Set `calibrated=True` only once you have run the evaluation
pipeline (`backend/evaluation/evaluate.py`) on an independent, representative labelled
set and stored its thresholds.

## 6. Security

* scrypt password hashing, JWT HS256 with expiry, hashed API tokens, RBAC on admin routes
* Upload limits (`DS_MAX_UPLOAD_MB`), magic-byte sniffing, Pillow decompression-bomb
  limit, files never executed, stored under random names outside any web root
* Media parsing runs in worker threads with time budgets. For production, run workers in
  a separate container with no network egress except via the fetcher (see
  DEPLOYMENT.md).
* SSRF guard for every outbound fetch, including `og:` media and redirects
* Signed (HMAC), expiring report links
* Per-IP and per-user rate limiting, an audit log for auth, token, delete, export and
  admin actions
* Retention purge of originals (`DS_RETENTION_HOURS`), user-initiated deletion
* Security headers, CORS restricted to configured origins
