"""Compression forensics: error level analysis (ELA) and JPEG block-grid alignment.

Both are classic, interpretable heuristics with known high false-positive rates
(text, sharp edges, saturated colours and heavy social-media recompression all
light up ELA). They are reported only as *weak* signals.
"""
import io

import numpy as np
from PIL import Image

from .base import Detector, EvidenceFile, MediaContext, Signal
from .imaging import ImageDecodeError, cached_image, to_rgb

MAX_SIDE = 2048


def _downscale(im: Image.Image) -> Image.Image:
    if max(im.size) > MAX_SIDE:
        im = im.copy()
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    return im


class ErrorLevelDetector(Detector):
    name = "error_level_analysis"
    version = "1.0"
    kinds = ("image",)
    category = "heuristic"
    description = "Re-compresses the image and maps regions whose error level differs from the rest."

    def run(self, ctx: MediaContext):
        try:
            im = cached_image(ctx)
        except ImageDecodeError as e:
            return self.report("error", reason=str(e))
        if im.format != "JPEG":
            return self.report("skipped", reason="ELA is only meaningful for JPEG (lossy) images")
        rgb = to_rgb(im)
        # Analyse at native resolution (resampling destroys the block structure), cropping huge images.
        if max(rgb.size) > 4096:
            rgb = rgb.crop((0, 0, min(rgb.width, 4096), min(rgb.height, 4096)))
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=90)
        buf.seek(0)
        resaved = Image.open(buf).convert("RGB")
        a = np.asarray(rgb, dtype=np.int16)
        b = np.asarray(resaved, dtype=np.int16)
        diff = np.abs(a - b).max(axis=2).astype(np.float32)

        # Block statistics (16x16)
        bs = 16
        h, w = (diff.shape[0] // bs) * bs, (diff.shape[1] // bs) * bs
        if h < bs * 4 or w < bs * 4:
            return self.report("skipped", reason="Image too small for ELA")
        blocks = diff[:h, :w].reshape(h // bs, bs, w // bs, bs).mean(axis=(1, 3))
        med = float(np.median(blocks))
        mad = float(np.median(np.abs(blocks - med))) + 1e-3
        z = (blocks - med) / (1.4826 * mad)
        outlier_frac = float((z > 6).mean())
        p99 = float(np.percentile(blocks, 99))

        # Heatmap evidence
        scale = 255.0 / max(1.0, float(np.percentile(diff, 99.5)))
        heat = np.clip(diff * scale, 0, 255).astype(np.uint8)
        heat_img = Image.fromarray(np.stack([heat, (heat.astype(np.uint16) * 3 // 5).astype(np.uint8),
                                             (255 - heat) // 6], axis=2), "RGB")
        _downscale(heat_img).save(ctx.out_dir / "ela.png")
        evidence = [EvidenceFile("ela.png", "heatmap", "Error level analysis: bright regions recompress differently "
                                 "from their surroundings. Edges and text are naturally bright.")]

        facts = {"median_block_error": round(med, 3), "p99_block_error": round(p99, 3),
                 "outlier_block_fraction": round(outlier_frac, 4)}
        signals = []
        # A small, concentrated cluster of strongly deviating blocks is the pattern of interest.
        if 0.002 < outlier_frac < 0.15 and p99 > med * 3 and med > 0.2:
            ys, xs = np.where(z > 6)
            bbox = [int(xs.min() * bs), int(ys.min() * bs), int((xs.max() + 1) * bs), int((ys.max() + 1) * bs)]
            signals.append(Signal(
                self.name, "ela_localized", "Localized compression inconsistency", "weak", "manipulated",
                f"{outlier_frac:.1%} of the image area recompresses very differently from the rest. Pasted or "
                "regenerated regions can cause this, but so can text, sharp edges and saturated colours.",
                category="local_edit", evidence={"bbox": bbox, **facts}))
        return self.report(signals=signals, evidence=evidence, facts=facts)


def blockiness_phase(gray: np.ndarray) -> tuple[int, int, float, float]:
    """Return (x_phase, y_phase, x_peak_ratio, y_peak_ratio) of 8x8 block boundaries."""
    g = gray.astype(np.float32)
    dx = np.abs(np.diff(g, axis=1)).mean(axis=0)
    dy = np.abs(np.diff(g, axis=0)).mean(axis=1)

    def phase(d: np.ndarray) -> tuple[int, float]:
        n = (len(d) // 8) * 8
        if n < 64:
            return -1, 0.0
        per = d[:n].reshape(-1, 8).mean(axis=0)
        k = int(per.argmax())
        others = np.delete(per, k).mean() + 1e-6
        return k, float(per[k] / others)

    xp, xr = phase(dx)
    yp, yr = phase(dy)
    return xp, yp, xr, yr


class JpegGridDetector(Detector):
    name = "compression_grid"
    version = "1.0"
    kinds = ("image",)
    category = "heuristic"
    description = "Checks JPEG 8x8 block-artifact alignment and quantization for re-compression or cropping clues."

    def run(self, ctx: MediaContext):
        try:
            im = cached_image(ctx)
        except ImageDecodeError as e:
            return self.report("error", reason=str(e))
        gray = np.asarray(to_rgb(im).convert("L"))
        if gray.shape[0] > 4096 or gray.shape[1] > 4096:
            gray = gray[:4096, :4096]
        xp, yp, xr, yr = blockiness_phase(gray)
        facts: dict = {"grid_phase": [xp, yp], "grid_peak_ratio": [round(xr, 3), round(yr, 3)]}
        q = getattr(im, "quantization", None)
        if q:
            luma = list(q.get(0, []))
            if luma:
                facts["luma_quant_mean"] = round(sum(luma) / len(luma), 2)
                # Rough IJG-equivalent quality estimate from the mean luminance table value.
                m = sum(luma) / len(luma)
                std_mean = 57.625
                scale = m / std_mean * 100
                facts["estimated_quality"] = int(max(1, min(100, (200 - scale) / 2 if scale <= 100 else 5000 / scale)))

        signals = []
        strong_grid = xr > 1.25 and yr > 1.25
        if im.format == "JPEG" and strong_grid and (xp != 7 or yp != 7):
            signals.append(Signal(
                self.name, "grid_misaligned", "JPEG block grid is misaligned", "weak", "manipulated",
                "Compression artifacts don't line up with the image's own 8x8 JPEG grid. The image was cropped "
                "or composited from a previously compressed source and then re-saved.",
                category="recompressed", evidence=facts))
        elif im.format in ("PNG", "WEBP", "BMP", "TIFF") and strong_grid:
            signals.append(Signal(
                self.name, "prior_jpeg", "Lossless file carries JPEG artifacts", "weak", "neutral",
                "This lossless image shows 8x8 JPEG blocking, so it was converted from a JPEG. That is common for "
                "screenshots and re-uploads.", evidence=facts))
        return self.report(signals=signals, facts=facts)
