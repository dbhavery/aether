"""Phase 3A — Synthetic conversation corpus generator for retrieval calibration.

Generates 50-100 conversational threads via Ollama gemma4:e4b. Each thread
is a coherent topic with 10-20 turns. ~20% of turns include cross-thread
references that form ground-truth retrieval pairs for the calibration bench.

Output schema (JSONL, one row per turn):
    {
      "turn_id": "t<thread_idx>_<turn_idx>",
      "thread_id": "thread_<idx>",
      "thread_topic": "trip planning to Iceland",
      "turn_index": 3,
      "role": "user" | "assistant",
      "text": "...",
      "references": ["t<otherthread>_<turnidx>", ...],  # ground-truth target turns
      "timestamp_ms": <synthetic ascending int>
    }

Thread topics are sampled from a fixed seed pool covering personal-life domains
(trip planning, recipe iteration, language learning, fitness, debugging, etc.)
matching the kinds of conversations Aether is built to remember.

The cross-thread reference is the calibration ground truth: when generating a
referencing turn, we ask the model to allude to a specific earlier turn in a
different thread, and we record that target turn's id in `references`. The
calibration bench then uses the referencing turn's text as a query and checks
whether the rank function surfaces the referenced turn near the top.

NOTE on reproducibility — we save the prompt template inline below. The
gen seed is fixed but model output is non-deterministic (gemma4:e4b temperature
default ~0.8). Re-running will produce a comparable but not byte-identical
corpus. The bench is rerunnable against any saved corpus jsonl.
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
MODEL = "gemma4:e4b"
OUT_PATH = Path("planning/session_2026-04-25/synthetic_corpus.jsonl")

# Configurable: smaller for fast iteration, larger for full calibration.
N_THREADS = 60       # 50-100 per handoff
TURNS_MIN = 10
TURNS_MAX = 18
CROSS_REF_RATE = 0.20  # ~20% of eligible turns reference another thread

random.seed(20260425)

# Topic pool — coherent, personal-life-shaped. Each is a (label, seed_prompt)
# tuple. Mixed so the corpus has cross-domain diversity.
TOPIC_POOL = [
    ("trip planning to Iceland", "two-week September trip, northern lights, ring road, hot springs"),
    ("trip planning to Kyoto", "April cherry blossom timing, ryokan booking, day trips to Nara"),
    ("trip planning to Patagonia", "January W-trek logistics, Torres del Paine permits, gear list"),
    ("trip planning to Marrakesh", "March riad selection, souk navigation, Atlas Mountains day trip"),
    ("trip planning to New Zealand", "South Island campervan loop, Milford Sound boat timing"),
    ("sourdough recipe iteration", "starter feeding schedule, hydration ratios, crumb structure debug"),
    ("ramen broth iteration", "tonkotsu rolling boil duration, emulsification, aroma oil"),
    ("macaron technique iteration", "macaronnage stages, feet development, oven temp tuning"),
    ("croissant lamination iteration", "butter block temperature, fold count, proof timing"),
    ("pizza dough iteration", "biga vs poolish, hydration, leoparding on the crust"),
    ("learning Spanish", "subjunctive triggers, ser vs estar drills, podcast listening"),
    ("learning Japanese", "kanji radicals, particle nuance, polite vs casual register"),
    ("learning German", "case system, separable verbs, modal particle feel"),
    ("learning Mandarin", "tone pair drills, character handwriting, HSK milestones"),
    ("debugging a Rust async deadlock", "tokio task budget, mutex held across await, tracing instrument"),
    ("debugging a Python memory leak", "tracemalloc snapshots, ref-cycle hunt, gc tuning"),
    ("debugging a TypeScript build slowdown", "tsc incremental, project refs, isolatedModules"),
    ("personal fitness routine", "5x5 strength split, deload weeks, sleep quality correlation"),
    ("running training plan", "base mileage build, threshold workouts, marathon taper"),
    ("yoga practice progression", "ashtanga primary series, bind progressions, breath count"),
    ("rock climbing progression", "V3 to V4 plateau, finger strength, route reading"),
    ("home espresso setup", "grinder dial-in, puck prep, milk steaming for latte art"),
    ("pour-over coffee dial-in", "V60 grind, bloom timing, agitation pattern"),
    ("home garden planning", "raised-bed layout, companion planting, drip irrigation"),
    ("woodworking bench build", "joinery selection, mortise-and-tenon vs domino, finish choice"),
    ("electronics synth build", "Eurorack module sequence, power budget, calibration"),
    ("photography studio lighting", "key vs fill ratio, softbox vs umbrella, color temp matching"),
    ("video editing workflow", "DaVinci Resolve color pages, proxy generation, audio sync"),
    ("3D printing calibration", "first-layer leveling, retraction tuning, temp tower analysis"),
    ("home theater calibration", "REW measurement, sub crawl, treatment placement"),
    ("aquarium cycling", "ammonia source, nitrite spike, beneficial bacteria establishment"),
    ("dog training progression", "loose-leash walking, place command, recall reliability"),
    ("budget tracking system", "category granularity, sinking funds, monthly review cadence"),
    ("retirement portfolio review", "asset allocation, rebalance trigger, tax-loss harvesting"),
    ("home renovation planning", "permit timing, contractor bid review, kitchen layout iteration"),
    ("commute optimization", "transit transfers, bike route variants, weather contingency"),
    ("car maintenance schedule", "oil interval, tire rotation, brake fluid flush"),
    ("guitar practice routine", "warm-up scales, repertoire rotation, recording check-ins"),
    ("piano repertoire progression", "Bach inventions, chord-tone improvisation, sight-reading drills"),
    ("songwriting iteration", "verse-chorus structure, lyric editing, demo arrangements"),
    ("novel drafting", "outline tightening, chapter breaks, dialogue tags pruning"),
    ("blog post pipeline", "draft cadence, headline iteration, link distribution"),
    ("research paper revision", "lit-review structure, methods clarity, peer review response"),
    ("meal prep optimization", "Sunday batch cook, container rotation, macro tracking"),
    ("knife skills progression", "honing routine, chiffonade speed, brunoise consistency"),
    ("bread baking schedule", "weekly bake plan, levain timing, oven steam method"),
    ("indoor plant care", "light mapping, watering frequency, pest scouting"),
    ("bicycle maintenance", "chain wear gauge, derailleur indexing, tubeless setup"),
    ("ski technique progression", "carving drills, mogul line choice, off-piste reading"),
    ("snowboard progression", "edge transitions, switch riding, jump approach speed"),
    ("kayak roll practice", "C-to-C technique, hip snap drill, off-side roll"),
    ("backpacking gear refinement", "base weight reduction, sleep system trade-offs, water treatment"),
    ("sleep quality experiment", "wake window timing, room temp tuning, magnesium trial"),
    ("morning routine iteration", "wake-time consistency, cold exposure, journaling practice"),
    ("evening wind-down routine", "screen cutoff, reading rotation, breathwork variants"),
    ("meditation practice deepening", "breath count anchor, body scan duration, retreat prep"),
    ("language tutor session notes", "pronunciation feedback, grammar drill assignments, homework"),
    ("therapy session journaling", "weekly themes, between-session homework, progress tracking"),
    ("home network upgrade", "wifi 7 access points, VLAN segmentation, NAS performance"),
    ("self-hosted server setup", "Tailscale mesh, Docker compose, backup rotation"),
    ("AI side project iteration", "model selection, eval design, latency budget"),
]

# Sanity: ensure pool is large enough to draw N_THREADS unique topics.
assert len(TOPIC_POOL) >= N_THREADS, f"pool {len(TOPIC_POOL)} < N_THREADS {N_THREADS}"


THREAD_GEN_PROMPT = """You are simulating an authentic conversation between a user (Don) and an AI assistant (Aether) about: {topic_label}

Context for the topic: {topic_seed}

Generate exactly {n_turns} alternating turns. The first turn is from the user. Strict format — one turn per line, no blank lines, no commentary, no markdown:

USER: <message>
AETHER: <message>
USER: <message>
AETHER: <message>
...

Rules:
- Each turn 1-3 sentences. Natural conversation, not a script.
- Specific concrete details (dates, numbers, names, decisions). Avoid generic platitudes.
- The conversation should evolve — the user makes decisions, the assistant remembers earlier turns.
- No meta commentary. No "Sure!" or "Of course!" filler openers from the assistant. Just the substance.
- Output ONLY the turns. No preamble, no closing."""


REFERENCE_GEN_PROMPT = """You are simulating Don, the user. You are mid-conversation about: {current_topic}

Earlier this week you had a separate conversation about: {ref_topic}

In that earlier conversation, you said this specific thing:
"{ref_text}"

Generate ONE single user message (1-2 sentences, no role prefix, no quotes around the message) that continues the current {current_topic} conversation but explicitly references back to the earlier {ref_topic} conversation — by paraphrasing the specific thing you said. Make the connection feel natural, like "remember when I mentioned X, that applies here because..." or "this is similar to the Y I brought up earlier when we discussed Z."

Output ONLY the message text. No prefix, no quotes, no commentary."""


def http_post(path: str, body: dict, timeout: float = 240.0) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def generate(prompt: str, max_retries: int = 3) -> str:
    """Single /api/generate call; retries on transient 500 (e.g. VRAM pressure
    from concurrent Phase 3C agent loading models)."""
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = http_post(
                "/api/generate",
                {"model": MODEL, "prompt": prompt, "stream": False,
                 "options": {"num_predict": 1024, "temperature": 0.85}},
                timeout=240.0,
            )
            return resp.get("response", "").strip()
        except Exception as e:
            last_err = e
            print(f"  [retry {attempt+1}] generate failed: {e}", file=sys.stderr)
            time.sleep(30)
    raise RuntimeError(f"generate failed after {max_retries} retries: {last_err}")


TURN_LINE_RE = re.compile(r"^(USER|AETHER)\s*:\s*(.+)$", re.IGNORECASE)


def parse_thread(raw: str, n_turns_target: int) -> list[tuple[str, str]]:
    """Parse model output into [(role, text), ...]. Tolerant of leading
    blank lines, occasional empty lines, accidental markdown bullets."""
    out: list[tuple[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip common markdown bullet/numbering noise.
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        m = TURN_LINE_RE.match(line)
        if not m:
            continue
        role_raw, text = m.group(1).upper(), m.group(2).strip()
        role = "user" if role_raw == "USER" else "assistant"
        out.append((role, text))
    return out[:n_turns_target]


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    chosen_topics = random.sample(TOPIC_POOL, N_THREADS)
    print(f"generating {N_THREADS} threads, target {TURNS_MIN}-{TURNS_MAX} turns each", file=sys.stderr)

    # Phase 1 — generate base threads (no cross-references yet).
    threads: list[dict] = []
    base_timestamp = 1_700_000_000_000  # arbitrary anchor in ms
    delta_ms = 60_000  # 1 minute between turns within thread
    thread_gap_ms = 6 * 3600 * 1000  # 6 hours between threads

    for ti, (label, seed) in enumerate(chosen_topics):
        n_turns = random.randint(TURNS_MIN, TURNS_MAX)
        # Force even count so user/assistant pairing stays clean.
        if n_turns % 2 == 1:
            n_turns += 1
        prompt = THREAD_GEN_PROMPT.format(topic_label=label, topic_seed=seed, n_turns=n_turns)
        print(f"  thread {ti+1}/{N_THREADS} '{label}' (n={n_turns}) ...", file=sys.stderr)
        try:
            raw = generate(prompt)
        except Exception as e:
            print(f"  SKIP thread {ti}: {e}", file=sys.stderr)
            continue
        parsed = parse_thread(raw, n_turns)
        if len(parsed) < 4:
            print(f"  SKIP thread {ti}: parsed only {len(parsed)} turns from {len(raw)} chars", file=sys.stderr)
            continue
        thread_start_ts = base_timestamp + ti * thread_gap_ms
        turns = []
        for ui, (role, text) in enumerate(parsed):
            turns.append({
                "turn_id": f"t{ti}_{ui}",
                "thread_id": f"thread_{ti}",
                "thread_topic": label,
                "turn_index": ui,
                "role": role,
                "text": text,
                "references": [],
                "timestamp_ms": thread_start_ts + ui * delta_ms,
            })
        threads.append({"label": label, "turns": turns})
        # Tiny pacing nap so we don't hammer Ollama (it shares the GPU
        # with Phase 3C if it's still warming models).
        time.sleep(0.2)

    print(f"\ngenerated {len(threads)} usable threads", file=sys.stderr)

    # Phase 2 — inject cross-thread references. For each thread we pick
    # ~CROSS_REF_RATE of its USER turns and rewrite them to reference a
    # turn from a DIFFERENT thread. The referenced turn must have enough
    # specific content to be meaningfully retrievable (we filter on len).
    print(f"injecting cross-thread references at rate {CROSS_REF_RATE:.2f}", file=sys.stderr)
    all_threads = threads
    ref_count = 0
    for ti, thread in enumerate(all_threads):
        # Eligible source turns: USER turns NOT at the very first position
        # (the first turn establishes the topic; rewriting it kills the thread).
        candidates = [t for t in thread["turns"] if t["role"] == "user" and t["turn_index"] >= 2]
        n_to_rewrite = max(0, int(round(len(candidates) * CROSS_REF_RATE)))
        if n_to_rewrite == 0:
            continue
        targets = random.sample(candidates, n_to_rewrite)
        for src_turn in targets:
            # Pick a target turn from a DIFFERENT thread, prefer assistant
            # turns (they tend to carry the substance).
            other_thread_idx = random.choice([i for i in range(len(all_threads)) if i != ti])
            other_thread = all_threads[other_thread_idx]
            ref_pool = [t for t in other_thread["turns"] if len(t["text"]) >= 60]
            if not ref_pool:
                continue
            ref_target = random.choice(ref_pool)
            try:
                new_text = generate(REFERENCE_GEN_PROMPT.format(
                    current_topic=thread["label"],
                    ref_topic=other_thread["label"],
                    ref_text=ref_target["text"][:300],
                ))
            except Exception as e:
                print(f"  SKIP ref rewrite {src_turn['turn_id']}: {e}", file=sys.stderr)
                continue
            # Strip wrapping quotes/markdown the model sometimes adds.
            new_text = new_text.strip().strip('"').strip("'").strip()
            if len(new_text) < 20:
                continue
            src_turn["text"] = new_text
            src_turn["references"] = [ref_target["turn_id"]]
            ref_count += 1
            time.sleep(0.2)

    print(f"injected {ref_count} cross-thread references", file=sys.stderr)

    # Write JSONL flat.
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for thread in all_threads:
            for t in thread["turns"]:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

    total_turns = sum(len(t["turns"]) for t in all_threads)
    print(f"\nwrote {OUT_PATH} ({total_turns} turns, {ref_count} reference pairs)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
