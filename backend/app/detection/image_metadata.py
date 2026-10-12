"""Metadata analysis: EXIF, PNG text chunks and XMP.

Metadata is easy to strip or forge, so its absence proves nothing and camera
fields are never treated as proof of authenticity. Explicit generator
declarations are, however, a reliable sign of *declared* synthetic origin.
"""
import re

from PIL import ExifTags

from .base import Detector, MediaContext, Signal
from .imaging import ImageDecodeError, cached_image

AI_GENERATORS = [
    "midjourney", "dall-e", "dall·e", "dalle", "stable diffusion", "stablediffusion", "sdxl", "novelai",
    "adobe firefly", "firefly", "imagen", "flux.1", "comfyui", "automatic1111", "invokeai", "leonardo.ai",
    "ideogram", "gemini", "openai", "chatgpt", "gpt-4o", "nano banana", "runway", "kandinsky", "playground ai",
]
FACE_APPS = ["faceapp", "facetune", "reface", "deepfacelab", "faceswap", "roop", "facefusion", "deepswap", "inswapper"]
EDITORS = ["photoshop", "gimp", "affinity photo", "pixelmator", "snapseed", "lightroom", "picsart", "canva", "photopea", "paint.net"]

PNG_AI_KEYS = {"parameters", "prompt", "workflow", "sd-metadata", "invokeai_metadata", "dream", "comfyui"}
XMP_SYNTHETIC = [b"trainedAlgorithmicMedia", b"compositeWithTrainedAlgorithmicMedia", b"algorithmicMedia"]


def _match(text: str, words: list[str]) -> str | None:
    t = text.lower()
    for w in words:
        if w in t:
            return w
    return None


class ImageMetadataDetector(Detector):
    name = "image_metadata"
    version = "1.1"
    kinds = ("image",)
    category = "heuristic"
    description = "EXIF, PNG text-chunk and XMP inspection for generator, editor and timestamp clues."

    def run(self, ctx: MediaContext):
        try:
            im = cached_image(ctx)
        except ImageDecodeError as e:
            return self.report("error", reason=str(e))

        signals: list[Signal] = []
        facts: dict = {"format": im.format, "width": im.width, "height": im.height, "mode": im.mode}

        exif = {}
        try:
            raw = im.getexif()
            exif = {ExifTags.TAGS.get(k, str(k)): v for k, v in raw.items()}
            try:
                sub = raw.get_ifd(0x8769)
                exif.update({ExifTags.TAGS.get(k, str(k)): v for k, v in sub.items()})
            except Exception:
                pass
        except Exception:
            pass
        exif_str = {k: str(v)[:200] for k, v in exif.items() if isinstance(k, str) and k in {
            "Make", "Model", "Software", "DateTime", "DateTimeOriginal", "DateTimeDigitized", "Artist",
            "ImageDescription", "LensModel", "HostComputer", "UserComment"}}
        facts["exif"] = exif_str

        texts: dict[str, str] = {}
        for k, v in (im.info or {}).items():
            if isinstance(v, str):
                texts[k] = v[:2000]
            elif isinstance(v, bytes) and k in ("xmp", "XML:com.adobe.xmp"):
                texts["xmp"] = v[:20000].decode("utf-8", "ignore")
        facts["text_chunks"] = sorted(texts.keys())

        xmp_blob = ctx.data[:4_000_000]
        xmp_start = xmp_blob.find(b"<x:xmpmeta")
        xmp = ""
        if xmp_start >= 0:
            end = xmp_blob.find(b"</x:xmpmeta>", xmp_start)
            xmp = xmp_blob[xmp_start:end + 12 if end > 0 else xmp_start + 20000].decode("utf-8", "ignore")
        elif "xmp" in texts:
            xmp = texts["xmp"]
        facts["xmp_present"] = bool(xmp)

        # 1. Generator declarations
        haystack = " ".join([exif_str.get("Software", ""), exif_str.get("ImageDescription", ""),
                             exif_str.get("UserComment", ""), exif_str.get("Artist", ""),
                             " ".join(f"{k}={v}" for k, v in texts.items() if k != "xmp")])
        gen = _match(haystack, AI_GENERATORS)
        ai_keys = PNG_AI_KEYS & {k.lower() for k in texts}
        xmp_ai = next((m.decode() for m in XMP_SYNTHETIC if m.decode() in xmp), None)
        creator_tool = re.search(r'CreatorTool[=>"\s]+([^"<]{1,120})', xmp)
        if creator_tool and not gen:
            gen = _match(creator_tool.group(1), AI_GENERATORS)

        if gen or ai_keys or xmp_ai:
            evidence = {}
            if gen:
                evidence["generator_keyword"] = gen
            if ai_keys:
                evidence["png_text_keys"] = sorted(ai_keys)
            if xmp_ai:
                evidence["xmp_digital_source_type"] = xmp_ai
            signals.append(Signal(
                self.name, "ai_generator_metadata", "AI generation declared in file metadata", "strong", "synthetic",
                "The file's metadata names an AI image generator or carries generation parameters. "
                "This indicates synthetic origin, not necessarily deceptive intent.",
                category="ai_generated_declared", evidence=evidence))

        # 2. Face manipulation apps
        all_text = haystack + " " + (creator_tool.group(1) if creator_tool else "")
        face = _match(all_text, FACE_APPS)
        if face:
            signals.append(Signal(
                self.name, "face_app_metadata", "Face-editing or face-swap software recorded", "moderate", "manipulated",
                f"Metadata references '{face}', software used to retouch, reshape or swap faces.",
                category="face_manipulation", evidence={"software": face}))

        # 3. General editors (normal, but relevant context)
        editor = _match(all_text, EDITORS)
        if editor and not face:
            signals.append(Signal(
                self.name, "editor_metadata", "Edited with image-editing software", "weak", "manipulated",
                f"Metadata references '{editor}'. Editing is common and often benign (cropping, colour), "
                "but it means the file is not a straight camera original.",
                category="edited_with_software", evidence={"software": editor}))

        # 4. Timestamp inconsistency
        dto, dt = exif_str.get("DateTimeOriginal"), exif_str.get("DateTime")
        if dto and dt and dto[:19] != dt[:19]:
            signals.append(Signal(
                self.name, "timestamp_mismatch", "Modification time differs from capture time", "weak", "manipulated",
                "EXIF DateTime (last modified) differs from DateTimeOriginal (capture), which suggests the file was "
                "re-saved after capture.", category="edited_with_software",
                evidence={"DateTimeOriginal": dto, "DateTime": dt}))

        # 5. Informational
        if exif_str.get("Make") or exif_str.get("Model"):
            signals.append(Signal(
                self.name, "camera_metadata", "Camera make/model present", "weak", "neutral",
                "Camera fields are present. They are trivially forgeable and are not evidence of authenticity.",
                evidence={k: exif_str[k] for k in ("Make", "Model") if k in exif_str}))
        elif not exif_str and not texts and not xmp:
            signals.append(Signal(
                self.name, "metadata_absent", "No embedded metadata", "weak", "neutral",
                "The file carries no EXIF/XMP/text metadata. Social platforms routinely strip metadata, "
                "so this is not suspicious on its own."))

        return self.report(signals=signals, facts=facts)
