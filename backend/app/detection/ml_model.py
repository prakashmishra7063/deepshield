"""Pluggable deep-learning detector slots.

No model weights ship with DeepShield. A slot reports `unavailable` until an
operator configures a TorchScript checkpoint:

  Image model  (DS_IMAGE_MODEL_PATH)
    input : float32 [1, 3, S, S] RGB, ImageNet-normalised, S = calibration.input_size (default 224)
    output: a single logit, or logits [1, 2] where index 1 = manipulated/synthetic
  Audio model  (DS_AUDIO_MODEL_PATH)
    input : float32 [1, N] mono 16 kHz waveform, windows of calibration.window_s seconds (default 4)
    output: as above

A calibration JSON (DS_*_MODEL_CALIBRATION) written by evaluation/evaluate.py
supplies the thresholds. Without it the model output is shown as an
*uncalibrated* weak signal and no likelihood number is displayed.
"""
import json
import threading
from pathlib import Path

import numpy as np

from ..config import get_settings
from .base import Detector, MediaContext, Signal
from .imaging import ImageDecodeError, cached_image, to_rgb

try:
    import torch  # type: ignore

    HAVE_TORCH = True
except Exception:  # pragma: no cover
    torch = None
    HAVE_TORCH = False

_lock = threading.Lock()
_loaded: dict[str, object] = {}


def _load(path: str):
    with _lock:
        if path not in _loaded:
            m = torch.jit.load(path, map_location="cpu")
            m.eval()
            _loaded[path] = m
        return _loaded[path]


def _calibration(path: str | None) -> dict:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _prob(out) -> float:
    t = out[0] if isinstance(out, (tuple, list)) else out
    t = t.detach().float().reshape(-1)
    if t.numel() == 1:
        return float(torch.sigmoid(t[0]))
    return float(torch.softmax(t[:2], dim=0)[1])


class _ModelSlot(Detector):
    category = "model"
    path_attr = ""
    cal_attr = ""

    def _cfg(self):
        s = get_settings()
        return getattr(s, self.path_attr), _calibration(getattr(s, self.cal_attr))

    def availability(self):
        path, _ = self._cfg()
        if not path:
            return False, f"No model configured (set DS_{self.path_attr.upper()})"
        if not HAVE_TORCH:
            return False, "PyTorch is not installed"
        if not Path(path).is_file():
            return False, f"Model file not found: {Path(path).name}"
        return True, None

    def _signals_for(self, score: float, cal: dict, label: str, ts: float | None = None) -> tuple[list[Signal], bool]:
        calibrated = bool(cal.get("calibrated")) and "low" in cal and "high" in cal
        if not calibrated:
            if score >= 0.5:
                return [Signal(self.name, "model_uncalibrated", f"{label} model flagged content (uncalibrated)", "weak",
                               "manipulated", f"Raw model output {score:.2f}. The model has not been calibrated on a "
                               "validation set, so this number is not a probability.", category="model_detection",
                               evidence={"raw_score": round(score, 4)}, timestamp_s=ts)], False
            return [], False
        lo, hi = float(cal["low"]), float(cal["high"])
        if score >= hi:
            return [Signal(self.name, "model_high", f"{label} model: high manipulation likelihood", "strong", "manipulated",
                           f"Calibrated score {score:.2f} meets the validated high-risk threshold ({hi:.2f}).",
                           category="model_detection", evidence={"score": round(score, 4)}, timestamp_s=ts)], True
        if score >= (lo + hi) / 2:
            return [Signal(self.name, "model_elevated", f"{label} model: elevated manipulation likelihood", "moderate",
                           "manipulated", f"Calibrated score {score:.2f} lies between the validated thresholds.",
                           category="model_detection", evidence={"score": round(score, 4)}, timestamp_s=ts)], True
        if score <= lo:
            return [Signal(self.name, "model_low", f"{label} model: no manipulation detected", "moderate", "authentic",
                           f"Calibrated score {score:.2f} is below the validated low threshold ({lo:.2f}). A low score "
                           "does not guarantee authenticity.", evidence={"score": round(score, 4)})], True
        return [], True


class ImageModelDetector(_ModelSlot):
    name = "ml_image"
    version = "slot-1"
    kinds = ("image", "video")
    path_attr = "image_model_path"
    cal_attr = "image_model_calibration"
    description = "Deep-learning face-swap / synthetic-image classifier (operator-supplied TorchScript model)."

    def run(self, ctx: MediaContext):
        ok, why = self.availability()
        if not ok:
            return self.report("unavailable", reason=why)
        path, cal = self._cfg()
        model = _load(path)
        size = int(cal.get("input_size", 224))
        mean = np.array([0.485, 0.456, 0.406], np.float32)
        std = np.array([0.229, 0.224, 0.225], np.float32)

        def score_rgb(rgb_arr: np.ndarray) -> float:
            from PIL import Image
            im = Image.fromarray(rgb_arr).resize((size, size))
            a = (np.asarray(im, np.float32) / 255 - mean) / std
            with torch.no_grad():
                return _prob(model(torch.from_numpy(a.transpose(2, 0, 1)[None].copy())))

        if ctx.kind == "image":
            try:
                rgb = np.asarray(to_rgb(cached_image(ctx)))
            except ImageDecodeError as e:
                return self.report("error", reason=str(e))
            score = score_rgb(rgb)
            sig, calibrated = self._signals_for(score, cal, "Image")
            return self.report(signals=sig, calibrated=calibrated, score=score if calibrated else None,
                               thresholds={"low": cal["low"], "high": cal["high"]} if calibrated else None,
                               facts={"raw_score": round(score, 4)})

        frames = ctx.cache.get("keyframes") or []
        if not frames:
            return self.report("skipped", reason="No keyframes available")
        scores = [(ts, score_rgb(f[:, :, ::-1].copy())) for ts, f in frames]
        ts_max, top = max(scores, key=lambda t: t[1])
        sig, calibrated = self._signals_for(top, cal, "Frame", ts=round(ts_max, 2))
        return self.report(signals=sig, calibrated=calibrated, score=top if calibrated else None,
                           thresholds={"low": cal["low"], "high": cal["high"]} if calibrated else None,
                           facts={"frame_scores": [{"t": round(t, 2), "score": round(s, 4)} for t, s in scores]})


class AudioModelDetector(_ModelSlot):
    name = "ml_audio"
    version = "slot-1"
    kinds = ("audio",)
    path_attr = "audio_model_path"
    cal_attr = "audio_model_calibration"
    description = "Deep-learning synthetic-speech / voice-clone classifier (operator-supplied TorchScript model)."

    def run(self, ctx: MediaContext):
        ok, why = self.availability()
        if not ok:
            return self.report("unavailable", reason=why)
        from .audio import AudioDecodeError, decode_audio
        try:
            x, sr = decode_audio(ctx)
        except AudioDecodeError as e:
            return self.report("unavailable", reason=str(e))
        path, cal = self._cfg()
        model = _load(path)
        if sr != 16000:  # linear resample is adequate for a classifier front-end
            n = int(len(x) * 16000 / sr)
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        win = int(float(cal.get("window_s", 4)) * 16000)
        scores = []
        for start in range(0, max(1, len(x) - win + 1), win):
            seg = x[start:start + win]
            if len(seg) < win // 2:
                break
            with torch.no_grad():
                scores.append((start / 16000, _prob(model(torch.from_numpy(seg[None].copy())))))
        if not scores:
            return self.report("skipped", reason="Audio too short for the model window")
        ts_max, top = max(scores, key=lambda t: t[1])
        sig, calibrated = self._signals_for(top, cal, "Voice", ts=round(ts_max, 2))
        return self.report(signals=sig, calibrated=calibrated, score=top if calibrated else None,
                           thresholds={"low": cal["low"], "high": cal["high"]} if calibrated else None,
                           facts={"window_scores": [{"t": round(t, 2), "score": round(s, 4)} for t, s in scores]})
