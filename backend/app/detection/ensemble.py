"""Combine independent detector reports into an assessment.

Rules are documented in docs/ARCHITECTURE.md §5. The ensemble never invents a
number: `likelihood` is only populated from calibrated detectors.
"""
from .base import STRENGTH_RANK, DetectorReport, Signal

LABELS = {
    "likely_authentic": "Likely Authentic",
    "uncertain": "Uncertain",
    "potentially_manipulated": "Potentially Manipulated",
    "high_risk": "High Risk — Possible Deepfake",
}
ORDER = ["likely_authentic", "uncertain", "potentially_manipulated", "high_risk"]

BASE_LIMITATIONS = [
    "Detection results are estimates, not proof. Every method here has false positives and false negatives.",
    "A low-risk result does not guarantee authenticity. A high-risk result does not establish who created the "
    "content or why.",
    "Recompression by social platforms, screenshots and resizing can hide or imitate manipulation traces.",
]


def _rank(s: Signal) -> int:
    return STRENGTH_RANK[s.strength]


def assess(kind: str, reports: list[DetectorReport]) -> dict:
    ran = [r for r in reports if r.status == "ok"]
    signals = [s for r in ran for s in r.signals]
    manip = [s for s in signals if s.direction == "manipulated"]
    synth = [s for s in signals if s.direction == "synthetic"]
    authentic = [s for s in signals if s.direction == "authentic"]

    def detectors_with(sigs: list[Signal], min_rank: int) -> set[str]:
        return {s.detector for s in sigs if _rank(s) >= min_rank}

    mod_manip = detectors_with(manip, 2)
    strong_manip = detectors_with(manip, 3)
    weak_manip_dets = detectors_with(manip, 1)

    calibrated = [r for r in ran if r.calibrated and r.score is not None]
    has_verified_prov = any(r.name == "content_credentials" and r.facts.get("verified") for r in ran)
    model_ran = bool(calibrated)

    # Classification: "high risk" always needs at least two independent detectors at moderate+ strength.
    if len(mod_manip) >= 2:
        cls = "high_risk"
    elif mod_manip or len(weak_manip_dets) >= 2:
        cls = "potentially_manipulated"
    elif not mod_manip and (any(_rank(s) >= 3 for s in authentic) or any(
            r.calibrated and r.thresholds and r.score <= r.thresholds["low"] for r in calibrated)) and not weak_manip_dets:
        cls = "likely_authentic"
    else:
        cls = "uncertain"
    # A single strong, calibrated model hit without corroboration is still at least "potentially manipulated".
    if cls == "uncertain" and strong_manip:
        cls = "potentially_manipulated"

    # Synthetic origin (reported independently of manipulation risk)
    if any(s.category == "ai_generated_declared" for s in synth):
        synthetic = "declared"
    elif synth:
        synthetic = "suspected"
    elif kind == "html":
        synthetic = "unknown"
    elif model_ran or has_verified_prov:
        synthetic = "none_detected"
    else:
        synthetic = "unknown"

    # Reliability reflects which classes of evidence were actually available.
    if model_ran and has_verified_prov:
        reliability = "high"
    elif model_ran or has_verified_prov or strong_manip or synthetic == "declared":
        reliability = "medium"
    else:
        reliability = "low"

    likelihood = max((r.score for r in calibrated), default=None)
    categories = sorted({s.category for s in manip + synth if s.category})

    limitations = list(BASE_LIMITATIONS)
    unavailable = [r for r in reports if r.status == "unavailable"]
    if not model_ran and kind in ("image", "video", "audio"):
        limitations.insert(0, "No calibrated deep-learning detector was available for this content type. This result "
                              "rests on forensic heuristics and provenance only, and cannot rule out sophisticated "
                              "deepfakes.")
    for r in unavailable:
        limitations.append(f"{r.name}: {r.reason}")
    if kind == "audio":
        limitations.append("Voice analysis accuracy varies with language, accent, recording device and background noise.")
    if kind == "video":
        limitations.append("Only sampled keyframes and the opening segment were examined. Audio-video synchronization "
                           "was not checked.")

    summary = _summary(cls, synthetic, manip, synth, kind)
    return {
        "classification": cls,
        "label": LABELS[cls],
        "summary": summary,
        "likelihood": round(likelihood, 4) if likelihood is not None else None,
        "likelihood_calibrated": likelihood is not None,
        "reliability": reliability,
        "synthetic_origin": synthetic,
        "categories": categories,
        "limitations": limitations,
        "next_steps": _next_steps(cls, synthetic, kind),
    }


def _summary(cls: str, synthetic: str, manip: list[Signal], synth: list[Signal], kind: str) -> str:
    top = sorted(manip, key=_rank, reverse=True)[:2]
    if kind == "html":
        if cls in ("high_risk", "potentially_manipulated"):
            return "This page shows signs of impersonation: " + "; ".join(s.title.lower() for s in top) + "."
        return "No strong impersonation indicators were found on this page. Stay cautious with any request for credentials or payment."
    parts = []
    if cls == "high_risk":
        parts.append("Several independent checks found indications of manipulation: " +
                     "; ".join(s.title.lower() for s in top) + ".")
    elif cls == "potentially_manipulated":
        parts.append("At least one meaningful indicator of editing or manipulation was found: " +
                     "; ".join(s.title.lower() for s in top) + ".")
    elif cls == "likely_authentic":
        parts.append("No strong manipulation indicators were detected, and the available evidence supports authenticity.")
    else:
        parts.append("The available evidence is insufficient or conflicting, so no confident assessment is possible.")
    if synthetic == "declared":
        parts.append("The file openly declares that it was generated with AI. Synthetic origin alone does not imply "
                     "deceptive intent.")
    elif synthetic == "suspected":
        parts.append("Some characteristics are consistent with AI-generated content.")
    return " ".join(parts)


def _next_steps(cls: str, synthetic: str, kind: str) -> list[str]:
    steps = []
    if kind == "html":
        return ["Do not enter passwords, payment details or recovery phrases on this page.",
                "Navigate to the organization's official site by typing its address yourself.",
                "Report suspected phishing to the impersonated brand and to your browser's safe-browsing service."]
    if cls in ("high_risk", "potentially_manipulated"):
        steps += ["Do not share or act on this content until it has been verified.",
                  "Find the original source and compare against other copies (reverse image or video search).",
                  "Contact the person or organization depicted through a known, independent channel."]
        if kind == "audio":
            steps.append("If this is a voice call or message asking for money or credentials, hang up and call back "
                         "on a number you already trust.")
        steps.append("Save this report and add the content to a case if you plan to report it to the platform.")
    else:
        steps += ["Check where the content was first published and who published it.",
                  "Look for corroborating coverage from independent, reputable sources."]
    if synthetic == "declared":
        steps.append("If the content is presented as real footage, report the missing AI disclosure to the platform.")
    steps.append("Get expert forensic review before taking legal, financial or reputational action.")
    return steps
