"""Video analysis: container metadata, keyframe extraction and frame-level
temporal consistency. Uses OpenCV for decoding (no shell-out)."""
import re
import struct

import numpy as np

from .base import Detector, EvidenceFile, MediaContext, Signal

try:
    import cv2  # type: ignore

    HAVE_CV2 = True
except Exception:  # pragma: no cover
    cv2 = None
    HAVE_CV2 = False

VIDEO_GENERATORS = ["sora", "runway", "pika", "kling", "google veo", "veo 3", "veo3", "luma dream", "dream machine",
                    "hailuo", "synthesia", "heygen", "d-id", "deepfacelab", "facefusion", "hedra", "invideo ai"]
CONTAINERS = {b"moov", b"udta", b"trak", b"mdia", b"minf", b"ilst", b"meta"}
MAX_SECONDS = 600
MAX_KEYFRAMES = 12
TEMPORAL_FRAMES = 450


def mp4_metadata(data: bytes, limit: int = 50_000_000) -> dict[str, str]:
    """Walk ISO-BMFF boxes and collect iTunes-style text tags (©too, ©cmt, ...)."""
    out: dict[str, str] = {}

    def walk(buf: bytes, start: int, end: int, depth: int) -> None:
        i = start
        while i + 8 <= end and depth < 8 and len(out) < 50:
            size, typ = struct.unpack(">I4s", buf[i:i + 8])
            hdr = 8
            if size == 1 and i + 16 <= end:
                size = struct.unpack(">Q", buf[i + 8:i + 16])[0]
                hdr = 16
            elif size == 0:
                size = end - i
            if size < hdr or i + size > end:
                return
            body_start = i + hdr
            if typ == b"meta":
                body_start += 4  # full box: version+flags
            if typ in CONTAINERS:
                walk(buf, body_start, i + size, depth + 1)
            elif depth >= 2 and (typ[:1] == b"\xa9" or typ in (b"desc", b"ldes", b"cprt")):
                inner = buf[body_start:i + size]
                j = inner.find(b"data")
                text = inner[j + 12:] if j >= 0 else inner
                val = text[:500].decode("utf-8", "ignore").strip("\x00 ").strip()
                if val:
                    out[typ.decode("latin-1").replace("\xa9", "©")] = val
            i += size

    view = data[:limit]
    try:
        walk(view, 0, len(view), 0)
    except struct.error:
        pass
    return out


class VideoForensicsDetector(Detector):
    name = "video_forensics"
    version = "1.0"
    kinds = ("video",)
    category = "heuristic"
    description = "Container metadata, keyframe sampling and frame-to-frame temporal consistency checks."

    def availability(self):
        return (HAVE_CV2, None if HAVE_CV2 else "OpenCV (opencv-python-headless) is not installed")

    def run(self, ctx: MediaContext):
        if not HAVE_CV2:
            return self.report("unavailable", reason=self.availability()[1])
        signals: list[Signal] = []
        evidence: list[EvidenceFile] = []

        meta = mp4_metadata(ctx.data) if ctx.mime in ("video/mp4", "video/quicktime") else {}
        facts: dict = {"container_tags": meta}
        tag_text = " ".join(meta.values()).lower()
        xmp_i = ctx.data.find(b"<x:xmpmeta")
        if xmp_i >= 0:
            tag_text += " " + ctx.data[xmp_i:xmp_i + 20000].decode("utf-8", "ignore").lower()
        gen = next((g for g in VIDEO_GENERATORS if re.search(r"\b" + re.escape(g) + r"\b", tag_text)), None)
        if gen or "trainedalgorithmicmedia" in tag_text:
            signals.append(Signal(
                self.name, "video_generator_metadata", "AI video tool named in metadata", "strong", "synthetic",
                f"Container metadata references '{gen or 'trainedAlgorithmicMedia'}'. That indicates synthetic origin, "
                "not necessarily deceptive intent.", category="ai_generated_declared", evidence={"tags": meta}))
        encoder = meta.get("©too", "")
        if encoder:
            facts["encoder"] = encoder

        cap = cv2.VideoCapture(str(ctx.path))
        if not cap.isOpened():
            return self.report("error", reason="Video could not be decoded", signals=signals, facts=facts)
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = n / fps if fps > 0 else 0.0
            facts.update({"fps": round(fps, 3), "frames": n, "width": w, "height": h, "duration_s": round(duration, 2)})
            if fps <= 0 or n <= 0:
                return self.report("error", reason="Video has no readable frames", signals=signals, facts=facts)
            if duration > MAX_SECONDS:
                facts["note"] = f"Only the first {MAX_SECONDS}s are sampled"

            # Keyframes for the evidence timeline and for frame-level model detectors.
            usable = min(n, int(MAX_SECONDS * fps))
            idxs = sorted(set(np.linspace(0, max(usable - 1, 0), num=min(MAX_KEYFRAMES, usable)).astype(int).tolist()))
            keyframes = []
            for k, fi in enumerate(idxs):
                cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
                ok, frame = cap.read()
                if not ok:
                    continue
                ts = fi / fps
                name = f"frame_{k:02d}.jpg"
                small = _resize(frame, 640)
                cv2.imwrite(str(ctx.out_dir / name), small, [cv2.IMWRITE_JPEG_QUALITY, 85])
                keyframes.append((ts, frame))
                evidence.append(EvidenceFile(name, "frame", f"Keyframe at {ts:.2f}s", timestamp_s=round(ts, 2)))
                ctx.progress(30 + int(20 * (k + 1) / len(idxs)), "Extracting keyframes")
            ctx.cache["keyframes"] = keyframes

            # Temporal consistency over the opening segment, read sequentially.
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            diffs: list[float] = []
            prev = None
            for _ in range(min(TEMPORAL_FRAMES, n)):
                ok, frame = cap.read()
                if not ok:
                    break
                g = cv2.cvtColor(_resize(frame, 256), cv2.COLOR_BGR2GRAY).astype(np.float32)
                if prev is not None and prev.shape == g.shape:
                    diffs.append(float(np.abs(g - prev).mean()))
                prev = g
            ctx.progress(60, "Checking temporal consistency")
        finally:
            cap.release()

        if len(diffs) >= 10:
            d = np.array(diffs)
            med = float(np.median(d)) + 1e-3
            cuts = [i + 1 for i, v in enumerate(d) if v > med * 8 and v > 12]
            # Isolated single-frame anomaly: frame i jumps away and i+1 jumps straight back.
            blips = [i + 1 for i in range(len(d) - 1) if d[i] > med * 6 and d[i + 1] > med * 6 and d[i] > 8]
            facts.update({"temporal_frames": len(diffs) + 1, "median_frame_diff": round(med, 3),
                          "scene_cuts": len(cuts)})
            if blips:
                ts = [round(b / fps, 2) for b in blips[:10]]
                signals.append(Signal(
                    self.name, "temporal_blips", "Isolated frame discontinuities", "weak", "manipulated",
                    f"{len(blips)} single frames differ sharply from both neighbours. Inserted or replaced frames can "
                    "cause this, but so can flashes, glitches and fast edits.", category="temporal_inconsistency",
                    evidence={"timestamps_s": ts}, timestamp_s=ts[0]))
        return self.report(signals=signals, evidence=evidence, facts=facts)


def _resize(frame, max_side: int):
    h, w = frame.shape[:2]
    s = max_side / max(h, w)
    if s >= 1:
        return frame
    return cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)


class AVSyncDetector(Detector):
    name = "av_sync"
    version = "0.0"
    kinds = ("video",)
    category = "model"
    description = "Lip-sync and audio-video synchronization analysis."

    def availability(self):
        return False, "Not implemented in this release. Needs ffmpeg plus a lip-sync model (Phase 3)."

    def run(self, ctx):
        return self.report("unavailable", reason=self.availability()[1])
