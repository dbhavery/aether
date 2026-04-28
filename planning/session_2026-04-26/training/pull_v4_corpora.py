"""V4-01: pull §4.3 corpora and re-mine existing Lex Fridman parquet.

New corpora:
  - OpenSubtitles via ghomasHudson/muld (English subset, 'input' field)
  - ordinary_screenplays via alankent/ordinary_screenplays
  - Lex Fridman re-mining: planning/session_2026-04-26/lexfridman.parquet
    contains 800k Whisper segments. Aggregate into 6-10 turn pseudo-
    conversations using long-pause heuristic for speaker change.

Outputs (raw HF dataset format where applicable):
  data/opensubtitles/
  data/ordinary_screenplays/
  data/lex_fridman_chunked/  (re-mined, raw conversation JSONL)
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)

LEX_PARQUET = ROOT.parent / "lexfridman.parquet"


def pull_opensubtitles():
    out = DATA / "opensubtitles"
    if (out / "dataset_info.json").exists() or (out / "dataset_dict.json").exists():
        print(f"[opensubtitles] already at {out}, skipping")
        return
    print("[opensubtitles] downloading ghomasHudson/muld 'OpenSubtitles' subset...")
    from datasets import load_dataset
    try:
        ds = load_dataset("ghomasHudson/muld", "OpenSubtitles",
                          split="train", trust_remote_code=True)
    except Exception as e:
        print(f"  failed first attempt: {e}")
        # Fallback name
        try:
            ds = load_dataset("ghomasHudson/muld", "opensubtitles",
                              split="train", trust_remote_code=True)
        except Exception as e2:
            print(f"  failed second attempt: {e2}")
            print("  skipping opensubtitles — try manual download")
            return
    print(f"  loaded {len(ds)} rows")
    ds.save_to_disk(str(out))
    print(f"  saved to {out}")


def pull_ordinary_screenplays():
    out = DATA / "ordinary_screenplays"
    if (out / "dataset_info.json").exists() or (out / "dataset_dict.json").exists():
        print(f"[ordinary_screenplays] already at {out}, skipping")
        return
    print("[ordinary_screenplays] downloading alankent/ordinary_screenplays...")
    from datasets import load_dataset
    try:
        ds = load_dataset("alankent/ordinary_screenplays", split="train",
                          trust_remote_code=True)
    except Exception as e:
        print(f"  failed: {e}")
        print("  skipping ordinary_screenplays")
        return
    print(f"  loaded {len(ds)} rows")
    ds.save_to_disk(str(out))
    print(f"  saved to {out}")


def remine_lex():
    """Aggregate Whisper segments into 6-10 turn pseudo-conversations.

    Heuristic: a long pause (>1.5s) between segments suggests speaker
    change. Group consecutive segments into 'turns' separated by pauses,
    then take 6-10 turn windows.
    """
    out = DATA / "lex_fridman_chunked"
    out.mkdir(parents=True, exist_ok=True)
    out_file = out / "conversations.jsonl"
    if out_file.exists():
        n = sum(1 for _ in out_file.open(encoding="utf-8"))
        if n > 1000:
            print(f"[lex] already at {out_file} with {n} convos, skipping")
            return

    if not LEX_PARQUET.exists():
        print(f"[lex] parquet not found at {LEX_PARQUET}, skipping")
        return

    print(f"[lex] reading {LEX_PARQUET}")
    import pyarrow.parquet as pq
    tbl = pq.read_table(str(LEX_PARQUET))
    df_cols = tbl.column_names
    print(f"  columns: {df_cols}")
    rows = tbl.to_pylist()
    print(f"  {len(rows)} rows")

    if not rows:
        print("  no rows, skipping")
        return

    # Sort by episode then start time if available
    sample = rows[0]
    ep_key = next((k for k in ("episode", "episode_id", "video_id", "source", "id", "guest", "title")
                   if k in sample), None)
    start_key = next((k for k in ("start", "start_time", "begin")
                      if k in sample), None)
    text_key = next((k for k in ("text", "transcript", "content")
                     if k in sample), "text")
    print(f"  ep_key={ep_key} start_key={start_key} text_key={text_key}")

    if start_key:
        rows.sort(key=lambda r: (r.get(ep_key, ""), r.get(start_key, 0)))
    elif ep_key:
        rows.sort(key=lambda r: r.get(ep_key, ""))

    PAUSE_THRESHOLD = 1.5  # seconds — likely speaker change
    MIN_TURNS = 6
    MAX_TURNS = 10
    MIN_TURN_LEN = 3
    MAX_TURN_LEN = 320
    MAX_CONVOS = 50000

    convos = []
    cur_ep = None
    cur_turn_text = []
    cur_turns: list[str] = []
    last_end = None
    speaker_idx = 0

    end_key = next((k for k in ("end", "end_time", "stop") if k in sample), None)

    def flush_turn():
        nonlocal cur_turn_text, speaker_idx
        if cur_turn_text:
            joined = " ".join(cur_turn_text).strip()
            if MIN_TURN_LEN <= len(joined) <= MAX_TURN_LEN:
                cur_turns.append({"speaker": "AB"[speaker_idx % 2], "text": joined})
                speaker_idx += 1
            cur_turn_text = []

    def flush_convo():
        nonlocal cur_turns, speaker_idx
        if MIN_TURNS <= len(cur_turns) <= MAX_TURNS:
            # Ensure ends on speaker A so reply is B (matches our prompt format)
            ctx = list(cur_turns)
            if ctx[-1]["speaker"] == "B":
                ctx = ctx[:-1]
            if MIN_TURNS <= len(ctx):
                convos.append({
                    "source": "lex_fridman",
                    "conversation_id": f"lex_fridman.{len(convos)}",
                    "turns": ctx,
                })
        cur_turns = []
        speaker_idx = 0

    for r in rows:
        if len(convos) >= MAX_CONVOS:
            break
        ep = r.get(ep_key, "_") if ep_key else "_"
        text = (r.get(text_key) or "").strip()
        if not text:
            continue
        def parse_ts(v):
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                # Formats: "MM:SS.mmm" or "HH:MM:SS.mmm"
                parts = v.split(":")
                try:
                    if len(parts) == 2:
                        return int(parts[0]) * 60 + float(parts[1])
                    if len(parts) == 3:
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                    return float(v)
                except (TypeError, ValueError):
                    return None
            return None

        start = parse_ts(r.get(start_key)) if start_key else 0.0
        if start is None:
            start = 0.0
        end = parse_ts(r.get(end_key)) if end_key else None
        if end is None:
            end = start + 1.0

        if ep != cur_ep:
            flush_turn()
            flush_convo()
            cur_ep = ep
            last_end = None

        # Detect speaker change via pause
        if last_end is not None and start - last_end > PAUSE_THRESHOLD:
            flush_turn()
            if len(cur_turns) >= MAX_TURNS:
                flush_convo()

        cur_turn_text.append(text)
        last_end = end

    flush_turn()
    flush_convo()

    print(f"  built {len(convos)} pseudo-convos (target up to {MAX_CONVOS})")
    with out_file.open("w", encoding="utf-8") as f:
        for c in convos:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"  wrote {out_file}")


def main() -> int:
    t0 = time.time()
    pull_opensubtitles()
    pull_ordinary_screenplays()
    remine_lex()
    print(f"\nall done in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
