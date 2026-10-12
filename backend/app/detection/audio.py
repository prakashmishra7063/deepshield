"""Audio forensics: decoding plus interpretable spectral statistics.

These statistics are weak heuristics. Reliable voice-clone detection requires a
trained model (see ml_model.AudioModelDetector).
"""
import io
import shutil
import subprocess
import wave

import numpy as np
from PIL import Image

from .base import Detector, EvidenceFile, MediaContext, Signal

MAX_SECONDS = 120
FFMPEG = shutil.which("ffmpeg")


class AudioDecodeError(Exception):
    pass


def decode_audio(ctx: MediaContext) -> tuple[np.ndarray, int]:
    """Return mono float32 samples in [-1, 1] and the sample rate."""
    if "audio" in ctx.cache:
        return ctx.cache["audio"]
    if ctx.mime == "audio/wav":
        try:
            with wave.open(io.BytesIO(ctx.data)) as w:
                sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
                raw = w.readframes(min(w.getnframes(), sr * MAX_SECONDS))
        except (wave.Error, EOFError) as e:
            raise AudioDecodeError(f"Unsupported WAV encoding ({e})") from e
        if sw == 1:
            x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
        elif sw == 2:
            x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
        elif sw == 3:
            b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
            v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
            v = np.where(v & 0x800000, v - 0x1000000, v)
            x = v.astype(np.float32) / 8388608
        elif sw == 4:
            x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
        else:
            raise AudioDecodeError("Unsupported WAV sample width")
        if ch > 1:
            x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
        ctx.cache["audio"] = (x, sr)
        return x, sr
    if not FFMPEG:
        raise AudioDecodeError(f"Decoding {ctx.mime} requires ffmpeg, which is not installed")
    # ffmpeg reads from stdin; no shell, fixed arguments, hard timeout.
    proc = subprocess.run(
        [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-t", str(MAX_SECONDS),
         "-vn", "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le", "-ar", "44100", "pipe:1"],
        input=ctx.data, capture_output=True, timeout=120, check=False)
    if proc.returncode != 0 or not proc.stdout:
        raise AudioDecodeError("ffmpeg could not decode the audio stream")
    x = np.frombuffer(proc.stdout, "<i2").astype(np.float32) / 32768
    ctx.cache["audio"] = (x, 44100)
    return x, 44100


def stft_db(x: np.ndarray, n_fft: int = 1024, hop: int = 256) -> np.ndarray:
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
    spec = np.abs(np.fft.rfft(frames * np.hanning(n_fft), axis=1)) ** 2
    return 10 * np.log10(spec + 1e-12)


class AudioSpectralDetector(Detector):
    name = "audio_spectral"
    version = "1.0"
    kinds = ("audio",)
    category = "heuristic"
    description = "Bandwidth, digital-silence and spectral statistics that can accompany synthetic or re-processed speech."

    def run(self, ctx: MediaContext):
        try:
            x, sr = decode_audio(ctx)
        except AudioDecodeError as e:
            return self.report("unavailable", reason=str(e))
        if len(x) < sr // 2:
            return self.report("skipped", reason="Audio shorter than 0.5 s")

        duration = len(x) / sr
        spec = stft_db(x)
        mean_db = spec.mean(axis=0)
        freqs = np.fft.rfftfreq(1024, 1 / sr)
        peak = mean_db.max()
        above = np.where(mean_db > peak - 70)[0]
        bandwidth = float(freqs[above.max()]) if len(above) else 0.0
        peak_amp = float(np.abs(x).max())
        clip_frac = float((np.abs(x) > 0.999).mean())

        # Runs of exact digital zeros (>= 20 ms) away from the clip edges.
        edge = int(0.25 * sr)
        zero = np.concatenate([[0], (x[edge:len(x) - edge] == 0).astype(np.int8), [0]])
        bounds = np.flatnonzero(np.diff(zero))
        lengths = bounds[1::2] - bounds[::2]
        runs = int((lengths >= int(0.02 * sr)).sum())
        facts = {"sample_rate": sr, "duration_s": round(duration, 2), "bandwidth_hz": round(bandwidth),
                 "peak_amplitude": round(peak_amp, 4), "clipping_fraction": round(clip_frac, 5),
                 "digital_silence_runs": runs}

        img = spec[:, : len(freqs)].T[::-1]
        lo, hi = np.percentile(img, 5), np.percentile(img, 99.5)
        norm = np.clip((img - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
        col = np.stack([norm, (norm.astype(np.uint16) * 2 // 3).astype(np.uint8), 255 - norm // 2], axis=2)
        Image.fromarray(col, "RGB").resize((min(1600, max(400, img.shape[1])), 300)).save(ctx.out_dir / "spectrogram.png")
        evidence = [EvidenceFile("spectrogram.png", "spectrogram",
                                 f"Spectrogram, 0 to {sr // 2} Hz (bottom to top), first {duration:.1f}s")]

        signals = []
        if sr >= 32000 and 0 < bandwidth < 12000:
            signals.append(Signal(
                self.name, "band_limited", "Audio is band-limited below its sample rate", "weak", "synthetic",
                f"Energy stops around {bandwidth / 1000:.1f} kHz although the file is sampled at {sr / 1000:.1f} kHz. "
                "Many speech synthesizers output 16 to 24 kHz audio that is later upsampled. Low-bitrate codecs and "
                "phone recordings produce the same pattern.", category="synthetic_speech_indicator",
                evidence={"bandwidth_hz": round(bandwidth), "sample_rate": sr}))
        if runs >= 3:
            signals.append(Signal(
                self.name, "digital_silence", "Perfect digital silence between sounds", "weak", "synthetic",
                f"{runs} stretches of exact zero-valued samples occur mid-recording. Microphone recordings almost "
                "always have a noise floor. Generated or heavily edited/noise-gated audio often does not.",
                category="synthetic_speech_indicator", evidence={"runs": runs}))
        if clip_frac > 0.01:
            signals.append(Signal(self.name, "clipping", "Significant clipping", "weak", "neutral",
                                  "Over 1% of samples are clipped. This reduces the reliability of all audio analysis.",
                                  evidence={"clipping_fraction": clip_frac}))
        return self.report(signals=signals, evidence=evidence, facts=facts)
