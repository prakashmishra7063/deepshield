# DeepShield AI

**See Beyond the Fake. Protect What's Real.**

DeepShield AI analyzes images, video, audio and web pages for signs of manipulation, AI generation and
impersonation. Each result comes with the evidence and uncertainty behind it, and the platform never fabricates a
detection: when a model or integration isn't configured, the result says so.

```
backend/     FastAPI API, detection pipeline, job queue, reports, Alembic migrations, tests, evaluation
frontend/    Next.js 16 + React 19 + Tailwind 4 dashboard
extension/   Chrome / Edge (Manifest V3) extension
docs/        Architecture, API, deployment, feature status, privacy & responsible use
```

## Quick start

```bash
# API
cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000

# Web (new terminal)
cd frontend && npm install && npm run dev        # → http://localhost:3000
```

Register an account (the first user becomes admin), then drop a file or paste a URL on **Scan content**.
To install the extension, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#local-development).

## What it does today

* **Image:** metadata (AI-generator declarations, face-swap apps, editors), C2PA Content Credentials validation,
  error level analysis heatmap, JPEG grid forensics
* **Video:** container tags, keyframe timeline, frame-level temporal discontinuities
* **Audio:** band-limiting, digital silence and clipping checks, with a spectrogram
* **Web pages:** lookalike or punycode domains, brand-impersonating login forms, plus analysis of the page's media
* Four-level classification (*Likely Authentic · Uncertain · Potentially Manipulated · High Risk*), reported
  separately from **synthetic origin**, with reliability, limitations and next steps
* PDF and JSON evidence reports via signed links, history, investigations with notes, alerts, and an audit log

The heuristic detectors are honest but limited. On their own they will usually return **Uncertain** for
sophisticated deepfakes. Plug in a trained model through the `ml_image` / `ml_audio` slots and calibrate it with
`backend/evaluation/evaluate.py` to get calibrated likelihoods. See [docs/FEATURE_STATUS.md](docs/FEATURE_STATUS.md)
for exactly what is implemented, what needs configuration and what is planned.

## Tests

```bash
cd backend && pytest -q          # 34 tests: API flows, SSRF guard, ensemble rules, detectors
cd frontend && npm test && npm run typecheck && npm run build
```

## Docs

* [Architecture, user flows, data model, pipeline](docs/ARCHITECTURE.md)
* [API reference](docs/API.md) (plus live OpenAPI at `/docs`)
* [Deployment](docs/DEPLOYMENT.md)
* [Feature status](docs/FEATURE_STATUS.md)
* [Privacy & responsible use](docs/PRIVACY_AND_RESPONSIBLE_USE.md)
