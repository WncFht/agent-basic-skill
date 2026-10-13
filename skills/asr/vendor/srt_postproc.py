# Vendored from asr-opt/harness/srt_postproc.py — pure stdlib, sync manually.
"""srt_postproc.py — subtitle cue building + line wrapping. Pure stdlib.

Break-point quality model: every candidate boundary (between two tokens, or
between two chars for zh) gets a score; higher is a better place to split.
Used in three places:

- words_to_cues(): when a hard limit trips (max_dur_s / max chars), look back
  within the cue for the best boundary instead of splitting mid-word.
- wrap_zh(): pick the best in-window break for the second line, balanced so
  the last line is never a 1-2 char orphan.
- CPS enforcement: cues denser than cfg max_cps are split at the best
  boundary nearest the middle.

jieba is used opportunistically for zh word boundaries when importable
(cfg key "jieba": false disables); heuristics below are the fallback.
"""

# --------------------------------------------------------------- char classes

SENT_END = tuple(".?!。？！…\"'”’")  # break cue after these (word suffix check)
ZH_PUNCT = "，。！？；：、—…"
PUNCT_ONLY = frozenset(".,!?;:%)”’\"'、。，！？；：")

_SENT_P = frozenset("。！？!?…")  # '.' handled specially (decimal point)
_CLAUSE_P = frozenset("，、；：—–,;:")  # break cue lazily at clause punct
_OPEN_P = frozenset("“‘「『（([<《")
_CLOSE_P = frozenset("”’」』）)]>》")

# break AFTER these is usually safe (particles / closed subject words)
_AFTER_OK = frozenset("的了呢吗吧啊呀嘛啦哦噢哇呐过着在是我你他她它这那个又都就也还")
# break BEFORE these is bad — they bind to the previous char
_BIND_LEFT = frozenset("们的了着过吗呢吧啊呀嘛啦")
# break BEFORE these is mildly bad — they bind to what follows
_BIND_RIGHT = frozenset("是在把被让对从向跟和与或及但而且因如若虽既不没别请最很更")
# break AFTER these is bad — prefix chars bind rightward (第 | 三，老 | 王)
_PREFIX = frozenset("第老阿每各")

_NO_BREAK = -1e6
_JIEBA_OK, _JIEBA_NO = 35.0, -25.0  # at / not-at a jieba token edge
_GAP_W, _GAP_CAP = 140.0, 0.5  # pause bonus: 0.5s -> +70
_LOOKBACK = 12  # tokens to search when a limit trips


_jieba_cache = None


def _jieba_mod():
    """Import jieba lazily; cache False when unavailable."""
    global _jieba_cache  # noqa: PLW0603 — module-level lazy-import cache is the idiom
    if _jieba_cache is None:
        try:
            import jieba

            _jieba_cache = jieba
        except ImportError:
            _jieba_cache = False
    return _jieba_cache or None


def jieba_bounds(text):
    """Char indices i where text[:i] | text[i:] is a jieba token edge.
    Returns None when jieba is not importable."""
    jb = _jieba_mod()
    if jb is None or not text:
        return None
    bounds, pos = set(), 0
    for tok in jb.cut(text):
        pos += len(tok)
        bounds.add(pos)
    bounds.discard(len(text))
    return bounds


def pair_score(lc, rc, gap_s=0.0):
    """Score a boundary between adjacent chars lc|rc (+inter-token pause)."""
    if not lc or not rc:
        return _NO_BREAK
    if lc.isascii() and rc.isascii():
        if lc.isalnum() and rc.isalnum():
            return _NO_BREAK  # inside latin word / digit run
        if lc.isdigit() and rc in ".,:%-":
            return _NO_BREAK  # 3. 1, 12: 50%
        if rc.isdigit() and lc in ".,:$#€£¥":
            return _NO_BREAK  # .5 $9
        if (lc.isalpha() and rc in "'’-") or (rc.isalpha() and lc in "'’-"):
            return _NO_BREAK  # don'|t, a|-b
    s = 0.0
    if (lc == "." and not rc.isdigit()) or lc in _SENT_P:
        s += 100.0
    elif lc in _CLAUSE_P:
        s += 80.0
    elif lc in _CLOSE_P:
        s += 70.0
    if rc in _OPEN_P:
        s += 70.0
    if rc in _SENT_P or rc in _CLAUSE_P or rc in _CLOSE_P or rc == ".":
        s -= 60.0  # dangling punct left behind
    if lc in _OPEN_P:
        s -= 60.0  # stranded open punct
    if lc in _AFTER_OK:
        s += 45.0
    if rc in _BIND_LEFT:
        s -= 45.0
    if rc in _BIND_RIGHT:
        s -= 20.0
    if lc in _PREFIX:
        s -= 40.0
    if _cjk(lc) != _cjk(rc) and (
        (lc.isascii() and lc.isalnum()) or (rc.isascii() and rc.isalnum())
    ):
        s += 25.0  # CJK <-> latin/digit edge
    if gap_s > 0:
        s += min(gap_s, _GAP_CAP) * _GAP_W
    return s


def _cjk(ch):
    return "一" <= ch <= "鿿"


# ------------------------------------------------------------------ diarize


def turn_at(turns, t):
    for tr in turns:
        if tr["t0"] - 1e-3 <= t <= tr["t1"] + 1e-3:
            return f"S{tr['speaker'] + 1}"
    return None


def assign_speaker(t0, t1, turns):
    best, best_ov = None, 0.0
    for tr in turns:
        ov = min(t1, tr["t1"]) - max(t0, tr["t0"])
        if ov > best_ov:
            best, best_ov = tr["speaker"], ov
    return f"S{best + 1}" if best is not None else "S1"


# ------------------------------------------------------------------ scoring


def cue_break_scores(parts, nxt=None, joiner="", use_jieba=True):
    """score[k] = quality of splitting between parts[k-1] and parts[k],
    k in 1..len(parts)-1 (plus k=len(parts) when nxt given — the boundary
    before the incoming word)."""
    allp = list(parts) + ([nxt] if nxt is not None else [])
    text = joiner.join(str(p["w"]) for p in allp)
    bounds = jieba_bounds(text) if (use_jieba and not joiner) else None
    offs = [0]
    for p in allp:
        offs.append(offs[-1] + len(str(p["w"])) + len(joiner))
    scores = {}
    for k in range(1, len(allp)):
        lw, rw = str(allp[k - 1]["w"]), str(allp[k]["w"])
        gap = allp[k]["t0"] - allp[k - 1]["t1"]
        s = pair_score(lw[-1:], rw[:1], gap)
        if bounds is not None:
            s += _JIEBA_OK if offs[k] in bounds else _JIEBA_NO
        scores[k] = s
    return scores


def _pick_split(
    parts, joiner, nxt, use_jieba=True, lookback=_LOOKBACK, min_left=2, min_right=2
):
    """Best split index k for a cue that hit a hard limit. k == len(parts)
    means 'break before nxt' (no internal split). Prefers higher scores,
    then later positions (fuller cue)."""
    n = len(parts)
    scores = cue_break_scores(parts, nxt=nxt, joiner=joiner, use_jieba=use_jieba)
    cands = list(range(max(min_left, n - lookback), n - min_right + 1))
    cands.append(n)
    best, best_key = n, None
    for k in cands:
        key = (scores.get(k, 0.0), k)
        if best_key is None or key > best_key:
            best_key, best = key, k
    return best


def _join_word(joiner, acc, wtext):
    if not acc:
        return wtext
    if joiner == " " and wtext and all(ch in PUNCT_ONLY for ch in wtext):
        return acc + wtext  # no space before punctuation
    return acc + joiner + wtext if joiner else acc + wtext


def _mk_cue(parts, joiner):
    text = ""
    for p in parts:
        text = _join_word(joiner, text, str(p["w"]))
    spk = next((p["spk"] for p in parts if p.get("spk") is not None), None)
    return {
        "t0": parts[0]["t0"],
        "t1": parts[-1]["t1"],
        "text": text,
        "speaker": spk,
        "_parts": parts,
    }


def _cue_char_mids(parts, joiner):
    """Cumulative display-length at each split index."""
    acc, lens = 0, []
    for p in parts:
        acc += len(str(p["w"])) + (len(joiner) if lens else 0)
        lens.append(acc)
    return lens


def _enforce_limits(cues, cfg, joiner):
    """Post-pass hard limits. Split cues that exceed max_dur_s (remnants of a
    lookback split can), exceed line_chars*max_lines chars (the utterance
    fallback has no streaming cap), or exceed max_cps AND one full line of
    text — CPS splitting chunks a dense block into trackable pieces; it
    cannot lower true chars/sec when speech itself is that fast, so short
    cues are left alone. Iterates; each half is re-checked. Never splits
    inside a latin/digit token."""
    max_cps = float(cfg.get("max_cps", 20.0))
    max_dur = float(cfg.get("max_dur_s", 5.0))
    min_dur = float(cfg.get("min_dur_s", 1.0))
    line_chars = int(cfg.get("line_chars", 42))
    max_chars = line_chars * int(cfg.get("max_lines", 2))
    use_jieba = bool(cfg.get("jieba", True))
    min_side = 1 if joiner else 2
    out = []
    for c in cues:
        pend = [c["_parts"]]
        while pend:
            ps = pend.pop(0)
            dur = max(ps[-1]["t1"] - ps[0]["t0"], min_dur, 0.05)
            text_len = sum(len(str(p["w"])) for p in ps) + len(joiner) * (len(ps) - 1)
            over_dur = max_dur > 0 and ps[-1]["t1"] - ps[0]["t0"] > max_dur
            over_len = max_chars > 0 and text_len > max_chars
            over_cps = (
                max_cps > 0 and text_len > line_chars and text_len / dur > max_cps
            )
            if not (over_dur or over_len or over_cps) or len(ps) < 2 * min_side:
                out.append(_mk_cue(ps, joiner))
                continue
            scores = cue_break_scores(ps, joiner=joiner, use_jieba=use_jieba)
            lens = _cue_char_mids(ps, joiner)
            mid = max(
                1,
                next((k for k, v in enumerate(lens) if v >= lens[-1] / 2), len(ps) - 1),
            )
            cand = list(range(min_side, len(ps) - min_side + 1))
            k = max(cand, key=lambda k: (scores[k] >= 0, scores[k], -abs(k - mid)))
            if scores[k] <= _NO_BREAK / 2:  # only inside-token breaks
                out.append(_mk_cue(ps, joiner))
                continue
            pend[:0] = [ps[:k], ps[k:]]  # DFS keeps halves in time order
    return out


def _parts_from_text(text, t0, t1, joiner, spk=None):
    """Pseudo word-ts for cues that lack them (utterance fallback): linear
    interpolation weighted by token length."""
    toks = text.split(joiner) if joiner else list(text)
    total = sum(len(t) for t in toks) or 1
    acc, parts = t0, []
    for t in toks:
        d = (t1 - t0) * len(t) / total
        parts.append({"w": t, "t0": acc, "t1": acc + d, "spk": spk})
        acc += d
    return parts


# --------------------------------------------------------------------- cues


def words_to_cues(words, cfg):
    """Group word-ts into subtitle cues. cfg keys: line_chars, max_lines,
    max_dur_s, min_dur_s, gap_s, max_cps, word_joiner, break_at_sentence,
    jieba, turns (optional diarization turns — cue breaks on speaker change).

    Break order: pause/sentence/speaker are natural breaks; duration/length
    limits look back for the best recent boundary (jieba edge, pause,
    particle, punctuation) instead of splitting mid-word."""
    line_chars = int(cfg.get("line_chars", 42))
    max_lines = int(cfg.get("max_lines", 2))
    max_chars = line_chars * max_lines
    max_dur = float(cfg.get("max_dur_s", 5.0))
    min_dur = float(cfg.get("min_dur_s", 1.0))
    gap_s = float(cfg.get("gap_s", 1.0))
    joiner = cfg.get("word_joiner", " ")
    sent_break = bool(cfg.get("break_at_sentence", True))
    use_jieba = bool(cfg.get("jieba", True))
    turns = cfg.get("turns")

    cues, cur = [], []
    for w in words:
        t0, t1, wt = w["t0"], w["t1"], str(w["w"])
        spk = turn_at(turns, t0) if turns else None
        if not cur:
            cur = [{"w": wt, "t0": t0, "t1": t1, "spk": spk}]
            continue
        clen = sum(len(p["w"]) for p in cur) + len(joiner) * (len(cur) - 1)
        prev = cur[-1]
        cur_spk = next((p["spk"] for p in cur if p["spk"] is not None), None)
        natural = (
            t0 - prev["t1"] > gap_s
            or (sent_break and prev["w"].endswith(SENT_END))
            or (spk is not None and cur_spk is not None and spk != cur_spk)
        )
        over = t1 - cur[0]["t0"] > max_dur or clen + len(joiner) + len(wt) > max_chars
        if natural or over:
            k = (
                len(cur)
                if natural or len(cur) < 2
                else _pick_split(
                    cur, joiner, {"w": wt, "t0": t0, "t1": t1}, use_jieba=use_jieba
                )
            )
            cues.append(_mk_cue(cur[:k], joiner))
            cur = [*cur[k:], {"w": wt, "t0": t0, "t1": t1, "spk": spk}]
        else:
            cur.append({"w": wt, "t0": t0, "t1": t1, "spk": spk})
    if cur:
        cues.append(_mk_cue(cur, joiner))

    cues = _enforce_limits(cues, cfg, joiner)

    # minimum display duration, never overlapping the next cue
    for i, c in enumerate(cues):
        end = max(c["t1"], c["t0"] + min_dur)
        if i + 1 < len(cues):
            end = min(end, cues[i + 1]["t0"])
        c["t1"] = max(c["t0"] + 0.2, end)
        c.pop("_parts", None)
    return cues


def cues_from_utterances(utterances, cfg):
    """Fallback when the ASR impl emits no word ts: one cue per chunk,
    CPS-split with linearly interpolated pseudo word ts."""
    joiner = cfg.get("word_joiner", " ")
    min_dur = float(cfg.get("min_dur_s", 1.0))
    cues = []
    for u in utterances:
        if not u.get("text"):
            continue
        cues.append(
            {
                "t0": u["start"],
                "t1": u["end"],
                "text": u["text"],
                "speaker": u.get("speaker"),
                "_parts": _parts_from_text(
                    u["text"], u["start"], u["end"], joiner, u.get("speaker")
                ),
            }
        )
    cues = _enforce_limits(cues, cfg, joiner)
    for i, c in enumerate(cues):
        end = max(c["t1"], c["t0"] + min_dur)
        if i + 1 < len(cues):
            end = min(end, cues[i + 1]["t0"])
        c["t1"] = max(c["t0"] + 0.2, end)
        c.pop("_parts", None)
    return cues


# --------------------------------------------------------------------- wrap


def wrap_zh(text, line_chars, bounds=None, use_jieba=True):
    """Word-aware zh wrap: best boundary in window, last line balanced so a
    <=3-char orphan only remains when a strong boundary (punct) justifies it.
    `bounds`: precomputed jieba token edges for `text` (None -> lookup)."""
    if bounds is None:
        bounds = jieba_bounds(text) if use_jieba else None
    lines, s, base = [], text, 0
    while len(s) > line_chars:
        if len(s) <= 2 * line_chars:
            lo, hi, target = len(s) - line_chars, line_chars, len(s) / 2
        else:
            lo, hi, target = 1, line_chars, float(line_chars)
        best_c, best_key = lo, None
        for c in range(max(1, lo), min(hi, len(s) - 1) + 1):
            sc = pair_score(s[c - 1], s[c])
            if bounds is not None:
                sc += _JIEBA_OK if (base + c) in bounds else _JIEBA_NO
            rem = len(s) - c
            if rem < 4:
                sc -= (4 - rem) * 12.0  # orphan-line penalty
            key = (sc, -abs(c - target))
            if best_key is None or key > best_key:
                best_key, best_c = key, c
        lines.append(s[:best_c])
        base += best_c
        s = s[best_c:]
    if s:
        lines.append(s)
    return lines


def _wrap_cue(text, line_chars, joiner, use_jieba=True):
    """Wrap cue text into <=~2 display lines."""
    if joiner:  # space-joined: greedy word wrap
        lines, cur = [], ""
        for wd in text.split(joiner):
            cand = wd if not cur else cur + joiner + wd
            if len(cand) <= line_chars or not cur:
                cur = cand
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines
    return wrap_zh(text, line_chars, use_jieba=use_jieba)


def _srt_ts(t):
    ms = round(t * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render_srt(cues, cfg):
    line_chars = int(cfg.get("line_chars", 42))
    joiner = cfg.get("word_joiner", " ")
    use_jieba = bool(cfg.get("jieba", True))
    blocks = []
    for i, c in enumerate(cues, 1):
        spk = f"[{c['speaker']}] " if c.get("speaker") else ""
        lines = _wrap_cue(c["text"], line_chars, joiner, use_jieba)
        if spk and lines:
            lines[0] = spk + lines[0]
        blocks.append(
            f"{i}\n{_srt_ts(c['t0'])} --> {_srt_ts(c['t1'])}\n" + "\n".join(lines)
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")
