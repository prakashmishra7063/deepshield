# Feature status: implemented vs. configurable vs. planned

DeepShield never presents simulated results as real detections. Anything below marked
**needs configuration** reports `unavailable` in the UI, API and reports until it is set up.

## Detection

| Capability | Status | Notes |
|---|---|---|
| Magic-byte file typing (JPG, PNG, WEBP, GIF, BMP, TIFF, MP4, MOV, WEBM, AVI, WAV, MP3, M4A, OGG, FLAC) | ✅ Implemented | HEIC/AVIF rejected with a clear message |
| Image metadata (EXIF / PNG text / XMP): AI-generator declarations, face-swap apps, editors, timestamp mismatch | ✅ Implemented | Heuristic. Metadata can be stripped or forged |
| C2PA Content Credentials: read and cryptographically validate, AI-generation assertions, capture provenance | ✅ Implemented | Uses `c2pa-python`, with remote manifest fetch disabled. Not yet covered by a signed test fixture |
| Error level analysis with heatmap evidence | ✅ Implemented | JPEG only. Always a *weak* signal |
| JPEG 8×8 block-grid alignment and quality estimate | ✅ Implemented | Weak signal |
| Video: container tags (AI tools), keyframe extraction, temporal discontinuities, timeline evidence | ✅ Implemented | OpenCV. Temporal analysis covers the first ~450 frames |
| Audio: bandwidth limit, digital silence, clipping, spectrogram evidence | ✅ Implemented | WAV natively. Other formats need `ffmpeg` |
| Web page impersonation: punycode, lookalike domains, brand-titled login forms, off-site credential posts, pressure language | ✅ Implemented | Heuristic brand list in `detection/web.py` |
| Embedded page media (og:image / og:video / inline) analyzed as linked child analyses | ✅ Implemented | Up to 2 per page |
| Ensemble: 4-level classification, separate synthetic-origin flag, reliability, limitations, next steps | ✅ Implemented | Rules in ARCHITECTURE.md §5 |
| Deep-learning image / video-frame detector (`ml_image`) | ⚙️ Needs configuration | Provide a TorchScript model plus a calibration JSON. See ARCHITECTURE.md |
| Deep-learning synthetic-voice detector (`ml_audio`) | ⚙️ Needs configuration | Same as above |
| Calibrated likelihood percentage | ⚙️ Needs configuration | Shown only when a calibrated model ran |
| Lip-sync / audio-video synchronization (`av_sync`) | 🗓 Planned (Phase 3) | Reported as unavailable |
| Facial landmark tracking | 🗓 Planned (Phase 3) | OpenCV 5 removed the bundled cascades. Needs a face model |

## Platform and product

| Capability | Status |
|---|---|
| Registration and login (scrypt, JWT). The first user becomes the **platform owner** | ✅ |
| Email verification before scanning, forgot/reset password, change password, sign out everywhere, self-service account deletion | ✅ (dev: emails go to `backend/data/outbox/` until SMTP is set) |
| Workspaces: a personal workspace per user, plus team workspaces with owner/admin/member roles, email invites, a workspace switcher and seat limits | ✅ |
| Plans (Free / Pro / Business / Internal), monthly scan quotas, per-plan upload limits, pay-per-scan credits | ✅ Enforced |
| Owner console: overview, customers (suspend, verify, reset, sign out, delete), workspaces (plan, quota, credits, suspend), plans editor, platform settings (open sign-ups, require verification), audit log | ✅ Shows metadata only, never customers' media or results |
| Public pricing page | ✅ |
| Online payments (Stripe checkout, subscriptions, invoices, credit packs) | 🗓 Next step. Needs Stripe keys. Until then the owner assigns plans and credits manually |
| API tokens (hashed, revocable, can't mint new tokens) | ✅ |
| Upload and URL scanning with background job queue, progress and crash recovery | ✅ |
| SSRF-safe fetcher (public IPs only, pinned connections, re-validated redirects, size and time caps) | ✅ |
| Analysis history with search and filters, deletion that purges media | ✅ |
| Evidence reports: PDF and JSON via signed, expiring links | ✅ |
| Cases with notes and status tracking | ✅ |
| In-app alerts with user threshold, acknowledge/dismiss | ✅ |
| Email alerts | ⚙️ Needs SMTP configuration |
| Browser notifications | ✅ (extension) |
| Dashboard: totals, flagged, trend, content types, recent, model availability | ✅ |
| Integrations registry page | ✅ |
| Audit log (auth, tokens, scans, deletes, report links, cases, owner actions) | ✅ In the owner console |
| Retention purge of originals | ✅ |
| Rate limiting | ✅ In-process. Use Redis for multiple replicas |
| Dark and light themes, responsive layout, keyboard and screen-reader basics | ✅ |
| Chrome / Edge MV3 extension: hover scan, context menu, page check, warning overlay, flag-for-review, notifications | ✅ |
| Postgres + Alembic migrations, Docker Compose | ✅ |

## Social platforms

| Platform | Status |
|---|---|
| Public websites, blogs, news, direct media links | ✅ Operational |
| YouTube | ⚠️ Limited: public page metadata and thumbnail only. No stream download |
| Reddit | ⚠️ Limited: direct `i.redd.it` media. Data API needs credentials |
| X, Instagram, Facebook, TikTok, LinkedIn | ⚙️ Official API credentials needed (not configured). Public preview images only where exposed |

## Later phases (not implemented)

* **Phase 4, identity protection:** consent-based face and voice reference enrollment, authorized URL watchlists, impersonation evidence packages.
* **Phase 5, enterprise:** SSO/SAML, two-factor login, SIEM/webhook export, Stripe billing.
