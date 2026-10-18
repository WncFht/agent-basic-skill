---
name: asr
description: 把音频或视频文件转录成 SRT 字幕或带时间戳的 TXT，词级时间戳。当用户想要语音转文字、转录、字幕、SRT 生成时使用——尤其是中文或英文音频 (transcription, subtitles, speech-to-text)。自包含——自行引导 venv 与模型。
---

# ASR 转录

把音频或视频文件转成 `.srt` 字幕 (或带时间戳的 `.txt`),输出词级时间戳。

## 车道

| 语言 | CPU(默认，哪里都能跑)            | GPU(可选，更快)                                                                     |
| ---- | -------------------------------- | ----------------------------------------------------------------------------------- |
| 英语 | sherpa parakeet-tdt-0.6b-v2 fp32 | parakeet.cpp CLI + GGUF f16(~1.3 GB 权重 + ~700 MB 运行时;Linux CUDA / macOS Metal) |
| 中文 | sherpa FireRedASR2-CTC fp32      | Qwen3-ASR-1.7B + ForcedAligner(~6.5 GB 显存;Linux CUDA / Apple Silicon MLX)         |

模型为 fp32 质量优先档。GPU 层的安装与显存要求见 [references/gpu.md](references/gpu.md)。

实测 (en 以 NeMo fp32、zh 以冻结 Qwen 为 oracle 的 micro WER/CER;全口径注记见 [references/metrics.md](references/metrics.md)):

| 车道                         | 速度                                     | 质量          | 足迹                          |
| ---------------------------- | ---------------------------------------- | ------------- | ----------------------------- |
| en sherpa fp32 CPU (nt2)     | ~9 rtfx(55 min 音频 ≈ 6 min)             | WER ~4.3–5.1% | RSS ~1.5–4 GB/进程            |
| en parakeet_cpp CUDA (4070S) | ~43 rtfx(1.2 s spawn 固定税 + ~50x 解码) | WER 1.55%     | VRAM ~2 GB 瞬时 + RSS ~1.7 GB |
| en parakeet_cpp Metal (M4)   | ~27 rtfx(load 1.6 s)                     | WER 1.44%     | 峰值 RSS ~5.3 GB              |
| zh sherpa fp32 CPU (M4)      | ~5.3 rtfx                                | CER 7.62%     | RSS ~1.5–2 GB/进程            |
| zh qwen CUDA (4070S)         | 见 references/gpu.md                     | —             | VRAM ~6.5 GB 常驻             |
| zh qwen MLX (M4 Air)         | ~2.1 rtfx                                | CER 4.28%     | 统一内存 ~5–6 GB              |

zh 口径:micro CER vs 冻结 Qwen oracle(48 段 le120s 门集)——qwen MLX 与 oracle 同权重，4.28% 是实现漂移;M4 Air 上 qwen 是**质量对齐档而非加速档**(比 sherpa 慢 ~2.5x、离 oracle 近 ~1.8x),要速度用 `--backend sherpa`。

GPU 车道又快又准 (解码路径不同，不只是算力差异)——有卡的机器上 en 优先 parakeet_cpp,CPU sherpa 是无卡兜底;Apple Silicon 上 Metal 车道与 CUDA 车道同档质量。

## 安装

每台机器跑一次。建 `.venv/`(sherpa-onnx + numpy) 并把模型拉到本文件旁的 `models/`。需要 `uv`——PATH 上没有时脚本会先尝试用官方安装脚本装到 `~/.local/bin`。

```bash
bash scripts/setup.sh                    # 两条 CPU 车道,自动选下载通道
bash scripts/setup.sh --lang en          # 只要英语
bash scripts/setup.sh --source modelscope
bash scripts/setup.sh --lang vad --gpu zh   # 只装 VAD + 中文 GPU 层
bash scripts/setup.sh --gpu all             # 全部,含两条 GPU 层
```

`--source auto` 探测三个通道 (HuggingFace / ModelScope / GitHub release),然后**逐工件**尝试所有有货的通道、可达者优先——不是全局选一条。下载写 `*.part` 断点续传 (`curl -C -`),按通道侧 API 宣告的 size/sha256 校验后落盘；中断或换通道后重跑，已齐的文件自动跳过。车道模型 (fp32) 只在 HuggingFace(`csukuangfj`/`csukuangfj2` 镜像);ModelScope/GitHub 只覆盖 VAD 与 GPU 工件 (gguf/Qwen)。hf 不可达时用 `HF_ENDPOINT` 指镜像。

网络差的环境有两个 env 开关：`HF_ENDPOINT` (huggingface_hub 惯例，把 hf 通道指到任意兼容 `/api`+`/resolve` 的镜像) 和 `ASR_GH_PROXY` (github.com URL 前缀，如 `https://ghproxy.net/`——github 主页能开但 release CDN 被墙的常见场景)。`--source hf|modelscope|github` 仍可强制单通道。

输入若是 mp4/m4a/mp3/mov/flac 需要 `ffmpeg`;16-bit PCM wav 不需要。

## 转录

```bash
.venv/bin/python3 scripts/transcribe.py INPUT --lang zh --out out.srt
.venv/bin/python3 scripts/transcribe.py INPUT --lang en --format txt
.venv-qwen/bin/python3 scripts/transcribe.py INPUT --lang zh --backend qwen --out out.srt   # Linux
.venv-mlx/bin/python3 scripts/transcribe.py INPUT --lang zh --backend qwen --out out.srt    # macOS
```

用 `python3` 而不是 `python` 起——Linux 上 earlyoom 这类按进程名豁免的 OOM-killer 通常只盖 `python3`,`.venv/bin/python` 的 comm 是 `python` 会裸奔被杀。venv 里 `python3` 软链与 `python` 指向同一解释器。

流水线：解码 → silero VAD 切段 (静音处切，单段 ≤30 s)→ ASR 识别 → 词级时间戳 → 组 cue(最多两行、CJK 感知断行)→ SRT。

值得知道的参数：

- `--backend auto|sherpa|parakeet_cpp|qwen` — auto(默认):本机平台的 GPU 工件装齐且有显卡就走 GPU 车道，否则 sherpa CPU；其他平台的二进制不参与自动选择。GPU 后端与语言绑定 (en→parakeet_cpp,zh→qwen)
- `--model-dir PATH` — 不走 `--lang` 默认，直接用任意兼容的 sherpa-onnx 模型目录
- `--models-dir DIR` 或 `ASR_MODELS` — 挪模型根目录 (默认 `<skill>/models`)
- `--vad-threshold 0.3` — 音量小/噪声大、默认 0.5 漏检语音时调低
- `--provider cpu|cuda` — 设备覆盖：默认 sherpa 走 CPU、GPU 车道自动选卡；`cpu` 可强制 parakeet_cpp 走 CPU 后端
- `--context` — qwen 提示上下文，可喂领域词汇

## 并发跑多个转录

CPU 车道单进程 RSS ~1.5–4 GB，共享机器上 5+ 并发稳定触发 OOM-kill。批量转录走 N 槽 flock 信号量 (fd 锁，进程被杀自动放槽，别用 mkdir 信号量):

```bash
LOCKDIR=$HOME/asr-slots; mkdir -p $LOCKDIR
SLOT=""
while [ -z "$SLOT" ]; do
  for i in 1 2 3; do
    if flock -n "$LOCKDIR/slot$i.lock" -c true 2>/dev/null; then SLOT=$i; break; fi
  done
  [ -z "$SLOT" ] && sleep 20
done
MALLOC_ARENA_MAX=2 flock "$LOCKDIR/slot$SLOT.lock" -c \
  ".venv/bin/python3 scripts/transcribe.py INPUT --lang zh --out out.srt"
```

槽位数按机器内存定 (32 GB RAM 建议 ≤3)。`MALLOC_ARENA_MAX=2` 压 glibc arena 膨胀，同任务省 ~30% RSS。GPU 车道 (parakeet_cpp) 单 spawn 足迹小，瓶颈是显存不是内存——占 GPU 窗按 hutil/本机纪律排队即可,不需要这个信号量。别用 `choom -800` 给转录进程免死金牌：盾不缩需求，只是把 kill 转嫁给别人。

## 常见失败

- `missing model dir` / `missing model file` / `missing tokens` — 对应车道没下载：跑 `setup.sh`。
- `missing .../parakeet-cli` / `missing ...gguf` / `missing ...Qwen3-*` — GPU 工件没装：跑 `setup.sh --gpu en|zh`。
- `qwen needs ~6500MB free VRAM` — 显存不够：`--backend sherpa` 回落 CPU，或等占用释放 (macOS 是统一内存，不查这条)。
- qwen 后端跑不起来先查解释器 — Linux 必须 `.venv-qwen/bin/python3`,macOS 必须 `.venv-mlx/bin/python3`;用 `.venv` 的解释器 auto 只会落到 sherpa。
- `ffmpeg not found` — 装 ffmpeg，或喂 16-bit PCM wav。
- SRT 为空且有 `no speech detected` — VAD 没找到语音：确认音频里真有人说话，或 `--vad-threshold 0.3` 重试。
- 中文输出里出现乱码拉丁串 — FireRedASR2-CTC 的固有行为，不是 bug;语音若实际是英文，换 `--lang en`。
