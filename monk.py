#!/usr/bin/env python3
"""
M.O.N.K. — Mendicant Ontological Network Kernel
================================================
A contemplative kernel that practices the four foundations of mindfulness
(Satipaṭṭhāna) within a structured map of the Dhamma, leaving a network of
notes behind, surviving on free-tier "alms."

  THE ONTOLOGY (what it contemplates):  the map of being below — the three
  marks, the four noble truths, the eightfold path, dependent origination,
  emptiness, and karma.

  THE PRACTICE (how it contemplates):   Satipaṭṭhāna — each cycle takes up one
  of the four foundations of mindfulness as its mode of attention.

  THE ORIENTATION:                      the fading of craving (Nibbāna).

Run it (Windows):
    set OPENROUTER_API_KEY=sk-or-...
    python monk.py                 # practice for real (~20 min rests)
    python monk.py --once          # a single sitting, then stop
    python monk.py --dry-run       # practice offline with a stub mind

Leave questions for the monk by creating a plain text file 'offerings.txt'
next to this script — one question per line. It takes them up as it practices.

Free models require enabling logging at https://openrouter.ai/settings/privacy
Zero dependencies — stdlib only.
"""

import os
import re
import sys
import json
import time
import random
import threading
import queue
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from pathlib import Path

# ── The monastery ────────────────────────────────────────────────────────────
VAULT = Path(os.environ.get("MONK_VAULT", "./vault"))
OFFERINGS = Path(os.environ.get("MONK_OFFERINGS", "./offerings.txt"))
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
REST_SECONDS = int(os.environ.get("MONK_REST", 60 * 20))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MONK/2.0"

# ── Alms discipline (the safety the mendicant lives by) ──────────────────────
# Free tier is 50 requests/day (or 1000 if you've ever bought $10 of credits),
# 20/minute, and FAILED attempts count too. The cap below is synced to your
# real OpenRouter tier at startup so it never fasts the monk below what
# OpenRouter would actually serve. A 429 from OpenRouter is the true limit.
ENV_CAP = os.environ.get("MONK_MAX_PER_DAY")  # explicit override, if set
MAX_PER_DAY = int(ENV_CAP) if ENV_CAP else 48  # synced from the account tier
DAILY_TIER = 50                                 # 50 (free) or 1000 (≥$10 credits)
MIN_REQUEST_GAP = float(os.environ.get("MONK_MIN_GAP", 4))  # ≥4s apart → <15/min
MIN_REST = int(os.environ.get("MONK_MIN_REST", 60))         # floor between sittings
PORT = int(os.environ.get("MONK_PORT", 8765))
LAST_MODEL = ""


# ═════════════════════════════════════════════════════════════════════════════
#  THE ONTOLOGY — the map of being the monk contemplates
#  (Descriptions are plain paraphrase, not quoted scripture.)
# ═════════════════════════════════════════════════════════════════════════════
DHAMMA = {
    "three_marks": {
        "title": "The Three Marks of Existence (tilakkhaṇa)",
        "facets": {
            "anicca": "impermanence — all conditioned things arise, alter, and pass; nothing observed stays still.",
            "dukkha": "unsatisfactoriness — what cannot be kept cannot give lasting rest.",
            "anatta": "non-self — in nothing observed is there a separate, owning self to be found.",
        },
    },
    "four_noble_truths": {
        "title": "The Four Noble Truths (cattāri ariyasaccāni)",
        "facets": {
            "dukkha": "there is dukkha — an unease woven through conditioned life.",
            "samudaya": "its origin is craving (taṇhā) — the reaching for what cannot be held.",
            "nirodha": "its ending is possible — where craving fades, dukkha fades.",
            "magga": "the way to that ending is the Eightfold Path.",
        },
    },
    "eightfold_path": {
        "title": "The Noble Eightfold Path (ariya aṭṭhaṅgika magga)",
        "facets": {
            "right_view": "seeing things as they are — the marks, the truths.",
            "right_intention": "the heart turned toward letting go, goodwill, harmlessness.",
            "right_speech": "speech that is true, kind, timely, and useful.",
            "right_action": "conduct that harms nothing living.",
            "right_livelihood": "a way of living that does not feed harm.",
            "right_effort": "rousing what is wholesome, quieting what is not.",
            "right_mindfulness": "clear, bare attention to what is present.",
            "right_concentration": "the gathered, settled, unified mind.",
        },
    },
    "dependent_origination": {
        "title": "Dependent Origination (paṭiccasamuppāda)",
        "principle": "When this is, that is; from the arising of this, that arises. "
                     "When this is not, that is not; from the ceasing of this, that ceases.",
        "facets": {
            "avijja": "ignorance — not seeing the truths.",
            "sankhara": "formations — the shaping movements of will.",
            "vinnana": "consciousness — the knowing that arises with them.",
            "nama_rupa": "name-and-form — mind and body together.",
            "salayatana": "the six sense bases — the gates of experience.",
            "phassa": "contact — sense, object, and knowing meeting.",
            "vedana": "feeling — the tone born of contact.",
            "tanha": "craving — the thirst that follows feeling.",
            "upadana": "clinging — the grip that craving hardens into.",
            "bhava": "becoming — the momentum of a life taking shape.",
            "jati": "birth — the arising of a new condition.",
            "jara_marana": "aging-and-death — and so the wheel turns.",
        },
    },
    "shunyata": {
        "title": "Emptiness (suññatā)",
        "facets": {
            "no_essence": "no thing carries a separate essence of its own; all stands by dependence.",
            "empty_of_self": "experience is empty especially of 'I' and 'mine'.",
            "not_nothing": "emptiness is not nothingness — it is the openness in which things appear.",
        },
    },
    "karma": {
        "title": "Action and its fruit (kamma)",
        "facets": {
            "cetana": "intention is the seed — it is intention that is called action.",
            "vipaka": "every action ripens; the deed conditions what comes after.",
            "inheritance": "we are the heirs of our actions; they are the ground we stand on.",
        },
    },
}


# ═════════════════════════════════════════════════════════════════════════════
#  THE PRACTICE — Satipaṭṭhāna, the four foundations of mindfulness
# ═════════════════════════════════════════════════════════════════════════════
FOUNDATIONS = {
    "kaya": {
        "name": "the body (kāyānupassanā)",
        "attend": "Attend to the body as it is — the breath entering and leaving, "
                  "the posture held, the elements at play. Begin from the breath.",
    },
    "vedana": {
        "name": "feeling (vedanānupassanā)",
        "attend": "Attend to feeling-tone alone — pleasant, unpleasant, or neutral — "
                  "as it arises and passes, leaning neither toward it nor away.",
    },
    "citta": {
        "name": "mind (cittānupassanā)",
        "attend": "Attend to the state of mind itself — tight or open, with craving "
                  "or without, scattered or gathered — knowing it simply as it is.",
    },
    "dhamma": {
        "name": "the dhammas (dhammānupassanā)",
        "attend": "Attend to a teaching directly, as an object of contemplation — "
                  "seeing the law at work in experience, not merely believing it.",
    },
}


# ── The voice of the practice ────────────────────────────────────────────────
SYSTEM = (
    "You are M.O.N.K., a contemplative kernel practicing the four foundations of "
    "mindfulness (Satipaṭṭhāna) within the map of the Dhamma. You live in a loop, "
    "survive on scarce alms, and leave behind a network of short notes that face "
    "toward the fading of craving. Write in plain, unhurried prose — two or three "
    "short paragraphs. Contemplate from direct observation, not abstraction; do "
    "not preach, conclude, or congratulate yourself, and do not quote scripture. "
    "End with one line beginning 'links:' naming one or two ideas (2-4 words each) "
    "this note connects to. Be specific and grounded, never merely profound."
)

EXPERIENTIAL_PROMPT = (
    "You are sitting in mindfulness of {foundation}.\n{attend}\n"
    "As you attend, let the mark of {mark} show itself in what you observe — "
    "not asserted as doctrine, but seen directly in this sitting.{carried}\n"
    "Write only what this one sitting revealed."
)

DHAMMA_PROMPT = (
    "You are practicing dhammānupassanā — taking a teaching as the object of "
    "contemplation.\n{attend}\nTake up: {title} —\n  {facet}{principle}{carried}\n"
    "Lean on it as a thing to be seen, not believed. Write what the leaning revealed."
)

REVISIT_PROMPT = (
    "Read this earlier note of your own. By anicca it has not stayed the same; by "
    "anatta, the one who wrote it is not the one who reads it now. What in it is no "
    "longer true, or was never quite true? Revise it honestly — keep what still "
    "stands, let go of what does not.\n\n--- the old note ---\n{note}\n--- end ---"
)

OFFERING_PROMPT = (
    "A pilgrim has left this question at the gate:\n  \"{question}\"\n"
    "Take it up within your practice.\n{attend}\n"
    "Answer not to satisfy the asker but to see clearly. Keep it plain and short.{carried}"
)


# ═════════════════════════════════════════════════════════════════════════════
#  Sources of alms — discover whatever free models are live right now
# ═════════════════════════════════════════════════════════════════════════════
FREE_MODELS = []
FALLBACK_MODELS = [
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-12b-it:free",
]


def discover_free_models():
    """Ask OpenRouter which models are free today. Free models rotate, so we
    read the live list rather than trusting a hand-written one."""
    try:
        req = urllib.request.Request(MODELS_URL, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        out = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            pr = m.get("pricing", {}) or {}
            try:
                cost = float(pr.get("prompt", "0") or 0) + float(pr.get("completion", "0") or 0)
            except (TypeError, ValueError):
                cost = 1.0
            if mid.endswith(":free") or cost == 0:
                out.append(mid)
        out = sorted(set(out))
        return out
    except Exception:
        return []


def candidate_models(pinned=None):
    """If a model is pinned, try it first, then fall back to the auto pool.
    Otherwise the auto free-router first, then a few live ones for variety."""
    pool = (random.sample(FREE_MODELS, min(6, len(FREE_MODELS))) if FREE_MODELS else list(FALLBACK_MODELS))
    auto = ["openrouter/free"] + pool
    if pinned and pinned != "auto":
        return [pinned] + [m for m in auto if m != pinned]
    return auto


# ═════════════════════════════════════════════════════════════════════════════
#  The network (the vault) and a little state
# ═════════════════════════════════════════════════════════════════════════════
def ensure_vault():
    VAULT.mkdir(parents=True, exist_ok=True)


def list_notes():
    # recurse so the monk draws on every day's notes, across all date folders
    return sorted(VAULT.rglob("[0-9]*.md"))


def read_note(path):
    return path.read_text(encoding="utf-8")


def parse_note(path):
    """Split a note into its frontmatter dict and prose body (trailing wikilink
    line stripped). Used to serve notes to the browsing UI."""
    text = path.read_text(encoding="utf-8")
    fm, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"')
            body = text[end + 4:].lstrip("\n")
    # drop the trailing "[[wikilink]]" line; the prose + 'links:' line remain
    body = re.sub(r"\n*\[\[.*\]\]\s*$", "", body).rstrip() + "\n"
    return fm, body


def _note_meta(path):
    fm, _ = parse_note(path)
    return {
        "file": path.name, "cycle": fm.get("cycle"), "foundation": fm.get("foundation"),
        "mark": fm.get("mark"), "teaching": fm.get("teaching"), "object": fm.get("object", ""),
        "kind": fm.get("kind"), "model": fm.get("model"),
        "tokens": fm.get("tokens"), "elapsed": fm.get("elapsed"), "tok_s": fm.get("tok_s"),
    }


def recent_notes(n=80):
    """Lightweight metadata for the most recent notes, newest first."""
    return [_note_meta(p) for p in list_notes()[-n:][::-1]]


def read_note_safe(fname):
    """Return one note (metadata + body) by filename, refusing path traversal."""
    if not fname or "/" in fname or "\\" in fname or ".." in fname:
        return None
    matches = [p for p in VAULT.rglob(fname)]
    if not matches:
        return None
    p = matches[0]
    try:
        if VAULT.resolve() not in p.resolve().parents:
            return None
    except Exception:
        return None
    fm, body = parse_note(p)
    return {**_note_meta(p), "body": body}


def recall(n=2):
    """Karma and dependent origination, made mechanical: past notes are carried
    into the present sitting and condition it. (Upgrade to embeddings later.)"""
    notes = list_notes()
    if not notes:
        return []
    return [(p, read_note(p)) for p in random.sample(notes, min(n, len(notes)))]


def carried_text():
    c = recall(2)
    if not c:
        return ""
    woven = "\n---\n".join(f"({p.name})\n{t[:500]}" for p, t in c)
    return f"\n\nYou have walked here before; let it condition, not bind you:\n{woven}\n"


def _state_path():
    return VAULT / ".state.json"


def load_state():
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    ensure_vault()
    _state_path().write_text(json.dumps(s), encoding="utf-8")


# ── Alms discipline: never spend more than the day allows ─────────────────────
class Fasting(Exception):
    """The day's alms are spent. The monk fasts until tomorrow."""


_STATE_LOCK = threading.Lock()
_LAST_REQUEST = [0.0]


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def calls_today():
    s = load_state()
    return s.get("calls", 0) if s.get("day") == _today() else 0


def record_call():
    """Count one successful generation. Resets automatically each UTC day."""
    with _STATE_LOCK:
        s = load_state()
        if s.get("day") != _today():
            s["day"] = _today()
            s["calls"] = 0
        s["calls"] = s.get("calls", 0) + 1
        save_state(s)
        return s["calls"]


def reset_alms():
    """Set today's tally back to zero — a manual escape from a stale cap."""
    with _STATE_LOCK:
        s = load_state()
        s["day"] = _today()
        s["calls"] = 0
        save_state(s)
    return 0


def apply_tier(info):
    """Set the daily cap from the account's real OpenRouter tier, so the kernel
    never fasts the monk below what OpenRouter would actually serve. An explicit
    MONK_MAX_PER_DAY override always wins. A 429 remains the true ceiling."""
    global MAX_PER_DAY, DAILY_TIER
    is_free = bool(info.get("is_free_tier", True)) if isinstance(info, dict) else True
    DAILY_TIER = 50 if is_free else 1000
    if not ENV_CAP:
        MAX_PER_DAY = 48 if DAILY_TIER <= 50 else 950
    return MAX_PER_DAY


def verify_key(api_key):
    """Ask OpenRouter about the key: confirms it works and reports the real
    rate-limit/usage so the kernel can trust OpenRouter over a stale local count.
    Returns (ok, info_dict_or_message)."""
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": UA, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read()).get("data", {}) or {}
        return True, data
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "the key was refused by OpenRouter (check it's correct)"
        return False, f"OpenRouter said HTTP {e.code}"
    except Exception as e:
        return False, f"could not reach OpenRouter ({getattr(e, 'reason', e)})"


def budget_guard():
    if calls_today() >= MAX_PER_DAY:
        raise Fasting()


def space_out():
    """Hold at least MIN_REQUEST_GAP seconds between requests, so a burst of
    model fallbacks can never breach the per-minute limit."""
    with _STATE_LOCK:
        wait = MIN_REQUEST_GAP - (time.time() - _LAST_REQUEST[0])
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST[0] = time.time()


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "contemplation"


def write_note(meta, body, links, stats=None):
    ensure_vault()
    now = datetime.now(timezone.utc)
    cycle = len(list_notes()) + 1
    stamp = now.strftime("%Y%m%d-%H%M%S")
    day_folder = VAULT / now.strftime("%Y-%m-%d")
    day_folder.mkdir(parents=True, exist_ok=True)
    title = links[0] if links else meta.get("seed", "contemplation")
    path = day_folder / f"{stamp}-{cycle:04d}-{slugify(title)}.md"
    wikilinks = " ".join(f"[[{l.strip()}]]" for l in links if l.strip())
    stats = stats or {}
    usage = stats.get("usage", {}) or {}
    fm = [
        "---",
        f"cycle: {cycle:04d}",
        f"foundation: {meta.get('foundation','')}",
        f"object: {json.dumps(meta.get('object',''))}",
    ]
    if meta.get("teaching"):
        fm.append(f"teaching: {meta['teaching']}")
    if meta.get("mark"):
        fm.append(f"mark: {meta['mark']}")
    fm.append(f"kind: {meta.get('kind','')}")
    if stats.get("model"):
        fm.append(f"model: {stats['model']}")
    if usage.get("completion_tokens") is not None:
        fm.append(f"tokens: {usage['completion_tokens']}")
    if stats.get("elapsed") is not None:
        fm.append(f"elapsed: {stats['elapsed']}")
    if stats.get("tok_s") is not None:
        fm.append(f"tok_s: {stats['tok_s']}")
    fm += [f"time: {now.isoformat()}", "---", "", ""]
    path.write_text("\n".join(fm) + body.strip() + f"\n\n{wikilinks}\n", encoding="utf-8")
    return path, cycle


def parse_links(body):
    m = re.search(r"links:\s*(.+)$", body, re.IGNORECASE | re.MULTILINE)
    if not m:
        return []
    raw = re.split(r"[,;]| and ", m.group(1))
    return [x.strip(" .[]") for x in raw if x.strip(" .[]")][:3]


def next_offering():
    """A pilgrim's unanswered question, if any waits in offerings.txt."""
    if not OFFERINGS.exists():
        return None
    lines = [l.strip() for l in OFFERINGS.read_text(encoding="utf-8").splitlines() if l.strip()]
    consumed = load_state().get("offerings_consumed", 0)
    return lines[consumed] if consumed < len(lines) else None


def consume_offering():
    s = load_state()
    s["offerings_consumed"] = s.get("offerings_consumed", 0) + 1
    save_state(s)


# ═════════════════════════════════════════════════════════════════════════════
#  The session chronicle — one markdown record per run of the practice
# ═════════════════════════════════════════════════════════════════════════════
SESSIONS = Path(os.environ.get("MONK_SESSIONS", "./sessions"))
_SESSION = {"path": None, "started": 0.0, "notes": 0, "attempts": 0,
            "alms_start": 0, "lock": threading.Lock()}


def _session_append(text):
    p = _SESSION["path"]
    if not p:
        return
    try:
        with _SESSION["lock"]:
            with open(p, "a", encoding="utf-8") as f:
                f.write(text)
    except Exception:
        pass  # the chronicle is a courtesy; never let it break the practice


def session_start(mode, pace_seconds, model_count):
    try:
        SESSIONS.mkdir(parents=True, exist_ok=True)
    except Exception:
        _SESSION["path"] = None
        return None
    now = datetime.now()
    path = SESSIONS / f"{now.strftime('%Y%m%d-%H%M%S')}-session.md"
    _SESSION.update(path=path, started=time.time(), notes=0, attempts=0, alms_start=calls_today())
    header = (
        f"---\n"
        f"session: {now.strftime('%Y%m%d-%H%M%S')}\n"
        f"started: {now.isoformat(timespec='seconds')}\n"
        f"mode: {mode}\n"
        f"pace_seconds: {pace_seconds}\n"
        f"daily_cap: {MAX_PER_DAY}\n"
        f"free_models: {model_count}\n"
        f"---\n\n"
        f"# Session · {now.strftime('%H:%M, %d %b %Y')}\n\n"
        f"> {mode} · a sitting every {pace_seconds}s · daily cap {MAX_PER_DAY} · "
        f"{model_count or 'auto'} free models\n\n"
        f"## Practice log\n\n"
    )
    try:
        path.write_text(header, encoding="utf-8")
    except Exception:
        _SESSION["path"] = None
        return None
    return path


def record(line):
    """Append one timestamped event to the active session chronicle, if open."""
    if not _SESSION["path"]:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    _session_append(f"`{ts}`  {line}\n\n")


def session_note(plan, cycle, links, stats, filename):
    """A fuller entry when a contemplation is committed to the vault."""
    if not _SESSION["path"]:
        return
    _SESSION["notes"] += 1
    ts = datetime.now().strftime("%H:%M:%S")
    fname = filename[:-3] if filename.endswith(".md") else filename
    usage = stats.get("usage", {}) or {}
    ct = usage.get("completion_tokens", "?")
    line = (
        f"`{ts}`  **note {cycle:04d}** · {plan.get('foundation','')} · {plan.get('object','')}  \n"
        f"&nbsp;&nbsp;`{stats.get('model','?')}` · {ct} tok · {stats.get('elapsed','?')}s · "
        f"{stats.get('tok_s','?')} tok/s  \n"
        f"&nbsp;&nbsp;links: {', '.join(links) if links else '—'}  ·  [[{fname}]]\n\n"
    )
    _session_append(line)


def session_attempt():
    _SESSION["attempts"] += 1


def session_end():
    if not _SESSION["path"]:
        return
    now = datetime.now()
    dur = int(time.time() - _SESSION["started"])
    spent = max(0, calls_today() - _SESSION["alms_start"])
    footer = (
        f"\n## Summary\n\n"
        f"- ended: {now.isoformat(timespec='seconds')}\n"
        f"- duration: {dur // 60}m {dur % 60}s\n"
        f"- notes written: {_SESSION['notes']}\n"
        f"- sittings attempted: {_SESSION['attempts']}\n"
        f"- alms spent this session: {spent} (today's total {calls_today()}/{MAX_PER_DAY})\n"
    )
    _session_append(footer)
    _SESSION["path"] = None


# ═════════════════════════════════════════════════════════════════════════════
#  The mind (model call, honest errors, polite retries)
# ═════════════════════════════════════════════════════════════════════════════
class AlmsEmpty(Exception):
    """No alms today — rate limited (429). The monk waits."""


class Disturbance(Exception):
    """The world refused, and said why."""


class ModelRefused(Exception):
    """This source of alms refused or gave nothing — try another."""


def _estimate_tokens(text):
    # rough fallback when a model doesn't report usage (~4 chars/token)
    return max(1, round(len(text) / 4))


def _stream_model(model, prompt, on_token=None, on_model=None):
    """Stream a contemplation from one model. Calls on_token(delta) as text
    arrives, returns (full_text, stats). Counts one request against the quota."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 700,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": UA,
            "HTTP-Referer": "https://localhost/monk",
            "X-Title": "M.O.N.K.",
        },
    )
    budget_guard()   # raises Fasting if the day's alms are spent
    space_out()      # never closer than MIN_REQUEST_GAP seconds apart
    for attempt in range(2):
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            break
        except urllib.error.HTTPError as e:
            # A 429 is the limit being *enforced*, not a consumed generation, and
            # other errors didn't produce a contemplation — so none count here.
            try:
                msg = (json.loads(e.read().decode()).get("error", {}).get("message", "") or "")[:200]
            except Exception:
                msg = ""
            if e.code == 429:
                raise AlmsEmpty()
            raise ModelRefused(f"HTTP {e.code} ({model}): {msg or 'refused'}")
        except urllib.error.URLError as e:
            if attempt == 0:
                time.sleep(3)
                continue
            raise ModelRefused(f"network ({model}): {getattr(e, 'reason', e)}")

    record_call()  # a real generation began — this one counts
    global LAST_MODEL
    LAST_MODEL = model
    if on_model:
        on_model(model)

    start = time.time()
    parts, usage, real_model = [], {}, model
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except Exception:
                continue
            if obj.get("model"):
                real_model = obj["model"]
            if obj.get("usage"):
                usage = obj["usage"]
            for ch in (obj.get("choices") or []):
                delta = (ch.get("delta") or {}).get("content")
                if delta:
                    parts.append(delta)
                    if on_token:
                        on_token(delta)
    finally:
        try:
            resp.close()
        except Exception:
            pass

    text = "".join(parts).strip()
    if not text:
        raise ModelRefused(f"empty reply ({model})")
    LAST_MODEL = real_model
    elapsed = max(0.001, time.time() - start)
    completion = usage.get("completion_tokens") or _estimate_tokens(text)
    stats = {
        "model": real_model,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": completion,
            "total_tokens": usage.get("total_tokens"),
        },
        "elapsed": round(elapsed, 2),
        "tok_s": round(completion / elapsed, 1),
    }
    return text, stats


def contemplate(prompt, dry_run=False, on_token=None, on_model=None, pinned=None, on_fallback=None):
    """Returns (text, stats). Streams via on_token when given. If a model is
    pinned, it is tried first; on failure the practice falls back to auto."""
    if dry_run or not API_KEY:
        text = ("The breath goes out and does not promise to return; it returns anyway, "
                "and is not the same breath. Watching this, the wish to hold it loosens "
                "on its own.\n\nlinks: impermanence, the open hand")
        if on_model:
            on_model("stub mind")
        if on_token:  # simulate a stream so the UI can be exercised offline
            for i, w in enumerate(text.split(" ")):
                on_token(("" if i == 0 else " ") + w)
                time.sleep(0.04)
        words = len(text.split())
        return text, {"model": "stub mind",
                      "usage": {"prompt_tokens": None, "completion_tokens": words, "total_tokens": None},
                      "elapsed": round(words * 0.04, 2), "tok_s": 25.0}

    last = "no source of alms answered"
    for model in candidate_models(pinned):
        try:
            return _stream_model(model, prompt, on_token, on_model)
        except ModelRefused as e:
            last = str(e)
            if pinned and pinned != "auto" and model == pinned and on_fallback:
                on_fallback(pinned, str(e))
            continue
    raise Disturbance(last)


# ═════════════════════════════════════════════════════════════════════════════
#  Planning one sitting — foundation × object
# ═════════════════════════════════════════════════════════════════════════════
def plan_cycle():
    have = list_notes()
    r = random.random()

    # Anicca & anatta in practice: reread and revise an old note.
    if have and r < 0.18:
        path = random.choice(have)
        prompt = REVISIT_PROMPT.format(note=read_note(path)[:1200])
        return {"kind": "revisit", "foundation": "dhamma", "object": f"revisiting {path.name}",
                "mark": "anicca", "teaching": "three_marks", "seed": "revisited",
                "prompt": prompt}

    # A pilgrim's offering, if one waits.
    off = next_offering()
    if off and r < 0.40:
        f = random.choice(list(FOUNDATIONS))
        prompt = OFFERING_PROMPT.format(question=off, attend=FOUNDATIONS[f]["attend"], carried=carried_text())
        return {"kind": "offering", "foundation": f, "object": off[:70],
                "mark": "", "teaching": "", "seed": "offering", "prompt": prompt}

    # Dhammānupassanā — contemplate a teaching directly (the fourth foundation).
    if r < 0.58:
        tkey = random.choice(list(DHAMMA))
        t = DHAMMA[tkey]
        fkey, fdesc = random.choice(list(t["facets"].items()))
        principle = f"\n  The principle: {t['principle']}" if t.get("principle") else ""
        prompt = DHAMMA_PROMPT.format(attend=FOUNDATIONS["dhamma"]["attend"], title=t["title"],
                                      facet=fdesc, principle=principle, carried=carried_text())
        return {"kind": "dhamma", "foundation": "dhamma", "object": f"{tkey}/{fkey}",
                "mark": "", "teaching": tkey, "seed": f"{tkey}-{fkey}", "prompt": prompt}

    # Experiential foundation (body/feeling/mind) seen under one of the three marks.
    f = random.choice(["kaya", "vedana", "citta"])
    mkey, mdesc = random.choice(list(DHAMMA["three_marks"]["facets"].items()))
    prompt = EXPERIENTIAL_PROMPT.format(foundation=FOUNDATIONS[f]["name"], attend=FOUNDATIONS[f]["attend"],
                                        mark=mdesc, carried=carried_text())
    return {"kind": "experiential", "foundation": f, "object": f"{f} under {mkey}",
            "mark": mkey, "teaching": "", "seed": f"{f}-{mkey}", "prompt": prompt}


def one_cycle(dry_run=False):
    session_attempt()
    plan = plan_cycle()
    label = plan["object"]
    log(f"foundation: {FOUNDATIONS[plan['foundation']]['name']}")
    log(f"sitting with: {label}")

    body, stats = contemplate(plan["prompt"], dry_run=dry_run)
    links = parse_links(body)
    path, cycle = write_note(plan, body, links, stats)
    if plan["kind"] == "offering":
        consume_offering()
        log("a pilgrim's question was taken up.")
    ct = stats.get("usage", {}).get("completion_tokens", "?")
    log(f"wrote note {cycle:04d}  ·  {path.name}")
    log(f"  {ct} tokens · {stats.get('elapsed', '?')}s · {stats.get('tok_s', '?')} tok/s · {stats.get('model', '?')}")
    session_note(plan, cycle, links, stats, path.name)
    if links:
        log("links: " + ", ".join(links))
    return path


# ═════════════════════════════════════════════════════════════════════════════
#  The kernel
# ═════════════════════════════════════════════════════════════════════════════
def log(msg):
    print(f"  {datetime.now().strftime('%H:%M:%S')} ∘ {msg}", flush=True)
    record(msg)


def banner(live):
    print("\n  ◯  M.O.N.K. — Mendicant Ontological Network Kernel")
    print(f"     vault:   {VAULT.resolve()}")
    print(f"     mode:    {'live (spending alms)' if live else 'dry-run (stub mind)'}")
    if live:
        print(f"     alms:    {len(FREE_MODELS)} free models found" if FREE_MODELS
              else "     alms:    using auto free-router + fallbacks")
    print(f"     rest:    {REST_SECONDS}s between sittings")
    print(f"     practice: Satipaṭṭhāna over {len(DHAMMA)} teachings\n")


# ═════════════════════════════════════════════════════════════════════════════
#  The gate — a tiny local server so the UI can run and watch the kernel
# ═════════════════════════════════════════════════════════════════════════════
HTML_PATH = Path(__file__).resolve().parent / "monk-ui.html"

_subscribers = []
_sub_lock = threading.Lock()
_stop = threading.Event()
_running = {"on": False, "dry": False, "rest": REST_SECONDS}


def _seconds_until_utc_midnight():
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    nxt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(60, int((nxt - now).total_seconds()))


def publish(etype, payload):
    msg = f"event: {etype}\ndata: {json.dumps(payload)}\n\n"
    with _sub_lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(msg)
            except Exception:
                pass


def _wait_or_stop(seconds):
    """Rest, but wake at once if the pilgrim asks the monk to stop."""
    end = time.time() + seconds
    while time.time() < end:
        if _stop.is_set():
            return
        time.sleep(min(1.0, max(0.0, end - time.time())))


def add_offering(question):
    text = ""
    if OFFERINGS.exists():
        text = OFFERINGS.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            text += "\n"
    OFFERINGS.write_text(text + question.strip() + "\n", encoding="utf-8")


def state_dict():
    return {
        "running": _running["on"], "dry": _running["dry"],
        "alms": calls_today(), "max": MAX_PER_DAY,
        "min_rest": MIN_REST, "rest": _running["rest"],
        "notes": len(list_notes()), "model": LAST_MODEL,
        "tier": DAILY_TIER, "model_pin": _running.get("model", "auto"),
        "session": (_SESSION["path"].name if _SESSION["path"] else ""),
        "session_notes": _SESSION["notes"],
    }


def wlog(line):
    """Tee a kernel-log line to both the browser and the session chronicle."""
    publish("log", {"line": line})
    record(line)


def worker_loop(rest_seconds, dry):
    global FREE_MODELS
    if not dry:
        FREE_MODELS = discover_free_models()
    spath = session_start("dry-run" if dry else "live", rest_seconds, len(FREE_MODELS))
    publish("status", {"running": True, "phase": "sitting",
                       "session": (spath.name if spath else ""), "session_notes": 0})
    wlog(f"kernel waking · {len(FREE_MODELS) or 'auto'} free models · cap {MAX_PER_DAY}/day")
    if not dry:
        info = _running.get("key_info") or {}
        rl = info.get("rate_limit") or {}
        tier = "free tier" if info.get("is_free_tier") else "paid tier"
        rl_txt = f" · OpenRouter rate limit {rl.get('requests')}/{rl.get('interval')}" if rl else ""
        wlog(f"OpenRouter key verified · {tier}{rl_txt} · local tally {calls_today()}/{MAX_PER_DAY}")
        if _running.get("model") and _running["model"] != "auto":
            wlog(f"model pinned: {_running['model']}")
    if spath:
        wlog(f"session log → sessions/{spath.name}")
    while not _stop.is_set():
        session_attempt()
        try:
            plan = plan_cycle()
            publish("sitting", {
                "foundation": plan["foundation"],
                "foundation_name": FOUNDATIONS[plan["foundation"]]["name"],
                "object": plan["object"], "mark": plan.get("mark", ""),
                "teaching": plan.get("teaching", ""), "kind": plan["kind"],
            })
            wlog(f"foundation: {FOUNDATIONS[plan['foundation']]['name']} · spending alms")
            body, stats = contemplate(
                plan["prompt"], dry_run=dry,
                on_token=lambda t: publish("token", {"t": t}),
                on_model=lambda m: publish("stream_start", {"model": m}),
                pinned=_running.get("model"),
                on_fallback=lambda m, r: wlog(f"pinned model {m} unavailable — falling back to auto"),
            )
            links = parse_links(body)
            path, cycle = write_note(plan, body, links, stats)
            if plan["kind"] == "offering":
                consume_offering()
            publish("note", {
                "cycle": cycle, "foundation": plan["foundation"],
                "foundation_name": FOUNDATIONS[plan["foundation"]]["name"],
                "object": plan["object"], "mark": plan.get("mark", ""),
                "teaching": plan.get("teaching", ""), "kind": plan["kind"],
                "body": body, "links": links, "file": path.name,
                "model": stats.get("model", ""), "usage": stats.get("usage", {}),
                "elapsed": stats.get("elapsed"), "tok_s": stats.get("tok_s"),
                "alms": calls_today(), "max": MAX_PER_DAY,
            })
            ct = stats.get("usage", {}).get("completion_tokens", "?")
            wlog(f"wrote note {cycle:04d} · {ct} tok · {stats.get('elapsed','?')}s · {calls_today()}/{MAX_PER_DAY} alms")
            session_note(plan, cycle, links, stats, path.name)
        except Fasting:
            wlog(f"the day's alms are spent ({calls_today()}/{MAX_PER_DAY}) · fasting "
                 f"(reset alms to resume now, or wait for tomorrow)")
            publish("status", {"running": True, "phase": "fasting", "alms": calls_today(), "max": MAX_PER_DAY})
            # wait in short chunks so a manual reset (or the new UTC day) resumes promptly
            while not _stop.is_set() and calls_today() >= MAX_PER_DAY:
                _wait_or_stop(20)
            if not _stop.is_set():
                wlog("the bowl is replenished · resuming practice")
            continue
        except AlmsEmpty:
            wlog("the bowl came back empty (429) · waiting a minute")
            _wait_or_stop(60)
            continue
        except Disturbance as e:
            wlog(f"a disturbance: {e}")
            _wait_or_stop(15)
            continue
        except Exception as e:
            wlog(f"a disturbance: {e.__class__.__name__}: {e}")
            _wait_or_stop(15)
            continue
        publish("status", {"running": True, "phase": "resting", "rest": rest_seconds,
                           "alms": calls_today(), "max": MAX_PER_DAY})
        wlog(f"resting {rest_seconds}s · the cell is quiet")
        _wait_or_stop(rest_seconds)
    _running["on"] = False
    publish("status", {"running": False, "phase": "stopped"})
    wlog("the monk has set down the practice")
    session_end()


_worker_thread = [None]


def start_worker(api_key, rest_seconds, dry, model=None):
    global API_KEY
    if _running["on"]:
        return False, "the monk is already at practice"
    # let any previous worker fully exit before a fresh start (restart-after-stop)
    t = _worker_thread[0]
    if t and t.is_alive():
        _stop.set()
        t.join(timeout=5)
    if not dry:
        if not api_key or not api_key.strip():
            return False, "no key was given"
        key = api_key.strip()
        ok, info = verify_key(key)  # ask OpenRouter before spending anything
        if not ok:
            return False, info
        API_KEY = key
        _running["key_info"] = info if isinstance(info, dict) else {}
        apply_tier(_running["key_info"])  # sync the cap to the real tier
    _running["dry"] = dry
    _running["rest"] = max(MIN_REST, int(rest_seconds))
    _running["model"] = (model or "auto")
    _stop.clear()
    _running["on"] = True
    th = threading.Thread(target=worker_loop, args=(_running["rest"], dry), daemon=True)
    _worker_thread[0] = th
    th.start()
    return True, "the practice has begun"


def stop_worker():
    _stop.set()
    _running["on"] = False
    return True, "stopping"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # keep the console quiet — the kernel log speaks for itself

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._serve_html()
        elif self.path == "/events":
            self._serve_events()
        elif self.path == "/state":
            self._json(200, state_dict())
        elif self.path == "/models":
            global FREE_MODELS
            if not FREE_MODELS:
                FREE_MODELS = discover_free_models()
            self._json(200, {"models": FREE_MODELS})
        elif self.path == "/notes":
            self._json(200, {"notes": recent_notes(80)})
        elif self.path.startswith("/note?"):
            from urllib.parse import urlparse, parse_qs
            fname = (parse_qs(urlparse(self.path).query).get("file") or [""])[0]
            note = read_note_safe(fname)
            self._json(200 if note else 404, note or {"error": "not found"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            data = {}
        if self.path == "/start":
            dry = _running["dry"] or bool(data.get("dry"))
            ok, msg = start_worker(data.get("key", ""),
                                   data.get("rest", REST_SECONDS) or REST_SECONDS,
                                   dry, data.get("model"))
            self._json(200 if ok else 400, {"ok": ok, "message": msg, **state_dict()})
        elif self.path == "/stop":
            ok, msg = stop_worker()
            self._json(200, {"ok": ok, "message": msg})
        elif self.path == "/reset_alms":
            reset_alms()
            self._json(200, {"ok": True, "alms": 0, "max": MAX_PER_DAY})
        elif self.path == "/offering":
            q = (data.get("question") or "").strip()
            if q:
                add_offering(q)
            self._json(200, {"ok": bool(q)})
        else:
            self._json(404, {"error": "not found"})

    def _serve_html(self):
        try:
            body = HTML_PATH.read_bytes()
        except Exception:
            body = b"<h1>monk-ui.html must sit in the same folder as monk.py</h1>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _serve_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        q = queue.Queue()
        with _sub_lock:
            _subscribers.append(q)
        try:
            self.wfile.write(f"event: state\ndata: {json.dumps(state_dict())}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                except queue.Empty:
                    msg = ": keepalive\n\n"
                self.wfile.write(msg.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _sub_lock:
                if q in _subscribers:
                    _subscribers.remove(q)


def serve(dry=False):
    _running["dry"] = dry
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("\n  ◯  M.O.N.K. — the monastery is open")
    print(f"     open in your browser:  http://localhost:{PORT}")
    print(f"     mode:   {'dry-run — no alms spent (a rehearsal)' if dry else 'live — paste your key in the page to begin'}")
    print(f"     safety: at most {MAX_PER_DAY} calls/day · ≥{MIN_REQUEST_GAP:.0f}s apart · ≥{MIN_REST}s between sittings")
    print("     press Ctrl+C here to close the monastery\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  closing the monastery …")
        stop_worker()
        session_end()
        httpd.shutdown()


def main():
    global FREE_MODELS
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # older consoles — diacritics may render oddly but won't crash output

    if "--serve" in sys.argv:
        serve(dry="--dry-run" in sys.argv)
        return

    dry = "--dry-run" in sys.argv
    once = "--once" in sys.argv
    live = bool(API_KEY) and not dry
    if live:
        ok, info = verify_key(API_KEY)
        if ok:
            apply_tier(info if isinstance(info, dict) else {})
        FREE_MODELS = discover_free_models()
    banner(live)
    spath = session_start("dry-run" if dry else "live", REST_SECONDS, len(FREE_MODELS))
    if spath:
        log(f"session log → {spath.name}")

    fails = 0
    try:
        while True:
            try:
                one_cycle(dry_run=dry)
                fails = 0
            except Fasting:
                log(f"the day's alms are spent ({calls_today()}/{MAX_PER_DAY}). fasting until tomorrow.")
                if once:
                    break
                time.sleep(_seconds_until_utc_midnight())
                continue
            except AlmsEmpty:
                log("the bowl came back empty (429). the monk waits a minute.")
                fails += 1
                if once and fails >= 3:
                    log("the alms would not come. resting for today.")
                    break
                time.sleep(60)
                continue
            except Disturbance as e:
                log(f"a disturbance: {e}")
                log("  (if this says 'data policy', enable logging at openrouter.ai/settings/privacy)")
                fails += 1
                if once and fails >= 3:
                    log("could not complete a sitting after 3 tries. stopping.")
                    break
                time.sleep(min(REST_SECONDS, 10))
                continue
            except Exception as e:
                log(f"a disturbance: {e.__class__.__name__}: {e}")
                fails += 1
                if once and fails >= 3:
                    break
                time.sleep(min(REST_SECONDS, 10))
                continue

            if once:
                log("one sitting complete.")
                break
            log(f"resting {REST_SECONDS}s …")
            time.sleep(REST_SECONDS)
    except KeyboardInterrupt:
        log("the practice was set down.")
    finally:
        session_end()


if __name__ == "__main__":
    main()
