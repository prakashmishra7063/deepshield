"""Shared, hardened image decoding."""
import io
import warnings

from PIL import Image, ImageOps

# Refuse decompression bombs (default is ~89M px and only warns).
Image.MAX_IMAGE_PIXELS = 80_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)


class ImageDecodeError(Exception):
    pass


def open_image(data: bytes) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        return im
    except Image.DecompressionBombError as e:  # type: ignore[attr-defined]
        raise ImageDecodeError("Image dimensions exceed the safe processing limit") from e
    except Image.DecompressionBombWarning as e:
        raise ImageDecodeError("Image dimensions exceed the safe processing limit") from e
    except Exception as e:
        raise ImageDecodeError(f"Could not decode image: {type(e).__name__}") from e


def to_rgb(im: Image.Image) -> Image.Image:
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    im = ImageOps.exif_transpose(im) if im.format == "JPEG" else im
    return im.convert("RGB")


def cached_image(ctx) -> Image.Image:
    if "image" not in ctx.cache:
        ctx.cache["image"] = open_image(ctx.data)
    return ctx.cache["image"]
