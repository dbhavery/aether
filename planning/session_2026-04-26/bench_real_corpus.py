"""Real-corpus retrieval bench — Phase C of HANDOFF_2026-04-26.

Extracts a single Lex Fridman episode from the lexicap parquet,
builds structural-reference ground truth (later turn containing a
distinctive term -> earliest turn that introduced that term),
embeds every turn with bge-m3 via Ollama, runs the production
rank function, and reports recall@1/3/5/10/20 + MRR.

Distinct from `bench_recall.py` (synthetic corpus): real human
conversation, ground truth derived from lexical reuse (no LLM
judge in the loop), so the recall numbers reflect "how well does
cosine retrieval surface the earlier mention when the speaker
re-uses a distinctive term?".

Output: real_corpus_recall.json
"""
from __future__ import annotations

import json
import math
import re
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

PARQUET = Path("planning/session_2026-04-26/lexfridman.parquet")
OUT = Path("planning/session_2026-04-26/real_corpus_recall.json")
EPISODE_ID = 4  # Yoshua Bengio - Deep Learning, 417 segments
OLLAMA = "http://127.0.0.1:11434"
MODEL = "bge-m3:latest"

# Stopword list — pruned to high-frequency English function words.
# We DON'T want these labeled as "distinctive" reference terms.
STOPWORDS = set("""
a an the and or but if then else when where why how what who whom whose which
that this these those there here is are was were be been being have has had
do does did doing done will would shall should can could may might must
i me my mine you your yours he him his she her hers it its we us our ours
they them their theirs of in on at to for from with by about as into through
during before after above below up down out off over under again further
not no nor so than too very just only own same such both each few more most
other some any all every either neither also still yet already
say said says saying tell told tells telling
think thought thinks thinking
know knew known knows knowing
go went gone goes going get got gotten gets getting
make made makes making
take took taken takes taking
come came comes coming
see saw seen sees seeing
look looks looking looked
want wants wanted wanting
like likes liked liking
right okay yeah yes no well so um uh oh ah hmm mhm
really actually basically literally probably maybe somehow somewhat somewhere
something anything everything nothing someone anyone everyone everybody
people thing things stuff lot lots kind sort way ways
mean means meant meaning
because cause why how
back even though although still however therefore thus hence
""".split())

# Minimum token length for a token to count as "distinctive". Drops
# 1-2 char filler that survived the stopword list.
MIN_TOKEN_LEN = 4

# Min and max document frequency for ground-truth terms. Too rare =
# noise (single mention can't establish a reference). Too common =
# function-word leakage masquerading as content.
MIN_DF = 2
MAX_DF = 4

# Min gap between query turn and its referenced turn. Adjacent
# repetition isn't "retrieval" — it's local context.
MIN_GAP = 10

# Minimum query length in words. Short Whisper segments ("Yeah.",
# "Right, mhm.") don't carry retrieval intent.
MIN_QUERY_WORDS = 12

# Use bigrams (multi-word phrases) instead of unigrams for ground
# truth. A repeated bigram is far more likely to be a real back-
# reference than a repeated single content word.
USE_BIGRAMS = True


def tokenize(text: str) -> list[str]:
    """Lowercase alphabetic tokens of length >= MIN_TOKEN_LEN."""
    return [
        t.lower()
        for t in re.findall(r"[A-Za-z][A-Za-z'-]+", text)
        if len(t) >= MIN_TOKEN_LEN
    ]


def keyphrases(text: str) -> set:
    """Extract distinctive keyphrases for ground-truth labeling.
    Bigrams of content tokens (stopwords stripped) — repeated
    bigrams are strong back-reference signals; repeated unigrams
    are not (cf. miss samples in v1 run, where unigram reuse
    surfaced semantically-irrelevant first-mentions)."""
    toks = [
        t.lower()
        for t in re.findall(r"[A-Za-z][A-Za-z'-]+", text)
        if len(t) >= MIN_TOKEN_LEN and t.lower() not in STOPWORDS
    ]
    if USE_BIGRAMS:
        return set(zip(toks, toks[1:]))
    return set(toks)


def load_episode(parquet_path: Path, ep_id: int) -> list[dict]:
    """Return [{turn_id, text, start, end}, ...] for the episode."""
    table = pq.read_table(parquet_path)
    ids = table.column("id").to_pylist()
    texts = table.column("text").to_pylist()
    starts = table.column("start").to_pylist()
    ends = table.column("end").to_pylist()
    out: list[dict] = []
    seq = 0
    for i, e in enumerate(ids):
        if e != ep_id:
            continue
        text = (texts[i] or "").strip()
        if not text:
            continue
        out.append({
            "turn_id": f"ep{ep_id}.t{seq:04d}",
            "text": text,
            "start": starts[i],
            "end": ends[i],
            "seq": seq,
        })
        seq += 1
    return out


def build_ground_truth(turns: list[dict]) -> tuple[list[dict], dict]:
    """For each turn after a distinctive term's first introduction,
    record `references = [introducing_turn_id]`. Returns (turns_with_refs,
    stats) where turns_with_refs has `references: [turn_id, ...]` and
    `referenced_terms: [term, ...]` for inspection.
    """
    n = len(turns)
    # Extract keyphrases (bigrams when USE_BIGRAMS, else unigrams).
    content_per_turn = [keyphrases(t["text"]) for t in turns]
    df: Counter = Counter()
    for s in content_per_turn:
        df.update(s)
    eligible = {
        term for term, c in df.items() if MIN_DF <= c <= MAX_DF
    }
    # First-introduction map: term -> earliest turn index containing it.
    first_seen: dict[str, int] = {}
    for i, s in enumerate(content_per_turn):
        for term in s & eligible:
            if term not in first_seen:
                first_seen[term] = i

    # For each turn, find any eligible term whose first introduction
    # was at least MIN_GAP turns earlier; record the introducing
    # turn as the ground-truth reference. Multiple terms in one turn
    # produce a multi-target ground truth.
    enriched = []
    qcount = 0
    target_counter: Counter = Counter()
    for i, turn in enumerate(turns):
        refs: list[str] = []
        ref_terms: list[str] = []
        for term in content_per_turn[i] & eligible:
            origin = first_seen[term]
            if origin <= i - MIN_GAP:
                ref_id = turns[origin]["turn_id"]
                if ref_id not in refs:
                    refs.append(ref_id)
                    ref_terms.append(term)
        copy = dict(turn)
        if refs and len(turn["text"].split()) >= MIN_QUERY_WORDS:
            copy["references"] = refs
            copy["referenced_terms"] = [str(t) for t in ref_terms]
            qcount += 1
            target_counter[len(refs)] += 1
        enriched.append(copy)

    stats = {
        "turns": n,
        "eligible_terms": len(eligible),
        "max_df": MAX_DF,
        "min_df": MIN_DF,
        "min_gap": MIN_GAP,
        "min_query_words": MIN_QUERY_WORDS,
        "use_bigrams": USE_BIGRAMS,
        "queries": qcount,
        "targets_per_query_distribution": dict(sorted(target_counter.items())),
    }
    return enriched, stats


def embed_one(text: str, retries: int = 3) -> list[float] | None:
    """Single-string Ollama embed. Retries on 5xx with backoff."""
    body = json.dumps({"model": MODEL, "prompt": text}).encode("utf-8")
    last_error: str = ""
    for attempt in range(retries):
        if attempt > 0:
            time.sleep(0.25 * (2 ** (attempt - 1)))
        req = urllib.request.Request(
            f"{OLLAMA}/api/embeddings",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - bench scratch
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        emb = payload.get("embedding")
        if isinstance(emb, list) and emb:
            return emb
        last_error = f"missing embedding field in payload"
    print(f"  embed failed after {retries} retries: {last_error}", file=sys.stderr)
    return None


def cosine(a: list[float], b: list[float]) -> float:
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def production_rank(query_vec, candidates, max_items):
    """Mirror of run_retrieval_context Phase 4 rank: cosine desc,
    timestamp desc tiebreak, truncate."""
    scored = []
    for row in candidates:
        s = cosine(query_vec, row["embedding"])
        scored.append((s, row["seq"], row))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [
        {"turn_id": row["turn_id"], "score": s, "seq": row["seq"]}
        for s, _ts, row in scored[:max_items]
    ]


def main() -> int:
    print(f"loading episode {EPISODE_ID} from {PARQUET}", file=sys.stderr)
    turns = load_episode(PARQUET, EPISODE_ID)
    if not turns:
        print(f"ERROR: no turns for episode {EPISODE_ID}", file=sys.stderr)
        return 1
    print(f"  {len(turns)} turns", file=sys.stderr)

    print("building structural ground truth (lexical reuse)…", file=sys.stderr)
    enriched, gt_stats = build_ground_truth(turns)
    print(f"  {gt_stats['queries']} queries with refs, "
          f"{gt_stats['eligible_terms']} eligible terms", file=sys.stderr)
    if gt_stats['queries'] < 30:
        print("ERROR: <30 queries — corpus or thresholds bad", file=sys.stderr)
        return 1

    print(f"embedding {len(enriched)} turns via {MODEL} on Ollama…", file=sys.stderr)
    t0 = time.time()
    embedded = []
    for i, turn in enumerate(enriched):
        if i % 50 == 0:
            print(f"  embed {i}/{len(enriched)} ({time.time()-t0:.1f}s)", file=sys.stderr)
        emb = embed_one(turn["text"])
        if emb is None:
            print(f"  skipping {turn['turn_id']} — embed failed", file=sys.stderr)
            continue
        copy = dict(turn)
        copy["embedding"] = emb
        embedded.append(copy)
    print(f"  {len(embedded)}/{len(enriched)} embedded in "
          f"{time.time()-t0:.1f}s", file=sys.stderr)

    by_id = {r["turn_id"]: r for r in embedded}
    queries = [r for r in embedded if r.get("references")]
    print(f"running rank for {len(queries)} queries…", file=sys.stderr)

    K_VALUES = [1, 3, 5, 10, 20]
    hit_counts = {k: 0 for k in K_VALUES}
    rr_sum = 0.0
    misses: list[dict] = []
    multi_target_recall = []

    for q in queries:
        # Candidates: all OTHER turns in the same episode. (Real
        # production retrieval excludes same-session via session_id;
        # here every turn is the same session — no filter.)
        candidates = [r for r in embedded if r["turn_id"] != q["turn_id"]]
        ranked = production_rank(q["embedding"], candidates, max_items=20)
        ranked_ids = [h["turn_id"] for h in ranked]
        expected = set(q["references"])

        first_pos = 0
        for i, rid in enumerate(ranked_ids, start=1):
            if rid in expected:
                first_pos = i
                break
        for k in K_VALUES:
            if 0 < first_pos <= k:
                hit_counts[k] += 1
        if first_pos > 0:
            rr_sum += 1.0 / first_pos
        else:
            misses.append({
                "query_turn_id": q["turn_id"],
                "query_text": q["text"][:160],
                "expected": list(expected),
                "expected_terms": q.get("referenced_terms", []),
                "top5": [
                    {**h, "text": by_id[h["turn_id"]]["text"][:120]}
                    for h in ranked[:5]
                ],
            })

        # Multi-target recall@5: fraction of expected refs in top-5.
        if expected:
            top5_set = set(ranked_ids[:5])
            multi_target_recall.append(
                len(expected & top5_set) / len(expected)
            )

    n = len(queries)
    summary = {
        "model": MODEL,
        "episode_id": EPISODE_ID,
        "corpus_size": len(embedded),
        "query_count": n,
        "recall_at_1": round(hit_counts[1] / n, 4),
        "recall_at_3": round(hit_counts[3] / n, 4),
        "recall_at_5": round(hit_counts[5] / n, 4),
        "recall_at_10": round(hit_counts[10] / n, 4),
        "recall_at_20": round(hit_counts[20] / n, 4),
        "mrr": round(rr_sum / n, 4),
        "mean_multi_target_recall_at_5": (
            round(statistics.mean(multi_target_recall), 4)
            if multi_target_recall else None
        ),
        "complete_misses": len(misses),
        "ground_truth": gt_stats,
        "rank_function": "cosine_desc__then_seq_desc__truncate(max_items)",
        "ground_truth_method": "structural_lexical_reuse",
    }

    out = {
        "summary": summary,
        "miss_samples": misses[:8],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
