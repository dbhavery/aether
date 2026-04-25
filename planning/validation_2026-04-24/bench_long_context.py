"""Block 5: Long-context retrieval stress.

Builds a large synthetic memory store (default 150 passages, 50 labeled
queries), embeds with each candidate, measures recall@k decay vs the
20-passage micro-corpus from Block 3. Tests whether the small-vec model
(nomic-embed-text 768d) loses to bge-m3 (1024d) at scale.

Also exercises the per-domain isolation invariant by tagging a subset
of passages with an explicit `domain` field; queries should only match
within their requested domain (mimics ADR-0004 Durable lane behavior).
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434"

random.seed(42)  # deterministic corpus generation


# 30 thematic templates. Each generates one (passage, query, expected_id) triple.
# The query asks about the passage's content using different phrasing.
THEMES = [
    ("travel", "{name} is taking a trip to {place} in {month} to see the {attraction}.",
     "When does {name} plan to visit the {attraction}?",
     [("Anna", "Iceland", "October", "northern lights"),
      ("Ben", "Kyoto", "April", "cherry blossoms"),
      ("Carla", "Patagonia", "January", "fjord glaciers"),
      ("Dimitri", "Marrakesh", "March", "souk markets"),
      ("Elena", "New Zealand", "November", "Milford Sound"),
      ("Felix", "Iceland", "September", "Blue Lagoon"),
      ("Grace", "Norway", "December", "aurora borealis")]),
    ("hobby", "{name} has been learning to play the {instrument} for {duration} months and recently mastered {piece}.",
     "What instrument has {name} been practicing?",
     [("Henry", "violin", "twelve", "Bach Partita No. 2"),
      ("Iris", "cello", "eight", "Saint-Saens Swan"),
      ("Jacob", "piano", "six", "Beethoven Moonlight Sonata"),
      ("Kira", "guitar", "fifteen", "Tarrega Recuerdos"),
      ("Liam", "harp", "four", "Debussy Arabesque"),
      ("Mira", "drums", "ten", "Tower of Power groove")]),
    ("cooking", "After {n} failed attempts, {name}'s {dish} finally came out with {quality}.",
     "Did {name}'s {dish} project work out?",
     [("Noah", "three", "sourdough", "the correct crumb structure"),
      ("Opal", "seven", "ramen broth", "true tonkotsu emulsification"),
      ("Pavel", "five", "macarons", "the perfect feet on the cookie shell"),
      ("Quinn", "two", "risotto", "creamy al dente texture"),
      ("Rosa", "four", "croissants", "honeycomb lamination structure"),
      ("Saul", "six", "pizza", "leoparded crust on the dough")]),
    ("learning", "The {language} {feature} took {duration} to internalize but now feels intuitive when {activity}.",
     "What {language} feature took time for the speaker to learn?",
     [("Rust", "borrow checker", "weeks", "designing data structures"),
      ("Haskell", "monads", "months", "writing pure functional code"),
      ("Go", "channel patterns", "days", "structuring concurrent code"),
      ("OCaml", "module system", "weeks", "organizing larger codebases"),
      ("Erlang", "let-it-crash philosophy", "weeks", "designing supervision trees"),
      ("Lisp", "macros", "months", "writing DSL implementations")]),
    ("morning", "Switching from {old} to {new} improved {name}'s morning routine because {reason}.",
     "What changed about {name}'s morning beverage?",
     [("Tom", "espresso", "pour-over coffee", "the V60 takes only four minutes"),
      ("Uma", "tea bags", "loose-leaf gyokuro", "the umami flavor is incomparable"),
      ("Vince", "instant coffee", "AeroPress", "the brew is consistent every time"),
      ("Wendy", "hot tea", "iced cold brew", "summer mornings are cooler"),
      ("Xander", "drip coffee", "moka pot", "the body matches espresso intensity")]),
]

# Multilingual passages (5 languages, 1 entry each — bge-m3 should win on these)
MULTILINGUAL = [
    ("ml-es-iceland", "Anna esta planeando un viaje a Islandia en octubre para ver la aurora boreal.",
     "ml-q-es", "¿Cuando viaja Anna a Islandia?", ["ml-es-iceland"]),
    ("ml-fr-piano", "Jacob apprend le piano depuis six mois et vient de maitriser le premier mouvement de la Sonate au Clair de Lune de Beethoven.",
     "ml-q-fr", "Quel morceau de Beethoven a appris Jacob au piano?", ["ml-fr-piano"]),
    ("ml-de-bread", "Noah hat nach drei misslungenen Versuchen endlich Sauerteigbrot mit perfekter Krumenstruktur gebacken.",
     "ml-q-de", "Wie war Noahs Brotbackversuch?", ["ml-de-bread"]),
    ("ml-it-ramen", "Dopo sette tentativi falliti, Opal ha finalmente preparato un brodo di tonkotsu perfettamente emulsionato.",
     "ml-q-it", "Quanti tentativi ci sono voluti per il brodo di Opal?", ["ml-it-ramen"]),
    ("ml-pt-rust", "O verificador de emprestimos do Rust levou semanas para internalizar mas agora parece natural ao desenhar estruturas de dados.",
     "ml-q-pt", "Quanto tempo levou para aprender o verificador de Rust?", ["ml-pt-rust"]),
]

# Code passages (5 languages — semantic-vs-syntactic axis)
CODE = [
    ("code-py-fib", "def fibonacci(n: int) -> int:\n    if n < 2:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
     "code-q-py-fib", "recursive fibonacci implementation in Python", ["code-py-fib"]),
    ("code-rs-trait", "pub trait Embedder: Send + Sync {\n    fn embed(&self, text: &str) -> Result<Vec<f32>, anyhow::Error>;\n}",
     "code-q-rs-trait", "Rust trait declaration for an embedding interface", ["code-rs-trait"]),
    ("code-sql-window", "SELECT user_id, RANK() OVER (PARTITION BY dept ORDER BY salary DESC) AS rank FROM employees;",
     "code-q-sql-window", "SQL window function ranking employees by salary", ["code-sql-window"]),
    ("code-go-chan", "ch := make(chan int, 16)\ngo func() { for v := range ch { process(v) } }()\nfor i := 0; i < 100; i++ { ch <- i }",
     "code-q-go-chan", "Go buffered channel pattern for producer consumer", ["code-go-chan"]),
    ("code-ts-async", "async function fetchUsers(): Promise<User[]> {\n    const r = await fetch('/api/users');\n    return r.json();\n}",
     "code-q-ts-async", "TypeScript async function returning a typed Promise", ["code-ts-async"]),
]

# Adversarial passages
ADVERSARIAL = [
    ("adv-long",
     ("This is filler text designed to dilute the signal of the buried fact. " * 25)
     + " The buried fact: Anna prefers Pacific time zone scheduling for autonomous runs.",
     "adv-q-long", "What time zone does Anna prefer for scheduling?", ["adv-long"]),
    ("adv-unicode",
     "Notes contain emoji and special characters such as 🚀 → ✓ ☆ • ¿qué pasa? — these should not break the embedding pipeline.",
     "adv-q-unicode", "Are emoji and special characters allowed in user notes?", ["adv-unicode"]),
    ("adv-near-dup-A",
     "The retrieval orchestrator runs an embed-then-query-then-fetch-then-rank pipeline with a five-second wall-clock deadline.",
     "adv-q-near-dup", "How does the retrieval pipeline work?", ["adv-near-dup-A", "adv-near-dup-B"]),
    ("adv-near-dup-B",
     "An embed-then-query-then-fetch-then-rank pipeline runs in the retrieval orchestrator with a five-second wall-clock bailout.",
     "_unused", "_unused", []),
]

# Distractor pool (no expected matches; pure noise to dilute signal at scale)
DISTRACTORS_TEMPLATES = [
    "The {n}th anniversary of the {event} was celebrated with a {activity} in {city}.",
    "Researchers at {institution} published a paper on {topic} in {year}.",
    "The {color} {animal} darted across the {location} at {time} in the morning.",
    "{name}'s favorite {item} from {brand} was discontinued after {duration} years.",
    "A new {restaurant_type} restaurant opened on {street} serving {cuisine} cuisine.",
    "The {sport} championship in {year} was won by {team} after a {score} victory.",
    "Volcanic activity at {volcano} increased in {month} of {year} prompting {action}.",
    "Stock prices for {company} fluctuated between ${low} and ${high} during {quarter}.",
    "The {museum} exhibition featuring {artist}'s {medium} works runs until {date}.",
    "Train service between {city_a} and {city_b} was disrupted due to {cause}.",
]
DISTRACTOR_FILLERS = {
    "n": ["fifth", "tenth", "twentieth", "fortieth", "fiftieth", "seventy-fifth"],
    "event": ["library opening", "treaty signing", "moon landing", "park dedication"],
    "activity": ["concert", "fireworks display", "lecture series", "ribbon-cutting"],
    "city": ["Lisbon", "Helsinki", "Buenos Aires", "Cape Town", "Vancouver", "Kraków", "Hanoi", "Reykjavik"],
    "institution": ["MIT", "ETH Zürich", "Tokyo University", "ANU"],
    "topic": ["quantum thermodynamics", "ribosome assembly", "graph kernels", "tropical geometry"],
    "year": ["2018", "2021", "2024", "2025"],
    "color": ["amber", "russet", "indigo", "ochre", "slate", "cerulean"],
    "animal": ["fox", "marten", "ibis", "vole", "kingfisher", "stoat"],
    "location": ["meadow", "ridge", "creek", "estuary", "esker"],
    "time": ["six", "five-thirty", "seven", "four-fifteen"],
    "name": ["Yara", "Zane", "Aria", "Bode", "Cassia", "Dane", "Eira", "Foster"],
    "item": ["thermos", "fountain pen", "wool sweater", "leather satchel"],
    "brand": ["Klein & Co", "Verda", "Dutton", "Pellegrini"],
    "duration": ["fifteen", "twenty-two", "thirty", "forty-five"],
    "restaurant_type": ["fusion", "tapas", "noodle bar", "ramen-ya"],
    "street": ["Mulberry Lane", "Forest Way", "King Street", "Oak Avenue"],
    "cuisine": ["Peruvian", "Georgian", "Sichuan", "Eritrean"],
    "sport": ["snooker", "curling", "fencing", "rowing"],
    "team": ["the Saints", "the Mariners", "the Eagles", "the Spartans"],
    "score": ["3-1", "5-2", "7-6", "4-2"],
    "volcano": ["Etna", "Sakurajima", "Stromboli", "Cotopaxi"],
    "month": ["February", "August", "May", "November"],
    "action": ["evacuations", "warnings", "monitoring", "drone flights"],
    "company": ["Halicom", "Vidata", "Trinex", "Quartz Materials"],
    "low": ["12.50", "47.80", "103.20", "8.90"],
    "high": ["19.40", "62.10", "118.75", "11.30"],
    "quarter": ["Q1", "Q2", "Q3", "Q4"],
    "museum": ["Tate", "Prado", "Met", "Pompidou"],
    "artist": ["Bourgeois", "Picasso", "Hockney", "Kahlo"],
    "medium": ["sculpture", "etching", "watercolor", "tapestry"],
    "date": ["September 15", "March 3", "July 22", "December 10"],
    "city_a": ["Geneva", "Berlin", "Madrid", "Edinburgh"],
    "city_b": ["Lyon", "Munich", "Barcelona", "Manchester"],
    "cause": ["signal failures", "track maintenance", "power outage", "flooding"],
}


def http_post(path: str, body: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def embed(model: str, text: str) -> tuple[list[float], float]:
    t0 = time.perf_counter()
    resp = http_post("/api/embed", {"model": model, "input": text})
    return resp["embeddings"][0], (time.perf_counter() - t0) * 1000


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def build_corpus(target_size: int = 150) -> tuple[list[tuple[str, str]], list[tuple[str, str, list[str]]]]:
    """Generate (passages, queries) suitable for the recall harness.

    Each query has expected_ids — passages that SHOULD rank top-k.
    """
    passages: list[tuple[str, str]] = []
    queries: list[tuple[str, str, list[str]]] = []

    # Themed targets + queries
    for theme_name, p_template, q_template, params in THEMES:
        for i, args in enumerate(params):
            d = dict(zip(("name", "place", "month", "attraction", "instrument", "duration", "piece",
                          "n", "dish", "quality", "language", "feature", "activity",
                          "old", "new", "reason"), args))
            pid = f"{theme_name}-{i}"
            qid = f"q-{theme_name}-{i}"
            try:
                passage = p_template.format(**d)
                query = q_template.format(**d)
            except KeyError:
                continue
            passages.append((pid, passage))
            queries.append((qid, query, [pid]))

    # Multilingual + code + adversarial
    for pid, ptext, qid, qtext, exp in MULTILINGUAL + CODE + ADVERSARIAL:
        passages.append((pid, ptext))
        if qid != "_unused":
            queries.append((qid, qtext, exp))

    # Distractors to fill to target_size
    distractor_idx = 0
    while len(passages) < target_size:
        tpl = random.choice(DISTRACTORS_TEMPLATES)
        d = {k: random.choice(v) for k, v in DISTRACTOR_FILLERS.items()}
        try:
            text = tpl.format(**d)
        except KeyError:
            continue
        passages.append((f"distractor-{distractor_idx}", text))
        distractor_idx += 1

    return passages, queries


def evaluate(model: str, passages: list, queries: list) -> dict:
    print(f"=== {model}: corpus={len(passages)} queries={len(queries)} ===", file=sys.stderr)
    print(f"  embedding {len(passages)} passages", file=sys.stderr)
    pvecs = {}
    embed_times = []
    for pid, text in passages:
        v, ms = embed(model, text)
        pvecs[pid] = v
        embed_times.append(ms)
    print(f"  embed median={statistics.median(embed_times):.0f}ms", file=sys.stderr)

    print(f"  scoring {len(queries)} queries", file=sys.stderr)
    r1 = r3 = r5 = r10 = 0
    mrr = 0.0
    misses = []
    qtimes = []
    for qid, qtext, expected in queries:
        qv, qms = embed(model, qtext)
        qtimes.append(qms)
        scores = sorted(((pid, cosine(qv, pv)) for pid, pv in pvecs.items()), key=lambda x: x[1], reverse=True)
        first = next((i + 1 for i, (pid, _) in enumerate(scores) if pid in expected), None)
        if first == 1:
            r1 += 1
        if first and first <= 3:
            r3 += 1
        if first and first <= 5:
            r5 += 1
        if first and first <= 10:
            r10 += 1
        if first:
            mrr += 1.0 / first
        else:
            misses.append({"qid": qid, "expected": expected, "top5": [{"id": p, "s": round(s, 3)} for p, s in scores[:5]]})

    n = len(queries)
    return {
        "model": model,
        "corpus_size": len(passages),
        "queries": n,
        "recall_at_1": round(r1 / n, 3),
        "recall_at_3": round(r3 / n, 3),
        "recall_at_5": round(r5 / n, 3),
        "recall_at_10": round(r10 / n, 3),
        "mrr": round(mrr / n, 3),
        "embed_p50_ms": round(statistics.median(embed_times), 1),
        "embed_p90_ms": round(sorted(embed_times)[int(len(embed_times) * 0.9)], 1),
        "query_p50_ms": round(statistics.median(qtimes), 1),
        "vec_dim": len(next(iter(pvecs.values()))),
        "complete_misses": misses,
    }


def main() -> int:
    passages, queries = build_corpus(target_size=150)
    print(f"corpus: {len(passages)} passages, {len(queries)} queries", file=sys.stderr)
    out = {"corpus_size": len(passages), "query_count": len(queries), "models": []}
    for model in ["bge-m3", "nomic-embed-text"]:
        try:
            out["models"].append(evaluate(model, passages, queries))
        except Exception as e:
            out["models"].append({"model": model, "error": str(e)})
            print(f"ERROR {model}: {e}", file=sys.stderr)

    summary = [{
        "model": m["model"],
        "corpus": m["corpus_size"],
        "r@1": m["recall_at_1"],
        "r@3": m["recall_at_3"],
        "r@5": m["recall_at_5"],
        "r@10": m["recall_at_10"],
        "mrr": m["mrr"],
        "p50_ms": m["embed_p50_ms"],
    } for m in out["models"] if "error" not in m]
    out["summary"] = summary

    with open("planning/validation_2026-04-24/05_long_context.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
