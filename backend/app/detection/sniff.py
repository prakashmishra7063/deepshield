"""Identify media type from magic bytes. File extensions and client-supplied
Content-Type headers are never trusted."""
from dataclasses import dataclass

_MP4_BRANDS_AUDIO = {b"M4A ", b"M4B ", b"M4P "}
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif"}


@dataclass(frozen=True)
class Sniffed:
    kind: str  # image | video | audio
    mime: str
    supported: bool = True
    note: str | None = None


def sniff(head: bytes) -> Sniffed | None:
    if head.startswith(b"\xff\xd8\xff"):
        return Sniffed("image", "image/jpeg")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Sniffed("image", "image/png")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return Sniffed("image", "image/webp")
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return Sniffed("image", "image/gif")
    if head[:2] == b"BM":
        return Sniffed("image", "image/bmp")
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return Sniffed("image", "image/tiff")
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return Sniffed("audio", "audio/wav")
    if head[:4] == b"fLaC":
        return Sniffed("audio", "audio/flac", note="FLAC decoding requires ffmpeg")
    if head[:4] == b"OggS":
        return Sniffed("audio", "audio/ogg", note="Ogg decoding requires ffmpeg")
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0 and head[1] != 0xFF):
        return Sniffed("audio", "audio/mpeg")
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in _HEIF_BRANDS:
            return Sniffed("image", "image/heic", supported=False, note="HEIC/AVIF decoding is not enabled")
        if brand in _MP4_BRANDS_AUDIO:
            return Sniffed("audio", "audio/mp4")
        if brand == b"qt  ":
            return Sniffed("video", "video/quicktime")
        return Sniffed("video", "video/mp4")
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return Sniffed("video", "video/webm")
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return Sniffed("video", "video/x-msvideo")
    return None


def looks_like_html(head: bytes) -> bool:
    h = head[:512].lstrip().lower()
    return h.startswith(b"<!doctype html") or h.startswith(b"<html") or b"<head" in h or b"<body" in h
