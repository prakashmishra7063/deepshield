"""C2PA / Content Credentials verification.

Uses the official c2pa-python SDK when installed to cryptographically validate
manifests. Without the SDK, it can only report that a manifest appears to be
present (unverified).
"""
import io
import json

from .base import Detector, MediaContext, Signal

try:
    import c2pa  # type: ignore

    HAVE_C2PA = True
except Exception:  # pragma: no cover - depends on environment
    c2pa = None
    HAVE_C2PA = False

SYNTHETIC_TYPES = ("trainedAlgorithmicMedia", "compositeWithTrainedAlgorithmicMedia", "algorithmicMedia",
                   "compositeSynthetic")
CAPTURE_TYPES = ("digitalCapture", "computationalCapture")


def _context():
    """Per-read SDK context that never fetches remote manifests (an SSRF surface)."""
    try:
        return c2pa.Context.from_dict({"verify": {"remote_manifest_fetch": False}})
    except Exception:
        return None


def _actions(manifest: dict) -> list[dict]:
    out = []
    for a in manifest.get("assertions", []) or []:
        if str(a.get("label", "")).startswith("c2pa.actions"):
            out.extend((a.get("data") or {}).get("actions", []) or [])
    return out


class ProvenanceDetector(Detector):
    name = "content_credentials"
    version = "1.0"
    kinds = ("image", "video", "audio")
    category = "provenance"
    description = "Reads and cryptographically validates C2PA Content Credentials when present."

    def availability(self):
        if HAVE_C2PA:
            return True, None
        return True, "c2pa-python not installed: manifests can be detected but not verified"

    def run(self, ctx: MediaContext):
        head = ctx.data[:8_000_000]
        marker = b"c2pa" in head and (b"jumb" in head or b"caBX" in head or b"uuid" in head)

        if not HAVE_C2PA:
            if not marker:
                return self.report(facts={"manifest": "none"}, reason="No Content Credentials found (unverified scan)")
            return self.report(
                facts={"manifest": "present_unverified"},
                reason="Install c2pa-python to verify signatures",
                signals=[Signal(self.name, "c2pa_unverified", "Content Credentials present (not verified)", "weak",
                                "neutral", "A C2PA manifest appears to be embedded, but signature verification is "
                                "unavailable in this deployment.")])

        try:
            reader = c2pa.Reader.try_create(ctx.mime, io.BytesIO(ctx.data), context=_context())
        except Exception as e:
            if marker:
                return self.report(
                    facts={"manifest": "unreadable"},
                    signals=[Signal(self.name, "c2pa_unreadable", "Content Credentials could not be read", "moderate",
                                    "manipulated", "The file seems to contain a C2PA manifest, but it could not be "
                                    "parsed. The file may have been modified after signing.",
                                    category="provenance_broken", evidence={"error": type(e).__name__})])
            return self.report(facts={"manifest": "none"}, reason="No Content Credentials found")
        if reader is None:
            return self.report(facts={"manifest": "none"}, reason="No Content Credentials found")

        try:
            store = json.loads(reader.json())
            state = reader.get_validation_state()
        finally:
            try:
                reader.close()
            except Exception:
                pass

        active_label = store.get("active_manifest")
        manifest = (store.get("manifests") or {}).get(active_label, {}) if active_label else {}
        sig = manifest.get("signature_info") or {}
        generator = manifest.get("claim_generator") or ", ".join(
            g.get("name", "") for g in manifest.get("claim_generator_info", []) or [] if isinstance(g, dict))
        actions = _actions(manifest)
        action_names = [a.get("action") for a in actions]
        source_types = [str(a.get("digitalSourceType", "")).rsplit("/", 1)[-1] for a in actions if a.get("digitalSourceType")]
        statuses = store.get("validation_status") or []
        failures = [s for s in statuses if isinstance(s, dict) and s.get("code") and not str(s.get("code")).endswith(
            (".validated", ".match", ".trusted", ".insideValidity"))]

        valid = (state in ("Valid", "Trusted")) and not failures
        facts = {
            "manifest": "present",
            "validation_state": state,
            "verified": valid,
            "trusted_signer": state == "Trusted",
            "issuer": sig.get("issuer"),
            "signed_at": sig.get("time"),
            "claim_generator": generator,
            "actions": action_names,
            "digital_source_types": source_types,
        }
        signals: list[Signal] = []
        if not valid:
            signals.append(Signal(
                self.name, "c2pa_invalid", "Content Credentials failed validation", "strong", "manipulated",
                "A C2PA manifest is present but its validation failed. The content may have been altered after "
                "it was signed, or the signature is untrusted.", category="provenance_broken",
                evidence={"validation_state": state, "issues": [s.get("code") for s in failures][:10]}))
        if any(t in SYNTHETIC_TYPES for t in source_types):
            signals.append(Signal(
                self.name, "c2pa_ai_generated", "Content Credentials declare AI generation", "strong", "synthetic",
                f"The signed manifest states the content was produced with generative AI ({generator or 'unknown tool'}). "
                "This is a disclosure of synthetic origin, not an indication of malicious intent.",
                category="ai_generated_declared", evidence={"digital_source_types": source_types, "issuer": sig.get("issuer")}))
        if valid and any(t in CAPTURE_TYPES for t in source_types) and not any(t in SYNTHETIC_TYPES for t in source_types):
            edits = [a for a in action_names if a and a not in ("c2pa.created", "c2pa.opened")]
            signals.append(Signal(
                self.name, "c2pa_capture", "Verified capture provenance", "strong", "authentic",
                f"A valid manifest signed by {sig.get('issuer') or 'an unknown issuer'} records capture by a device"
                + (f"; later actions: {', '.join(edits)}." if edits else " with no recorded edits."),
                evidence={"issuer": sig.get("issuer"), "actions": action_names}))
        elif valid and not source_types:
            signals.append(Signal(
                self.name, "c2pa_valid", "Valid Content Credentials", "moderate", "neutral",
                f"Manifest signed by {sig.get('issuer') or 'unknown issuer'} validated successfully. "
                f"Recorded actions: {', '.join(a for a in action_names if a) or 'none'}.",
                evidence={"issuer": sig.get("issuer"), "actions": action_names}))
        return self.report(signals=signals, facts=facts)
