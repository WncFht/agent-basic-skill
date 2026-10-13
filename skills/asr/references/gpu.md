# GPU 车道

GPU 层是可选加速：转录更快，输出质量不低于 CPU 车道。实测 en 车道 (RTX 4070S)：parakeet_cpp ~43 rtfx / WER 1.55% / VRAM ~2 GB 瞬时 vs sherpa CPU ~9 rtfx / WER ~4.3–5.1%——又快又准是解码路径差异，不只是算力。安装不碰 GPU——没显卡的机器也能跑 `setup.sh --gpu`，只是转录时 auto 会回落 CPU。例外：zh 车道在 Apple Silicon 上是**质量对齐档而非加速档**——M4 Air 实测 qwen MLX ~2.1 rtfx vs sherpa CPU ~5.3 rtfx，但 micro CER 4.28% vs 7.62%（同 oracle 口径）；要速度显式 `--backend sherpa`。

## 车道明细

各车道实测 rtfx/WER/足迹与落选方案记录见 [metrics.md](metrics.md)。

| 车道              | 组件                                                                                                                                                                                                                  | 下载量                 | 显存         | 下载通道                                                                                                        |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ------------ | --------------------------------------------------------------------------------------------------------------- |
| en `parakeet_cpp` | parakeet-cli v0.5.0 bundle(Linux x64 = cuda,macOS arm64 = metal)+ `tdt-0.6b-v2-f16.gguf`                                                                                                                              | ~700 MB + ~1.3 GB      | ~3 GB 瞬时   | bundle 只在 GitHub release(可经 `ASR_GH_PROXY` 前缀走代理);gguf 在 HF + ModelScope (`mudler/parakeet-cpp-gguf`) |
| zh `qwen`         | Linux:`.venv-qwen/`(torch 2.14.0 + transformers 4.57.6 + qwen_asr 0.0.6 + accelerate + qwen_omni_utils);macOS arm64:`.venv-mlx/`(`mlx-qwen3-asr[aligner]`)+ Qwen3-ASR-1.7B + Qwen3-ForcedAligner-0.6B(同一套模型目录) | ~5 GB pip + ~4 GB 模型 | ~6.5 GB 常驻 | HF + ModelScope (`Qwen/`);仅 Linux CUDA / Apple Silicon MLX                                                     |

## 安装

```bash
bash scripts/setup.sh --gpu en          # parakeet-cli → bin/(按平台选 cuda/metal bundle),gguf → models/parakeet-cpp-gguf/
bash scripts/setup.sh --gpu zh          # 两个 Qwen 模型 → models/;Linux 建 .venv-qwen/,macOS arm64 建 .venv-mlx/(Intel Mac 无 qwen 运行时,跳过)
bash scripts/setup.sh --gpu all         # 两层都装
bash scripts/setup.sh --lang vad --gpu zh   # 跳过 CPU 车道模型,只装 GPU zh + VAD
```

en bundle 按 `uname -s`/`uname -m` 选:Linux x86_64 → `bin-linux-cuda-x64`,macOS arm64 → `bin-macos-metal-arm64`;其它组合没有 GPU 车道，`--gpu en` 直接报错 (sherpa CPU 兜底)。`--gpu zh` 拉同一对模型目录 (Qwen3-ASR-1.7B + Qwen3-ForcedAligner-0.6B),按平台建运行时:Linux → `.venv-qwen`(torch CUDA),macOS arm64 → `.venv-mlx`(mlx-qwen3-asr——Qwen3-ASR 的 MLX 重写，直接读原版 safetensors，词时间戳由原生 MLX ForcedAligner 出，实测与官方实现对齐 MAE ~6ms);Intel Mac 无任何运行时，跳过。

GitHub release 资产不可达的机器装不了 `--gpu en`(bundle 只在那里)——除非设 `ASR_GH_PROXY` 走代理前缀;`--gpu zh` 不受影响 (Qwen 模型 HF/ModelScope 都有)。`--source github` 与 `--gpu` 互斥——gguf 和 Qwen 模型不在 GitHub 上。

## 转录

```bash
# en GPU:parakeet-cli 是纯二进制 subprocess,用哪个 python 跑都行
.venv/bin/python3 scripts/transcribe.py INPUT --lang en --backend parakeet_cpp --out out.srt

# zh GPU:必须用装了对应运行时的解释器——Linux 是 .venv-qwen,macOS 是 .venv-mlx
.venv-qwen/bin/python3 scripts/transcribe.py INPUT --lang zh --backend qwen --out out.srt   # Linux
.venv-mlx/bin/python3 scripts/transcribe.py INPUT --lang zh --backend qwen --out out.srt    # macOS arm64
```

## `--backend` 语义

`auto`(默认) 按车道检查：GPU 工件齐了且能看到加速硬件就走 GPU 后端，否则 sherpa CPU。硬件检测——Linux 查 `nvidia-smi`,macOS 认 Apple Silicon (arm64,Metal 必在)。工件齐的定义——en:`bin/parakeet-*/parakeet-cli` + gguf 都在 (多个 bundle 时选本平台的);zh:当前解释器能 import 对应运行时 (Linux `qwen_asr`,macOS `mlx_qwen3_asr`) 且两个模型目录都在。

显式 `--backend` 不做回落：工件缺失直接报错，提示跑 `setup.sh --gpu`。后端与语言绑定写死——`--lang zh --backend parakeet_cpp` 和 `--lang en --backend qwen` 都报错。

## 显存

转录前用 `nvidia-smi` 查空闲显存 (macOS 是统一内存，跳过检查——Metal 后端自行预算，撑不住时还有二分重试):

- `qwen` 需要 ≥6500 MB，不够**直接拒绝启动**——比解码到一半 OOM 强。
- `parakeet_cpp` 需要 ~3000 MB，不够只警告——占用是瞬时的，挤一挤可能进得去。
- `--provider cpu` 让 parakeet_cpp 强制 CPU 后端 (`PARAKEET_DEVICE=cpu`),跳过显存检查。

macOS 实测 (M4 Air 16 GB,42 段 50.6 min,NeMo oracle 口径):Metal f16 ~26.6 rtfx / WER 1.44%(与 CUDA 车道 1.55% 同档)/ 峰值 RSS ~5.3 GB——16 GB 机器上避开重负载时段跑。zh 车道同机实测 (48 段 zh gate,Qwen oracle 口径):qwen MLX fp16 ~2.1 rtfx / CER 4.28% / ~5-6 GB 统一内存，sherpa firered ~5.3 rtfx / CER 7.62%——详见仓库 `results/tasks/m1-mac-qwen-bench.md`;投机解码 (0.6B 草稿) 实测更慢，别用。

## 实现要点 (为什么会这样设计)

- **parakeet_cpp 失败二分自适应 decode。** 先整文件一次子进程 (生产形态——空卡可行);失败的片段在 VAD 段边界二分重试，共享卡上自动发现放得下的最大块——计算图随音频长度超线性涨 (1 小时实测 ~11.7 GB)，没法从空闲显存预先算准。libparakeet 把 CUDA 错误映射成 SIGABRT、退出析构也可能 abort——子进程隔离让这些只变成非零退出码，而不是整跑崩掉；进程退出显存全释放。模型自己处理小时级音频，VAD 段不送进去，只用于无语音早退、选二分切点和 txt 分句。
- **词时间戳 80ms 栅格。** parakeet-cli `--json` 给的 `words[].start/end` 是 TDT duration head 输出、相对块起点的秒，加块偏移进 SRT。
- **qwen 的 aligner 后台加载。** ForcedAligner ~1-3 s 加载放在线程里，藏在第一段解码后面；`transcribe` 结束才 join。aligner 偶尔给 `t1<=t0` 的零时长词，钳到 80ms。
- **transformers 锁 4.57.6。** 5.x 与 qwen_asr 0.0.6 不兼容，`.venv-qwen` 里别升级 transformers。

## 常见失败

- `parakeet-cli info failed` / 每段都崩 — bundle 不完整或驱动太老；bundle 自带 cudart13/cublas,系统只需 NVIDIA 驱动。
- `qwen needs a CUDA GPU (nvidia-smi failed)` — 无卡或驱动没装；用 `--backend sherpa` (macOS 不走 nvidia-smi，不会报这条)。
- `.venv-qwen` 里 `import qwen_asr` 失败 (或 `.venv-mlx` 里 `import mlx_qwen3_asr` 失败) — 转录用错了解释器;qwen 后端 Linux 必须 `.venv-qwen/bin/python`,macOS 必须 `.venv-mlx/bin/python`。
