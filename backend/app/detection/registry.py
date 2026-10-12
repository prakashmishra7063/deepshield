from .audio import AudioSpectralDetector
from .base import Detector
from .compression import ErrorLevelDetector, JpegGridDetector
from .image_metadata import ImageMetadataDetector
from .ml_model import AudioModelDetector, ImageModelDetector
from .provenance import ProvenanceDetector
from .video import AVSyncDetector, VideoForensicsDetector
from .web import WebImpersonationDetector

# Order matters: video_forensics populates keyframes used by ml_image.
DETECTORS: list[Detector] = [
    ProvenanceDetector(),
    ImageMetadataDetector(),
    ErrorLevelDetector(),
    JpegGridDetector(),
    VideoForensicsDetector(),
    AVSyncDetector(),
    ImageModelDetector(),
    AudioSpectralDetector(),
    AudioModelDetector(),
    WebImpersonationDetector(),
]


def detectors_for(kind: str) -> list[Detector]:
    return [d for d in DETECTORS if kind in d.kinds]


def health() -> list[dict]:
    out = []
    for d in DETECTORS:
        ok, reason = d.availability()
        out.append({"name": d.name, "version": d.version, "kinds": list(d.kinds), "category": d.category,
                    "description": d.description, "available": ok, "reason": reason})
    return out
