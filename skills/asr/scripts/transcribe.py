"""transcribe.py — audio/video -> SRT or TXT with word-level timestamps.

Pipeline: decode (stdlib wave for PCM16 wav, ffmpeg for anything else) ->
silero VAD segmentation -> ASR backend -> word timestamps -> cue builder
(../vendor/srt_postproc.py).

Backends (--backend, default auto):
    sherpa       CPU sherpa-onnx, any machine (en parakeet / zh FireRedASR2)
    parakeet_cpp parakeet.cpp CLI on GPU (en only; needs bin/ + gguf from
                 `setup.sh --gpu en`; whole file in one subprocess)
    qwen         Qwen3-ASR-1.7B + ForcedAligner on GPU (zh only; linux uses
                 the .venv-qwen torch interpreter, macOS the .venv-mlx
                 mlx-qwen3-asr interpreter — both from `setup.sh --gpu zh`)
    auto         picks the installed GPU backend for the lane, else sherpa

Self-contained: sherpa needs only `sherpa_onnx` + `numpy` (setup.sh .venv);
qwen needs the .venv-qwen stack; parakeet_cpp needs no python deps at all.
Model locations come from --models-dir/--model-dir/--vad-model/--gguf/--bin-dir
or $ASR_MODELS.

Usage:
    .venv/bin/python scripts/transcribe.py INPUT --lang en --out out.srt
    .venv-qwen/bin/python scripts/transcribe.py INPUT --lang zh --backend qwen
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))
import srt_postproc

SKILL_ROOT = Path(__file__).resolve().parents[1]
SR = 16000

# --lang lane -> (default model dir name, recognizer family, srt cfg)
LANES = {
    "en": {
        "dir": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2",
        "family": "transducer",
        "srt": {
            "line_chars": 42,
            "max_lines": 2,
            "max_dur_s": 5.0,
            "min_dur_s": 1.0,
            "gap_s": 1.0,
            "word_joiner": " ",
            "break_at_sentence": True,
            "max_cps": 20.0,
            "jieba": True,
        },
    },
    "zh": {
        "dir": "sherpa-onnx-fire-red-asr2-ctc-zh_en-2026-02-25",
        "family": "fire_red_ctc",
        "srt": {
            "line_chars": 20,
            "max_lines": 2,
            "max_dur_s": 5.0,
            "min_dur_s": 1.0,
            "gap_s": 1.0,
            "word_joiner": "",
            "break_at_sentence": True,
            "max_cps": 20.0,
            "jieba": True,
        },
    },
}


# -------------------------------------------------------------------- audio
def _read_pcm16_wav(path):
    with wave.open(str(path), "rb") as w:
        nch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        if sw != 2:
            raise ValueError(f"not 16-bit PCM (sampwidth={sw})")
        frames = w.readframes(w.getnframes())
    x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if nch > 1:
        x = x.reshape(-1, nch).mean(axis=1)
    return x, sr


def _read_via_ffmpeg(path):
    try:
        out = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                str(SR),
                "-f",
                "f32le",
                "-",
            ],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        raise SystemExit(
            "error: ffmpeg not found — install it, or feed a 16-bit PCM wav"
        ) from None
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"error: ffmpeg failed on {path}:\n{e.stderr.decode()}") from e
    return np.frombuffer(out.stdout, dtype=np.float32), SR


def read_audio(path):
    """Return (float32 mono samples, sample_rate)."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"error: no such input: {p}")
    if p.suffix.lower() == ".wav":
        try:
            return _read_pcm16_wav(p)
        except Exception:
            pass
    return _read_via_ffmpeg(p)


def _resample_linear(x, src_sr, dst_sr=SR):
    if src_sr == dst_sr:
        return x
    n_out = round(len(x) * dst_sr / src_sr)
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    xp = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    xi = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(xi, xp, x).astype(np.float32)


# ---------------------------------------------------------------------- vad
class SileroWindows:
    """silero VAD via sherpa_onnx.VadModel — per-window is_speech flags."""

    def __init__(self, model_path, threshold=0.5, provider="cpu", num_threads=1):
        import sherpa_onnx

        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(model_path)
        cfg.silero_vad.threshold = float(threshold)
        # post-processing happens in segment() below — keep the model's own
        # segmenter from pre-empting us
        cfg.silero_vad.min_speech_duration = 0.0
        cfg.silero_vad.min_silence_duration = 0.0
        cfg.silero_vad.max_speech_duration = 1e9
        cfg.sample_rate = SR
        cfg.num_threads = int(num_threads)
        cfg.provider = provider
        self._vad = sherpa_onnx.VadModel.create(cfg)
        self.window = self._vad.window_size()

    def flags(self, samples):
        self._vad.reset()
        n = len(samples) // self.window
        out = np.zeros(n, dtype=bool)
        for i in range(n):
            w = samples[i * self.window : (i + 1) * self.window]
            out[i] = self._vad.is_speech(w.tolist())
        return out


def _split_run(islands, i0, i1, max_w):
    """Split merged run islands[i0:i1] into pieces <= max_w windows.

    Cuts at the widest internal gap that keeps the piece <= max_w; falls back
    to a hard mid-speech split when no gap fits. Returns [(s, e), ...] in
    window indices."""
    s, e = islands[i0][0], islands[i1 - 1][1]
    pieces = []
    cur, j = s, i0
    while e - cur > max_w:
        best = None  # (width, gap_end, next_start, next_island_idx)
        for k in range(j, i1 - 1):
            ge, gs = islands[k][1], islands[k + 1][0]
            if ge - cur > max_w:
                break
            width = gs - ge
            if best is None or width >= best[0]:
                best = (width, ge, gs, k + 1)
        if best is None:
            cut = min(cur + max_w, e)
            pieces.append((cur, cut))
            cur = cut
            while j < i1 and islands[j][1] <= cut:
                j += 1
        else:
            _, ge, gs, nxt = best
            pieces.append((cur, ge))
            cur = gs
            j = nxt
    pieces.append((cur, e))
    return pieces


def segment(
    samples,
    vad,
    max_segment_s=30.0,
    min_silence_s=0.5,
    min_speech_s=0.25,
    pad_s=0.1,
    edge_snap_s=1.0,
):
    """VAD -> [{"t0","t1"}] padded cut bounds in seconds.

    Merge islands separated by < min_silence_s, drop runs < min_speech_s,
    re-split runs > max_segment_s at their widest internal gap, then pad and
    snap near-file-edge bounds to the edge (silero onset/offset lag otherwise
    clips words there)."""
    total_s = len(samples) / SR if len(samples) else 0.0
    if total_s <= 0:
        return []
    flags = vad.flags(samples)
    hop = vad.window / SR

    islands = []
    start = None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            islands.append((start, i))
            start = None
    if start is not None:
        islands.append((start, len(flags)))
    if not islands:
        return []

    min_sil_w = round(min_silence_s / hop)
    min_sp_w = round(min_speech_s / hop)
    max_w = round(max_segment_s / hop)

    merged = []
    for k, (s, _e) in enumerate(islands):
        if merged and s - islands[merged[-1][1] - 1][1] < min_sil_w:
            merged[-1] = (merged[-1][0], k + 1)
        else:
            merged.append((k, k + 1))

    pad_w = pad_s / hop
    out = []
    for i0, i1 in merged:
        s, e = islands[i0][0], islands[i1 - 1][1]
        if min_sp_w > e - s:
            continue
        pieces = [(s, e)] if max_w >= e - s else _split_run(islands, i0, i1, max_w)
        for s, e in pieces:
            lt0, lt1 = s * hop, min(total_s, e * hop)
            t0 = 0.0 if lt0 < edge_snap_s else max(0.0, (s - pad_w) * hop)
            t1 = (
                total_s
                if total_s - lt1 < edge_snap_s
                else min(total_s, (e + pad_w) * hop)
            )
            out.append({"t0": round(t0, 3), "t1": round(t1, 3)})
    return out


# ---------------------------------------------------------------------- asr
def _words_from_tokens(tokens, timestamps, durations, total_s, family):
    """Group ASR tokens into word dicts {w,t0,t1}.

    transducer (parakeet): BPE pieces; a leading space/'▁' starts a word;
    t1 from the TDT duration head. fire_red_ctc: SentencePiece '▁' starts a
    Latin word; CJK chars stay char-level."""
    if not tokens or not timestamps or len(timestamps) != len(tokens):
        return []
    words = []
    for i, tok in enumerate(tokens):
        if tok.startswith("<") and tok.endswith(">"):
            continue
        t0 = float(timestamps[i])
        if durations and i < len(durations) and durations[i] is not None:
            t1 = t0 + float(durations[i])
        else:
            t1 = float(timestamps[i + 1]) if i + 1 < len(tokens) else total_s
        piece = tok.replace("▁", " ").strip()
        if not piece:
            continue
        standalone = len(piece) == 1 and not piece.isascii()
        prev_standalone = (
            bool(words) and len(words[-1]["w"]) == 1 and not words[-1]["w"].isascii()
        )
        new_word = tok.startswith((" ", "▁")) or not words
        if family == "fire_red_ctc":
            new_word = new_word or standalone or prev_standalone
        if new_word:
            words.append({"w": piece, "t0": t0, "t1": t1})
        else:
            words[-1]["w"] += piece
            words[-1]["t1"] = t1
    return words


def _model_file(model_dir, stem):
    p = Path(model_dir) / f"{stem}.onnx"
    if not p.exists():
        raise SystemExit(f"error: missing model file: {p} — run scripts/setup.sh")
    return str(p)


def make_recognizer(family, model_dir, provider, num_threads):
    import sherpa_onnx

    tokens = Path(model_dir) / "tokens.txt"
    if not tokens.exists():
        raise SystemExit(f"error: missing tokens: {tokens} — run scripts/setup.sh")
    if family == "transducer":
        return sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=_model_file(model_dir, "encoder"),
            decoder=_model_file(model_dir, "decoder"),
            joiner=_model_file(model_dir, "joiner"),
            tokens=str(tokens),
            num_threads=int(num_threads),
            provider=provider,
            decoding_method="greedy_search",
            model_type="nemo_transducer",
            modeling_unit="cjkchar",
            debug=False,
        )
    return sherpa_onnx.OfflineRecognizer.from_fire_red_asr_ctc(
        model=_model_file(model_dir, "model"),
        tokens=str(tokens),
        num_threads=int(num_threads),
        decoding_method="greedy_search",
        provider=provider,
        debug=False,
    )


def recognize(rec, family, samples, segs, batch=8):
    """Decode each segment; return word list offset onto the file timeline."""
    words_all, text_parts = [], []
    order = sorted(
        range(len(segs)), key=lambda i: segs[i]["t1"] - segs[i]["t0"], reverse=True
    )
    for bi in range(0, len(order), batch):
        idxs = order[bi : bi + batch]
        streams = []
        for i in idxs:
            seg = segs[i]
            chunk = samples[round(seg["t0"] * SR) : round(seg["t1"] * SR)]
            s = rec.create_stream()
            s.accept_waveform(SR, np.ascontiguousarray(chunk, dtype=np.float32))
            streams.append((i, s, len(chunk) / SR))
        rec.decode_streams([s for _, s, _ in streams])
        for i, s, dur in streams:
            r = s.result
            seg = segs[i]
            for w in _words_from_tokens(
                list(getattr(r, "tokens", None) or []),
                list(getattr(r, "timestamps", None) or []),
                list(getattr(r, "durations", None) or []),
                dur,
                family,
            ):
                w["t0"] += seg["t0"]
                w["t1"] += seg["t0"]
                words_all.append(w)
            if r.text.strip():
                text_parts.append((seg["t0"], seg["t1"], r.text.strip()))
        done = min(bi + batch, len(order))
        print(f"[asr] {done}/{len(order)} segments decoded", file=sys.stderr)
    words_all.sort(key=lambda w: w["t0"])
    text_parts.sort()
    return words_all, text_parts


# --------------------------------------------------------- parakeet.cpp GPU
def _gpu_free_mb():
    """Per-GPU free VRAM in MB, [] when nvidia-smi is absent/fails."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [int(x.strip()) for x in out.stdout.split() if x.strip()]
    except Exception:
        return []


def recognize_cpp(
    samples,
    segs,
    gguf,
    bin_dir,
    provider=None,
    threads=0,
    timeout_s=900,
):
    """en GPU lane: `parakeet-cli transcribe --json` per contiguous span.

    Starts with the whole file in ONE spawn (production form — works on a
    free card). A failed span is bisected at a VAD-segment boundary and
    retried, so a shared card self-discovers the largest block that fits —
    the compute graph grows superlinearly with audio length (11.7GB for
    1h measured) and can't be budgeted from free VRAM ahead of time.
    Process isolation is the point: libparakeet maps CUDA failures to
    SIGABRT and its exit destructors can abort; inside a disposable child
    that degrades to a nonzero exit code instead of killing the run.

    Word start/end arrive as seconds relative to the span start on the
    80ms encoder grid. VAD segments aren't decoded — the model handles
    hour-scale audio itself — but they gate the no-speech early exit,
    pick bisection cut points at natural pauses, and bin words into
    --format txt parts."""
    cli = Path(bin_dir) / "parakeet-cli"
    for p in (cli, Path(gguf)):
        if not p.exists():
            raise SystemExit(f"error: missing {p} — run scripts/setup.sh --gpu en")
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = (
        str(bin_dir) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    ).rstrip(os.pathsep)
    if provider == "cpu":
        env["PARAKEET_DEVICE"] = "cpu"
    else:
        env.pop("PARAKEET_DEVICE", None)  # auto-pick first GPU device

    words_all, failed = [], 0
    queue = [segs]  # pending seg-lists; pop() takes the most recent append
    with tempfile.TemporaryDirectory(prefix="asr_cpp_") as td:
        wav_path = Path(td) / "blk.wav"
        while queue:
            blk = queue.pop()
            t0, t1 = blk[0]["t0"], blk[-1]["t1"]
            chunk = samples[round(t0 * SR) : round(t1 * SR)]
            with wave.open(str(wav_path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((chunk * 32768.0).astype("<i2").tobytes())
            cmd = [
                str(cli),
                "transcribe",
                "--model",
                str(gguf),
                "--input",
                str(wav_path),
                "--json",
            ]
            if threads > 0:
                cmd += ["--threads", str(threads)]
            try:
                cp = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout_s, env=env
                )
            except subprocess.TimeoutExpired:
                cp = None
            if cp is None or cp.returncode != 0:
                tail = (
                    ""
                    if cp is None
                    else " | ".join((cp.stderr or "").strip().splitlines()[-3:])[:300]
                )
                why = "timeout" if cp is None else f"rc={cp.returncode}"
                if len(blk) > 1:
                    mid = len(blk) // 2
                    queue.append(blk[mid:])
                    queue.append(blk[:mid])
                    print(
                        f"[cpp] span {t0:.0f}-{t1:.0f}s failed ({why}), "
                        f"splitting at seg {mid}: {tail}",
                        file=sys.stderr,
                    )
                else:
                    failed += 1
                    print(
                        f"[cpp] seg {t0:.0f}-{t1:.0f}s failed ({why}), skipped: {tail}",
                        file=sys.stderr,
                    )
                continue
            doc = json.loads(cp.stdout)
            words_all.extend(
                {
                    "w": wd["w"],
                    "t0": t0 + float(wd["start"]),
                    "t1": t0 + float(wd["end"]),
                }
                for wd in doc.get("words", [])
            )
            print(f"[asr] span {t0:.0f}-{t1:.0f}s done", file=sys.stderr)
    if failed == len(segs):
        raise SystemExit("error: every parakeet-cli decode failed")
    if failed:
        print(f"[cpp] {failed}/{len(segs)} segments failed, skipped", file=sys.stderr)
    words_all.sort(key=lambda w: w["t0"])

    text_parts = []
    wi = 0
    for seg in segs:
        parts = []
        while wi < len(words_all) and words_all[wi]["t0"] < seg["t1"]:
            if words_all[wi]["t0"] >= seg["t0"]:
                parts.append(words_all[wi]["w"])
            wi += 1
        if parts:
            text_parts.append((seg["t0"], seg["t1"], " ".join(parts)))
    return words_all, text_parts


# ------------------------------------------------------------- qwen3 GPU
class _DeferredAligner:
    """Lazy forced_aligner stand-in: background-thread load, join at align().

    qwen3_asr's transcribe decodes ASR first and only calls
    forced_aligner.align() at the end, so a thread started at load time gets
    the whole first decode as overlap budget (~1-3 s aligner load hidden)."""

    def __init__(self, path, kwargs):
        import threading

        self._holder = {}

        def _load():
            from qwen_asr.inference.qwen3_forced_aligner import Qwen3ForcedAligner

            try:
                self._holder["m"] = Qwen3ForcedAligner.from_pretrained(path, **kwargs)
            except Exception as e:  # surfaced at first align(), not silently
                self._holder["err"] = e

        self._th = threading.Thread(target=_load, daemon=True)
        self._th.start()

    def align(self, *args, **kwargs):
        self._th.join()
        if "err" in self._holder:
            raise self._holder["err"]
        return self._holder["m"].align(*args, **kwargs)


def _clamp_zero_duration(words, min_s=0.08):
    """Aligner occasionally emits t1<=t0 spans — clamp to one 80ms bin."""
    out = []
    for w in words:
        t0, t1 = w.get("t0"), w.get("t1")
        if t0 is None or t1 is None or t1 > t0:
            out.append(w)
            continue
        w2 = dict(w)
        w2["t1"] = round(float(t0) + min_s, 6)
        out.append(w2)
    return out


# ------------------------------------------------------- qwen3 GPU (mlx, darwin)
def make_qwen_mlx(model_dir, aligner_dir):
    """zh GPU lane on Apple Silicon: mlx-qwen3-asr runtime over the same
    safetensors repos the torch lane uses (~3.4GB unified mem for 1.7B)."""
    from mlx_qwen3_asr import ForcedAligner, load_model

    model, _cfg = load_model(str(model_dir))
    aligner = ForcedAligner(str(aligner_dir))
    return model, aligner


def recognize_qwen_mlx(model, samples, segs, context="", timeout_note=30.0):
    """Decode VAD segments through mlx qwen3-asr + aligner word ts."""
    from mlx_qwen3_asr import transcribe as mlx_transcribe

    asr, aligner = model
    words_all, text_parts = [], []
    for i, seg in enumerate(segs):
        chunk = np.ascontiguousarray(
            samples[round(seg["t0"] * SR) : round(seg["t1"] * SR)],
            dtype=np.float32,
        )
        res = mlx_transcribe(
            (chunk, SR),
            model=asr,
            forced_aligner=aligner,
            language="Chinese",
            context=context,
            return_timestamps=True,
        )
        for s in res.segments or []:
            txt = (s.get("text") or "").strip()
            if txt:
                words_all.append(
                    {
                        "w": txt,
                        "t0": seg["t0"] + float(s["start"]),
                        "t1": seg["t0"] + float(s["end"]),
                    }
                )
        if res.text and res.text.strip():
            text_parts.append((seg["t0"], seg["t1"], res.text.strip()))
        if (i + 1) % 8 == 0 or i + 1 == len(segs):
            print(f"[asr] {i + 1}/{len(segs)} segments decoded", file=sys.stderr)
    words_all.sort(key=lambda w: w["t0"])
    return words_all, text_parts


def make_qwen(
    model_dir,
    aligner_dir,
    dtype_name="bfloat16",
    device_map="cuda:0",
    max_inf_batch=16,
    max_new_tokens=384,
):
    """zh GPU lane: Qwen3-ASR-1.7B + Qwen3-ForcedAligner-0.6B (~6.5 GB VRAM)."""
    import torch
    from qwen_asr import Qwen3ASRModel

    dtype = getattr(torch, dtype_name)
    aligner_kwargs = {"dtype": dtype, "device_map": device_map}
    model = Qwen3ASRModel.from_pretrained(
        str(model_dir),
        dtype=dtype,
        device_map=device_map,
        max_inference_batch_size=int(max_inf_batch),
        max_new_tokens=int(max_new_tokens),
        forced_aligner=None,
        forced_aligner_kwargs=None,
    )
    model.forced_aligner = _DeferredAligner(str(aligner_dir), aligner_kwargs)
    return model


def recognize_qwen(model, samples, segs, batch=4, language="Chinese", context=""):
    """Decode VAD segments through qwen; aligner gives char/word ts."""
    words_all, text_parts = [], []
    for bi in range(0, len(segs), batch):
        idxs = list(range(bi, min(bi + batch, len(segs))))
        audio = [
            (
                np.ascontiguousarray(
                    samples[round(segs[i]["t0"] * SR) : round(segs[i]["t1"] * SR)],
                    dtype=np.float32,
                ),
                SR,
            )
            for i in idxs
        ]
        rs = model.transcribe(
            audio=audio,
            context=context,
            language=language,
            return_time_stamps=True,
        )
        for i, r in zip(idxs, rs, strict=False):
            seg = segs[i]
            if getattr(r, "time_stamps", None) is not None:
                ws = [
                    {
                        "w": it.text,
                        "t0": seg["t0"] + it.start_time,
                        "t1": seg["t0"] + it.end_time,
                    }
                    for it in r.time_stamps.items
                ]
                words_all.extend(_clamp_zero_duration(ws))
            if r.text and r.text.strip():
                text_parts.append((seg["t0"], seg["t1"], r.text.strip()))
        done = min(bi + batch, len(segs))
        print(f"[asr] {done}/{len(segs)} segments decoded", file=sys.stderr)
    words_all.sort(key=lambda w: w["t0"])
    text_parts.sort()
    return words_all, text_parts


# -------------------------------------------------------------------- backend
QWEN_MODEL = "Qwen3-ASR-1.7B"
QWEN_ALIGNER = "Qwen3-ForcedAligner-0.6B"
GGUF_REL = "parakeet-cpp-gguf/tdt-0.6b-v2-f16.gguf"
CPP_BIN_REL = "bin/parakeet-v0.5.0-bin-linux-cuda-x64"


def _default_bin_dir():
    """Newest bundle dir under bin/ matching this platform.

    setup.sh picks the release asset per uname (linux-cuda-x64,
    macos-metal-arm64). Ignore bundles for other platforms so auto falls
    back to sherpa when only a foreign binary is installed."""
    bundles = sorted(p.parent for p in SKILL_ROOT.glob("bin/parakeet-*/parakeet-cli"))
    tag = "macos" if sys.platform == "darwin" else "linux"
    for b in reversed(bundles):  # newest version sort-last
        if tag in b.name:
            return b
    fallback = (
        CPP_BIN_REL.replace("linux-cuda-x64", "macos-metal-arm64")
        if tag == "macos"
        else CPP_BIN_REL
    )
    return SKILL_ROOT / fallback


def _has_accel():
    """GPU present: nvidia-smi on linux, Apple Silicon on macOS (Metal)."""
    if sys.platform == "darwin":
        import platform

        return platform.machine() == "arm64"
    return bool(_gpu_free_mb())


def _cpp_installed(bin_dir, gguf):
    return (Path(bin_dir) / "parakeet-cli").exists() and Path(gguf).exists()


def _qwen_installed(models_dir):
    import importlib.util

    pkg = "mlx_qwen3_asr" if sys.platform == "darwin" else "qwen_asr"
    return (
        importlib.util.find_spec(pkg) is not None
        and (models_dir / QWEN_MODEL).is_dir()
        and (models_dir / QWEN_ALIGNER).is_dir()
    )


def resolve_backend(lang, backend, bin_dir, gguf, models_dir):
    """auto -> installed GPU backend for the lane (files + accelerator), else sherpa."""
    if lang == "en" and backend == "qwen":
        raise SystemExit("error: --backend qwen is zh-only (use sherpa/parakeet_cpp)")
    if lang == "zh" and backend == "parakeet_cpp":
        raise SystemExit("error: --backend parakeet_cpp is en-only (use sherpa/qwen)")
    if backend != "auto":
        return backend
    if not _has_accel():
        return "sherpa"
    if lang == "en" and _cpp_installed(bin_dir, gguf):
        return "parakeet_cpp"
    if lang == "zh" and _qwen_installed(models_dir):
        return "qwen"
    return "sherpa"


def _preflight_gpu(backend, provider):
    free = _gpu_free_mb()
    if backend == "parakeet_cpp":
        if provider == "cpu" or sys.platform == "darwin":
            # darwin: unified memory — no nvidia-smi, the Metal backend and
            # the bisection retry handle budgeting themselves
            return
        if not free:
            raise SystemExit("error: parakeet_cpp needs a GPU (nvidia-smi failed)")
        if max(free) < 3000:
            print(
                f"[warn] parakeet_cpp wants ~3000MB VRAM, {max(free)}MB free",
                file=sys.stderr,
            )
    elif backend == "qwen":
        if sys.platform == "darwin":
            return  # mlx runtime on unified memory — no nvidia-smi
        if not free:
            raise SystemExit("error: qwen needs a CUDA GPU (nvidia-smi failed)")
        if max(free) < 6500:
            raise SystemExit(
                f"error: qwen needs ~6500MB free VRAM, only {max(free)}MB free"
            )


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="audio/video -> SRT/TXT with word-level timestamps"
    )
    ap.add_argument("input", help="audio/video file (wav, mp4, m4a, mp3, ...)")
    ap.add_argument(
        "--lang",
        choices=sorted(LANES),
        required=True,
        help="model lane: en=parakeet-tdt-0.6b-v2, zh=FireRedASR2-CTC/Qwen3-ASR",
    )
    ap.add_argument(
        "--backend",
        choices=["auto", "sherpa", "parakeet_cpp", "qwen"],
        default="auto",
        help="auto: installed GPU backend for the lane, else sherpa (CPU)",
    )
    ap.add_argument("--out", help="output path (default: stdout)")
    ap.add_argument("--format", choices=["srt", "txt"], default="srt")
    ap.add_argument(
        "--models-dir",
        default=os.environ.get("ASR_MODELS") or str(SKILL_ROOT / "models"),
        help="dir holding model subdirs (default: $ASR_MODELS or <skill>/models)",
    )
    ap.add_argument(
        "--model-dir",
        help="explicit sherpa model dir (overrides --models-dir+--lang resolution)",
    )
    ap.add_argument(
        "--vad-model",
        help="silero vad onnx (default: <models-dir>/silero-vad-v5/silero_vad.onnx)",
    )
    ap.add_argument(
        "--gguf",
        help=f"parakeet.cpp gguf (default: <models-dir>/{GGUF_REL})",
    )
    ap.add_argument(
        "--bin-dir",
        help="parakeet-cli bundle dir (default: newest bin/parakeet-* "
        "matching this platform)",
    )
    ap.add_argument(
        "--context",
        default="",
        help="qwen context prompt (e.g. domain vocabulary hints)",
    )
    ap.add_argument(
        "--provider",
        choices=["cpu", "cuda"],
        default=None,
        help="device override — sherpa decode provider; for parakeet_cpp, "
        "cpu forces PARAKEET_DEVICE=cpu. Default: cpu for sherpa, GPU auto "
        "for parakeet_cpp/qwen",
    )
    ap.add_argument("--num-threads", type=int, default=4)
    ap.add_argument("--max-segment-s", type=float, default=30.0)
    ap.add_argument(
        "--vad-threshold",
        type=float,
        default=0.5,
        help="lower (e.g. 0.3) for quiet/noisy audio",
    )
    args = ap.parse_args()

    lane = LANES[args.lang]
    models_dir = Path(args.models_dir)
    gguf = Path(args.gguf) if args.gguf else models_dir / GGUF_REL
    bin_dir = Path(args.bin_dir) if args.bin_dir else _default_bin_dir()
    backend = resolve_backend(args.lang, args.backend, bin_dir, gguf, models_dir)
    print(f"[backend] {backend}", file=sys.stderr)

    vad_model = (
        Path(args.vad_model)
        if args.vad_model
        else models_dir / "silero-vad-v5" / "silero_vad.onnx"
    )
    if not vad_model.exists():
        raise SystemExit(
            f"error: missing vad model: {vad_model} — run scripts/setup.sh"
        )
    if backend == "sherpa":
        if args.model_dir:
            model_dir = Path(args.model_dir)
        else:
            name = lane["dir"]
            model_dir = models_dir / name
        if not model_dir.exists():
            raise SystemExit(
                f"error: missing model dir: {model_dir} — run scripts/setup.sh"
            )
    else:
        _preflight_gpu(backend, args.provider)

    samples, sr = read_audio(args.input)
    samples = _resample_linear(np.asarray(samples, dtype=np.float32), sr)
    total_s = len(samples) / SR
    print(f"[io] {args.input}: {total_s:.1f}s @ {SR}Hz", file=sys.stderr)

    # VAD always runs on the sherpa CPU wheel — it is tiny and the qwen venv
    # has no CUDA sherpa build
    vad = SileroWindows(
        vad_model, threshold=args.vad_threshold, provider="cpu", num_threads=1
    )
    segs = segment(samples, vad, max_segment_s=args.max_segment_s)
    if not segs:
        print("[vad] no speech detected", file=sys.stderr)
        if args.out:
            Path(args.out).write_text("")
        return
    print(f"[vad] {len(segs)} segments", file=sys.stderr)

    if backend == "parakeet_cpp":
        words, text_parts = recognize_cpp(
            samples,
            segs,
            gguf,
            bin_dir,
            provider=args.provider,
            threads=args.num_threads,
        )
    elif backend == "qwen":
        if sys.platform == "darwin":
            model = make_qwen_mlx(models_dir / QWEN_MODEL, models_dir / QWEN_ALIGNER)
            words, text_parts = recognize_qwen_mlx(
                model, samples, segs, context=args.context
            )
        else:
            model = make_qwen(models_dir / QWEN_MODEL, models_dir / QWEN_ALIGNER)
            words, text_parts = recognize_qwen(
                model, samples, segs, context=args.context
            )
    else:
        rec = make_recognizer(
            lane["family"],
            model_dir,
            args.provider or "cpu",
            args.num_threads,
        )
        words, text_parts = recognize(rec, lane["family"], samples, segs)

    cfg = lane["srt"]
    if args.format == "txt":
        body = (
            "\n".join(f"[{t0:>7.2f}-{t1:>7.2f}] {txt}" for t0, t1, txt in text_parts)
            + "\n"
        )
    else:
        if words:
            cues = srt_postproc.words_to_cues(words, cfg)
        else:  # recognizer emitted no word ts — one cue per segment
            cues = srt_postproc.cues_from_utterances(
                [{"start": t0, "end": t1, "text": txt} for t0, t1, txt in text_parts],
                cfg,
            )
        body = srt_postproc.render_srt(cues, cfg)

    if args.out:
        Path(args.out).write_text(body)
        print(f"[out] {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(body)


if __name__ == "__main__":
    main()
