#!/usr/bin/env python3
"""视频选帧工具：接触表时间轴 / 字幕带安静度扫描 / 定点抽帧 / 去烧录字幕合成。

子命令：
  timeline  均匀采样拼接触表，建立全片 slide 时间轴
  scan      在目标时间窗内按字幕带 (band) 的 jpg 体积打分，找无硬字幕的干净时刻
  grab      在给定时间戳抽全尺寸帧（可裁剪、可拼候选表）
  desub     静止窗口内合成净帧（median / auto / rebuild 三档，见下）

字幕带扫描的原理：烧录字幕经过的带状区域，有字时 jpg 体积明显变大
（实测干净带 ~7-12KB，有字幕 >=15KB）。先 scan 拿安静时刻，再 grab 抽帧。

desub 三档：
  median   ffmpeg tmedian 逐像素时域中位数。--radius 缺省时覆盖全窗口采样
           （不是只合成中心 2R+1 帧）；字幕稀疏（覆盖率 <~50%）时最快够用。
  auto     先量化带内字幕覆盖率再分派：>=3 帧近无字幕 -> 最净帧中位数；
           近连续字幕 -> 逐像素重建（离背景近的样本均值 + 残留块擦除）。
           需 numpy：`uv run --with numpy python3 frames.py desub --mode auto ...`
  rebuild  强制逐像素重建（跳过 clean-frames 快路径）。

为什么要先测覆盖率：白填充 + 黑描边字幕的两极亮度同为离群值，覆盖率 >50% 时
中位数/主导类都会撞上其中一极——必须先量化，不能盲试。auto 会打印覆盖率
与所选路径；结果发糊说明窗口内有滚动/翻页，换窗口（窗口不能跨 slide 边界）。

用法：
  python3 frames.py timeline video.mp4 --step 30 --out sheets/
  python3 frames.py scan video.mp4 --start 22:53 --end 25:18 --band auto
  python3 frames.py scan video.mp4 --start 22:53 --end 25:18 \
      --band 1400:90:300:915 --step 1
  python3 frames.py grab video.mp4 --at 25:15,25:17 \
      --crop 1660:945:10:60 --sheet --out assets/candidates/
  python3 frames.py desub video.mp4 --start 0:56 --end 1:18 \
      --crop 1130:600:415:338 --band 0:520:1130:600 --mode auto --out clean.png

时间格式支持 SS、MM:SS、HH:MM:SS（可带小数秒）。
--crop 为 ffmpeg crop 的 w:h:x:y（作用于输入帧，w/h 须偶数）；scan 的
--band 同格式（输入帧上的探测带）。desub 的 --band 语义不同：输出帧内的
字幕矩形 x0:y0:x1:y1（--crop 之后的坐标系）。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def parse_t(s):
    parts = [float(p) for p in s.split(":")]
    return sum(p * 60**i for i, p in enumerate(reversed(parts)))


def fmt_t(t):
    """整数秒给 HH:MM:SS；带小数保留毫秒（片尾边界探测要亚秒）。"""
    ms = round(t * 1000)
    s, rem = divmod(ms, 1000)
    base = f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{base}.{rem:03d}" if rem else base


def norm_crop(s):
    """解析 w:h:x:y 并校验：w/h 为奇数时 ffmpeg 会静默圆整，
    rawvideo 管道按声明尺寸读就逐帧错位——直接拒掉比出烂图好。"""
    try:
        w, h, x, y = [int(v) for v in s.split(":")]
    except ValueError:
        sys.exit(f"crop/band 需要 w:h:x:y 四个整数，收到：{s!r}")
    if w % 2 or h % 2:
        sys.exit(f"crop/band 的 w、h 必须为偶数（ffmpeg 会静默圆整致管道错位）: {s!r}")
    return w, h, x, y


def grab_one(video, t, out_path, vf=None):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-frames:v", "1", "-q:v", "2", str(out_path)]
    subprocess.run(cmd, check=True)
    return out_path.stat().st_size


def probe_size(video):
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            video,
        ],
        capture_output=True,
        text=True,
    )
    w, h = r.stdout.strip().split(",")
    return int(w), int(h)


def duration(video):
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            video,
        ],
        capture_output=True,
        text=True,
    )
    return float(r.stdout.strip())


def norm_tile(s):
    """--tile 接受 '5x4' 或单整数 '5'（后者等价 5x5）。"""
    if "x" in s:
        cols, rows = s.split("x")
    else:
        cols = rows = s
    try:
        cols, rows = int(cols), int(rows)
    except ValueError:
        sys.exit(f"--tile 需要 NxM 或单个整数（如 5x4 / 5），收到：{s!r}")
    if cols < 1 or rows < 1:
        sys.exit(f"--tile 行列必须 >=1，收到：{s!r}")
    return f"{cols}x{rows}", cols * rows


def _import_np():
    try:
        import numpy as np
    except ImportError:
        sys.exit("此模式需要 numpy：uv run --with numpy python3 frames.py <原命令>")
    return np


def sample_frames(video, t0, t1, fps, crop=None, gray=False):
    """ffmpeg 采窗内帧为 numpy 数组 (n,H,W[,3])。crop 为已校验的 (w,h,x,y)。"""
    np = _import_np()
    vf = f"fps={fps}"
    if crop:
        w, h, x, y = crop
        vf += f",crop={w}:{h}:{x}:{y}"
    else:
        w, h = probe_size(video)
    pix = "gray" if gray else "rgb24"
    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-ss",
        f"{t0:.2f}",
        "-to",
        f"{t1:.2f}",
        "-i",
        video,
        "-vf",
        vf,
        "-f",
        "rawvideo",
        "-pix_fmt",
        pix,
        "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    ch = 1 if gray else 3
    n = len(raw) // (w * h * ch)
    if n < 1:
        sys.exit("窗口内未采到帧——检查 --start/--end 与 --crop")
    arr = np.frombuffer(raw[: n * w * h * ch], dtype=np.uint8)
    return arr.reshape(n, h, w) if gray else arr.reshape(n, h, w, 3)


def cmd_timeline(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    dur = duration(a.video)
    n = int(dur // a.step) + 1
    tile, per = norm_tile(a.tile)
    sheets = (n + per - 1) // per
    vf = f"fps=1/{a.step},scale={a.width}:-1,tile={tile}"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            a.video,
            "-vf",
            vf,
            str(out / "sheet_%02d.jpg"),
        ],
        check=True,
    )
    print(
        f"{dur / 60:.1f}min, {n} samples -> {sheets} sheet(s), "
        f"每张 {per} 格，格间距 {a.step}s -> {out}/sheet_XX.jpg"
    )
    if dur > 1800:
        print("提示：长视频 timeline 可放后台与 ASR 转写并行跑。", file=sys.stderr)


def detect_band(video, t0, t1, step):
    """自动定带：窗口采样帧底部 45% 做逐行时域 std，字幕行方差远高于静止
    背景；取方差最大的连续段，横向取中间 90% 宽。返回 w:h:x:y 或 None。"""
    np = _import_np()
    vw, vh = probe_size(video)
    top = int(vh * 0.55)  # 只探底部 45%
    arr = sample_frames(video, t0, t1, max(0.5, 1.0 / step), gray=True)
    std = arr[:, top:, :].astype(np.float32).std(axis=0).mean(axis=1)  # 逐行
    k = 7
    sm = np.convolve(std, np.ones(k) / k, mode="same")
    floor = np.median(sm)
    thr = max(floor * 2.0, floor + 6.0)
    hot = sm > thr
    if not hot.any():
        print(
            f"auto-band: 底部 45% 无显著时域变化（row-std 峰值 {sm.max():.1f}），"
            "该窗口可能无烧录字幕",
            file=sys.stderr,
        )
        return None
    best = None
    start = None
    for i, v in enumerate(hot):
        if v and start is None:
            start = i
        elif not v and start is not None:
            seg = (start, i)
            if best is None or seg[1] - seg[0] > best[1] - best[0]:
                best = seg
            start = None
    if start is not None:
        seg = (start, len(hot))
        if best is None or seg[1] - seg[0] > best[1] - best[0]:
            best = seg
    pad = 10
    y0 = max(top + best[0] - pad, 0)
    y1 = min(top + best[1] + pad, vh)
    x0 = int(vw * 0.05)
    w = int(vw * 0.9)
    h = y1 - y0
    w -= w % 2
    h -= h % 2
    band = f"{w}:{h}:{x0}:{y0}"
    print(
        f"auto-band -> {band}（行方差基线 {floor:.1f}，峰 {sm.max():.1f}；"
        "建议先抽一张该带帧目检确认）",
        file=sys.stderr,
    )
    return band


def cmd_scan(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0, t1 = parse_t(a.start), parse_t(a.end)
    for stale in out.glob("band_*.jpg"):
        stale.unlink()
    band = a.band
    if band == "auto":
        band = detect_band(a.video, t0, t1, a.step)
        if not band:
            sys.exit(
                "auto-band 未定位到字幕带——确认该窗口确有烧录字幕，或手动给 --band"
            )
    norm_crop(band)
    # select 单 pass：按真实 pts 每 step 秒选一帧，showinfo 打出精确时间戳。
    # 不能用 fps 滤镜——VFR 源会选错显示帧，扫到的时间戳和 -ss 抽帧对不上。
    vf = (
        f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{a.step:g})'"
        f",crop={band},showinfo"
    )
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "info",
            "-ss",
            f"{t0:.2f}",
            "-t",
            f"{t1 - t0:.2f}",
            "-i",
            a.video,
            "-vf",
            vf,
            "-fps_mode",
            "passthrough",
            "-q:v",
            "2",
            str(out / "band_%05d.jpg"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    times = re.findall(r"pts_time:([0-9.]+)", r.stderr)
    files = sorted(out.glob("band_*.jpg"))
    if not files or len(times) < len(files):
        sys.exit("no frames extracted")
    rows = [(t0 + float(times[i]), f.stat().st_size) for i, f in enumerate(files)]
    sizes = [s for _, s in rows]
    lo, hi = min(sizes), max(sizes)
    # 干净时刻是体积下凹的离群点（字幕文字显著增加细节 → jpg 变大）。
    # 以最小值为基线；窗口内全程有/无字幕时比值趋平，此时提示换窗。
    thr = lo * 1.5
    if hi < lo * 1.8:
        print(
            f"注意：band 体积起伏小 ({lo}~{hi} B)，该窗口可能全程有/无字幕——换窗口或人工看图"
        )
    print(f"baseline (min) ≈ {lo} B; 安静判定：<= {int(thr)} B")
    print(f"{'time':>10} {'bytes':>8}  quiet")
    for t, s in rows:
        q = "*" if s <= thr else " "
        print(f"{fmt_t(t):>10} {s:>8}  {q}")
    quiet = [t for t, s in rows if s <= thr]
    if quiet:
        print("安静时刻 (靠后优先):", ", ".join(fmt_t(t) for t in quiet[-8:]))


def cmd_grab(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.crop:
        norm_crop(a.crop)
    vf = f"crop={a.crop}" if a.crop else None
    made = []
    for s in a.at.split(","):
        t = parse_t(s.strip())
        p = out / f"f_{fmt_t(t).replace(':', '-')}.jpg"
        grab_one(a.video, t, p, vf=vf)
        made.append(p)
        print(f"{fmt_t(t)} -> {p}")
    if a.sheet and len(made) > 1:
        cols = min(len(made), 5)
        # 每路先统一到 W x H 字面尺寸，再用预算好的像素偏移排版。
        # 不能用 layout 表达式 N*w0_N*h0：ffmpeg 9 的 xstack 里 w0/h0 求值为 1，
        # 全部 tile 塌缩叠在原点（症状：candidates.jpg 只有单 tile 大小）。
        vw, vh = probe_size(a.video)
        if a.crop:
            vw, vh = norm_crop(a.crop)[:2]
        tw = a.width
        th = round(vh * tw / vw / 2) * 2  # 偶数高
        inputs = [x for p in made for x in ("-i", str(p))]
        fc = "".join(f"[{i}:v]scale={tw}:{th}[s{i}];" for i in range(len(made)))
        fc += "".join(f"[s{i}]" for i in range(len(made)))
        layout = "|".join(
            f"{(i % cols) * tw}_{(i // cols) * th}" for i in range(len(made))
        )
        fc += f"xstack=inputs={len(made)}:layout={layout}[o]"
        sheet = out / (a.sheet_name or "candidates.jpg")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                *inputs,
                "-filter_complex",
                fc,
                "-map",
                "[o]",
                "-frames:v",
                "1",
                str(sheet),
            ],
            check=True,
        )
        # 自检：画布必须大于单 tile，否则布局塌缩一眼可辨
        sw, sh = probe_size(str(sheet))
        rows = (len(made) + cols - 1) // cols
        if sw <= tw or sh < th * rows:
            print(
                f"警告：sheet 尺寸 {sw}x{sh} 异常（预期 ~{cols * tw}x{rows * th}），"
                "xstack 布局可能塌缩——逐张读候选帧",
                file=sys.stderr,
            )
        print(f"contact sheet {sw}x{sh} ({len(made)} tiles) -> {sheet}")


def _tmedian(video, t0, t1, fps, radius, crop, out):
    """ffmpeg tmedian：radius 缺省 = 全窗口 (n-1)//2，输出即全采样中位数。"""
    span = t1 - t0
    n_in = max(1, int(span * fps))
    r = (n_in - 1) // 2 if radius is None else min(radius, (n_in - 1) // 2)
    n_out = n_in - 2 * r
    mid = max(0, n_out // 2)  # tmedian 输出 k 覆盖 [k, k+2R]，取中位帧使覆盖居中
    vf = f"fps={fps},tmedian=radius={r},select='eq(n\\,{mid})'"
    if crop:
        vf += f",crop={crop}"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{t0:.2f}",
            "-to",
            f"{t1:.2f}",
            "-i",
            video,
            "-vf",
            vf,
            "-frames:v",
            "1",
            out,
        ],
        check=True,
    )
    print(
        f"{fmt_t(t0)}--{fmt_t(t1)}: {n_in} 帧采样，radius={r} "
        f"(覆盖 {min(2 * r + 1, n_in)}/{n_in} 帧) -> {out}"
    )


def _desub_np(video, t0, t1, fps, crop, band, blanks, out, force_rebuild):
    """numpy 管线：全帧去离群中位数合成；band 内先测覆盖率再分派。

    分派逻辑（两次实战收敛出的规则）：
      - 带内逐帧 ink 率有 >=3 帧 <3% -> clean-frames：直接对最净的 <=8 帧
        取中位数，背景与内容都无损。ink = 反背景极端像素（亮底上的暗块/
        暗底上的亮块，空间上就是字幕形）+ 朝反极方向偏离时域中位数 >40
        的像素（抓中间调字幕；逐像素多数派是墨迹时 dev=0 漏检，但反极
        项仍命中，gap 帧也不会被反向误报）。
      - 否则逐像素 rebuild：保留「离带内背景标量 B 比离反极更近」的样本
        取均值（暗底本身就是近极端值，非极端区间判据会把真背景也拒了）；
        证据不足填 B。
      - 收尾：孤立反极碎点清理 + 残留大实心块擦除
        （>2500px 且填充率 >0.3 的块是气泡字幕残影，真实内容是小连通域）。
    """
    np = _import_np()
    arr = sample_frames(video, t0, t1, fps, crop=crop)
    n, h, w, _ = arr.shape
    if n < 3:
        sys.exit(f"窗口只采到 {n} 帧，加大窗口或 --fps")

    # 全幅合成：先丢与整体中位数偏差最大的 25% 帧（翻页/过渡帧），再取中位数
    med = np.median(arr, axis=0).astype(np.int16)
    dev = np.abs(arr.astype(np.int16) - med).mean(axis=(1, 2, 3))
    keep = dev <= np.percentile(dev, 75)
    sel = arr[keep]
    comp = np.median(sel, axis=0).astype(np.uint8)
    print(f"composite: kept {sel.shape[0]}/{n} frames (dev<=p75)")

    if band:
        x0, y0, x1, y1 = band
        bz = arr[:, y0:y1, x0:x1].astype(np.float32)  # n x bh x bw x 3
        blum = bz.mean(axis=3)
        tmed = np.median(blum, axis=0)
        b = float(np.median(blum))
        light = b > 128
        anti = (blum < 60) if light else (blum > 195)
        devi = (np.abs(blum - tmed[None]) > 40) & (
            (blum < tmed[None]) if light else (blum > tmed[None])
        )
        ink = (anti | devi).mean(axis=(1, 2))
        print(
            f"band ink coverage: min {ink.min():.3f}, median "
            f"{np.median(ink):.3f}, frames<3%: {(ink < 0.03).sum()}"
        )
        clean = np.where(ink < 0.03)[0]
        if not force_rebuild and clean.size >= 3:
            seli = clean[np.argsort(ink[clean])[: min(8, clean.size)]]
            zone_out = np.median(arr[seli][:, y0:y1, x0:x1], axis=0).astype(np.uint8)
            print(
                f"clean-frames path: median of frames {seli.tolist()} "
                f"(ink<={ink[seli].max():.3f})"
            )
        else:
            zone_out = _rebuild_band(np, bz, blum)

        # 残留实心块擦除：重建后剩下的「反色大实心块」是字幕残影（气泡底），
        # 真实内容（字符、坐标轴）是小连通域。反色 = 与带内主导背景极相反：
        # 亮背景上找暗块，暗背景上找亮块；填回主导极。
        zl = zone_out.astype(np.int16).mean(axis=2)
        zb = float(np.median(zl))
        resid = (zl < 80) if zb > 128 else (zl > 175)
        lab, ncomp = _label_components(np, resid)
        erased = 0
        for i in range(1, ncomp + 1):
            ys, xs = np.where(lab == i)
            a_ = ys.size
            if a_ > 2500:
                fill = a_ / ((np.ptp(ys) + 1) * (np.ptp(xs) + 1))
                if fill > 0.3:
                    zone_out[lab == i] = zb
                    erased += 1
        if erased:
            print(f"residual blob erase: {erased} blobs")
        comp[y0:y1, x0:x1] = zone_out

    if blanks:
        for b in blanks.split(","):
            bx0, by0, bx1, by1 = [int(v) for v in b.split(":")]
            pole = 255 if comp[by0:by1, bx0:bx1].astype(np.int16).mean() > 128 else 0
            comp[by0:by1, bx0:bx1] = pole
            print(f"blanked x[{bx0}:{bx1}] y[{by0}:{by1}] -> {pole}")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-i",
            "-",
            "-frames:v",
            "1",
            out,
        ],
        input=comp.tobytes(),
        check=True,
    )
    print(f"-> {out}")


def _rebuild_band(np, bz, blum):
    """逐像素重建：保留离背景标量 B 比离反极端更近的样本取均值。

    B = 全带时序中位数标量（背景本色，亮底 ~238、暗底 ~40 都行）。
    墨迹像素总偏向反极（黑描边→0 / 白字→255），按「离谁近」二分给样本，
    比「非极端区间 (60~240)」更通用——暗底/亮底本身就是近极端值时仍正确。
    """
    n = bz.shape[0]
    b = float(np.median(blum))
    light = b > 128
    anti_pole = 0.0 if light else 255.0
    keep = np.abs(blum - b) < np.abs(blum - anti_pole)
    kcnt = keep.sum(axis=0)
    ksum = (bz * keep[..., None]).sum(axis=0)
    kmean = ksum / np.maximum(kcnt[..., None], 1)
    out = np.broadcast_to(np.float32(b), kmean.shape).copy()
    has = kcnt >= max(3, int(0.2 * n))
    out[has] = kmean[has]
    # 孤立反极碎点清理：亮底上的暗碎点 / 暗底上的亮碎点是描边残屑
    res = out.mean(axis=2)
    resid = (res < 60) if light else (res > 195)
    h, w = res.shape
    pad = np.pad(resid.astype(np.int32), 1)
    nbr = (
        sum(pad[dy : dy + h, dx : dx + w] for dy in (0, 1, 2) for dx in (0, 1, 2))
        - resid
    )
    specks = int((resid & (nbr <= 3)).sum())
    out[resid & (nbr <= 3)] = b
    print(
        f"rebuild path: {has.mean():.3f} px from kept-samples "
        f"(bg={'light' if light else 'dark'}), cleaned {specks} specks"
    )
    return out.astype(np.uint8)


def _label_components(np, m):
    """4-连通域标记（纯 numpy BFS，band 尺寸下够用）。"""
    h, w = m.shape
    lab = np.zeros((h, w), dtype=np.int32)
    comp = 0
    for y in range(h):
        for x in range(w):
            if m[y, x] and not lab[y, x]:
                comp += 1
                lab[y, x] = comp
                stack = [(y, x)]
                while stack:
                    cy, cx = stack.pop()
                    for ny, nx in (
                        (cy - 1, cx),
                        (cy + 1, cx),
                        (cy, cx - 1),
                        (cy, cx + 1),
                    ):
                        if (
                            0 <= ny < h
                            and 0 <= nx < w
                            and m[ny, nx]
                            and not lab[ny, nx]
                        ):
                            lab[ny, nx] = comp
                            stack.append((ny, nx))
    return lab, comp


def cmd_desub(a):
    t0, t1 = parse_t(a.start), parse_t(a.end)
    if a.crop:
        norm_crop(a.crop)
    band = None
    if a.band:
        try:
            x0, y0, x1, y1 = [int(v) for v in a.band.split(":")]
        except ValueError:
            sys.exit(
                f"desub --band 需要输出帧内矩形 x0:y0:x1:y1（--crop 后坐标），"
                f"收到：{a.band!r}"
            )
        band = (x0, y0, x1, y1)
    if a.mode == "median" and band is None and not a.blanks:
        _tmedian(a.video, t0, t1, a.fps, a.radius, a.crop, a.out)
        print(
            "提示：median 假设窗口内画面静止且字幕覆盖率 <50%；结果发糊/留残影"
            "说明有滚动或字幕过密，换窗口或改用 --mode auto（需 numpy）。",
            file=sys.stderr,
        )
        return
    _desub_np(
        a.video,
        t0,
        t1,
        a.fps,
        norm_crop(a.crop) if a.crop else None,
        band,
        a.blanks,
        a.out,
        force_rebuild=(a.mode == "rebuild"),
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("timeline", help="均匀采样接触表")
    p.add_argument("video")
    p.add_argument("--step", type=int, default=30)
    p.add_argument("--width", type=int, default=400)
    p.add_argument("--tile", default="5x5")
    p.add_argument("--out", default="sheets")
    p.set_defaults(f=cmd_timeline)

    p = sub.add_parser("scan", help="字幕带安静度扫描")
    p.add_argument("video")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument(
        "--band",
        default="auto",
        help="crop w:h:x:y 探测带（输入帧坐标），或 auto 自动定带",
    )
    p.add_argument("--step", type=float, default=1.0)
    p.add_argument("--out", default="bandscan")
    p.set_defaults(f=cmd_scan)

    p = sub.add_parser("grab", help="定点抽帧")
    p.add_argument("video")
    p.add_argument("--at", required=True, help="逗号分隔时间戳（支持小数秒）")
    p.add_argument("--crop", default=None, help="crop w:h:x:y，w/h 须为偶数")
    p.add_argument("--out", default="candidates")
    p.add_argument("--sheet", action="store_true", help="多帧时拼一张候选表")
    p.add_argument(
        "--sheet-name",
        default=None,
        help="拼图文件名（默认 candidates.jpg；同目录多次 --sheet 时用不同名防覆盖）",
    )
    p.add_argument("--width", type=int, default=400)
    p.set_defaults(f=cmd_grab)

    p = sub.add_parser("desub", help="静止窗口去烧录字幕合成净帧")
    p.add_argument("video")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--fps", type=float, default=2.0, help="窗口内采样帧率")
    p.add_argument(
        "--radius",
        type=int,
        default=None,
        help="tmedian 半径（仅 mode=median；缺省覆盖全窗采样）",
    )
    p.add_argument(
        "--mode",
        choices=["auto", "median", "rebuild"],
        default="auto",
        help="auto=测覆盖率分派（默认）; median=纯 ffmpeg 中位数; rebuild=强制逐像素重建",
    )
    p.add_argument("--crop", default=None, help="内容区裁剪 w:h:x:y（输入帧坐标）")
    p.add_argument(
        "--band",
        default=None,
        help="字幕矩形 x0:y0:x1:y1（--crop 后输出帧坐标）；不给则整幅中位数",
    )
    p.add_argument(
        "--blanks",
        default=None,
        help="额外抹除矩形 x0:y0:x1:y1,...（水印/工具栏；填局部主导极）",
    )
    p.add_argument("--out", required=True, help="输出图片路径（png/jpg）")
    p.set_defaults(f=cmd_desub)

    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
