#!/usr/bin/env python3
"""
Piscator solver: brute-forces interpretations of a Deadfish-like program.

Usage:
    python3 solve.py FILE            # diagnostics + standard search
    python3 solve.py FILE --deep     # also try extended operations (slower)
    python3 solve.py FILE --top 30   # show more candidates

Everything printed is also written to solve_report.txt, so you can push the
report back out of the environment if nothing decodes cleanly.
No third-party packages needed.
"""
import itertools
import sys
import time
from collections import Counter

# ---------------------------------------------------------------- output ---
_report = []


def say(*parts):
    line = " ".join(str(p) for p in parts)
    print(line)
    _report.append(line)


# ------------------------------------------------------------ operations ---
NOP, ADD, SQ, OUT, RST, DBL, HLF, NEG, LEFT, RIGHT, PRE = range(11)

BASIC_OPS = {
    "inc": (ADD, 1), "dec": (ADD, -1), "sq": (SQ, 0), "out": (OUT, 0),
    "reset": (RST, 0), "dbl": (DBL, 0), "left": (LEFT, 0), "right": (RIGHT, 0),
}
EXTRA_OPS = {"half": (HLF, 0), "neg": (NEG, 0)}
for _k in (2, 3, 4, 5, 8, 10, 16, 32):
    EXTRA_OPS["add%d" % _k] = (ADD, _k)
    EXTRA_OPS["sub%d" % _k] = (ADD, -_k)
for _k in (2, 3, 4, 5, 8, 10, 16):
    EXTRA_OPS["next_x%d" % _k] = (PRE, _k)   # multiplies the next inc/dec
ALL_OPS = dict(BASIC_OPS, **EXTRA_OPS)
ALL_OPS["nop"] = (NOP, 0)

WRAPS = ("none", "deadfish", "mod256")
BIG = 10 ** 7


def printable(v):
    return 32 <= v <= 126 or v == 10


def run(prog, ops, wrap, screen):
    """prog: list of symbol indices. ops: list of (code, arg) per symbol.
    Returns list of output values, or None if rejected while screening."""
    a = 0
    mult = 1
    tape = {}
    ptr = 0
    out = []
    good = 0
    since_out = 0
    for sym in prog:
        code, arg = ops[sym]
        if code == NOP:
            continue
        if code == ADD:
            a += arg * mult
            mult = 1
        elif code == OUT:
            out.append(a)
            if screen:
                since_out = 0
                if printable(a):
                    good += 1
                n = len(out)
                if n == 20 and good < 17:
                    return None
                if n == 80 and good < 72:
                    return None
            continue
        elif code == SQ:
            a *= a
        elif code == RST:
            a = 0
        elif code == DBL:
            a *= 2
        elif code == HLF:
            a //= 2
        elif code == NEG:
            a = -a
        elif code == PRE:
            mult = arg
            continue
        elif code == LEFT or code == RIGHT:
            tape[ptr] = a
            ptr += 1 if code == RIGHT else -1
            a = tape.get(ptr, 0)
            continue
        if wrap == "deadfish":
            if a == -1 or a == 256:
                a = 0
        elif wrap == "mod256":
            a &= 255
        if screen:
            if a > BIG or a < -BIG:
                return None
            since_out += 1
            if since_out > 6000:
                return None
    return out


# --------------------------------------------------------------- scoring ---
WORDS = """et in est non ad ut cum sed qui quae quod nomen bestia belua piscis
vexillum signum littera litteris minusculis sine spatiis inter hoc haec sunt
monstrum mare maris draco the and flag name beast fish with lowercase is of
submit wrap format underscore""".split()


def to_text(vals):
    return "".join(chr(v) if printable(v) else "\u00b7" for v in vals)


def word_hits(text):
    low = " " + "".join(c if c.isalpha() else " " for c in text.lower()) + " "
    return sum(low.count(" " + w + " ") for w in WORDS)


def score(vals):
    if len(vals) < 8:
        return 0.0
    n = float(len(vals))
    p = sum(1 for v in vals if printable(v)) / n
    if p < 0.9:
        return p
    text = to_text(vals)
    letters = sum(1 for c in text if c.isalpha() or c == " ") / n
    variety = min(1.0, len(set(vals)) / 12.0)
    words = min(1.0, word_hits(text) / max(1.0, n / 25.0))
    return p + letters * variety + words


# ----------------------------------------------------------- diagnostics ---
def diagnostics(raw, syms, counts):
    say("=" * 72)
    say("DIAGNOSTICS")
    say("=" * 72)
    say("bytes:", len(raw), " lines:", raw.count("\n") + 1,
        " whitespace chars:", sum(1 for c in raw if c.isspace()))
    say("symbols by frequency:")
    for s, c in counts.most_common():
        say("   %r  %7d  %5.1f%%" % (s, c, 100.0 * c / sum(counts.values())))
    lines = [l for l in raw.split("\n") if l]
    if len(lines) > 1:
        lens = Counter(len(l) for l in lines)
        say("non-empty lines:", len(lines), " line lengths (len: how many):",
            dict(lens.most_common(8)))
    say("first 300 chars:")
    say("   " + raw[:300].replace("\n", "\\n"))
    say("last 120 chars:")
    say("   " + raw[-120:].replace("\n", "\\n"))

    body = "".join(c for c in raw if not c.isspace())
    say("\nbigram table (row = symbol, column = what follows it):")
    big = Counter(zip(body, body[1:]))
    say("        " + "".join("%8r" % s for s in syms))
    for x in syms:
        say("   %4r " % x + "".join("%8d" % big[(x, y)] for y in syms))

    total = len(body)
    rare = [s for s in syms if counts[s] < 0.1 * total]
    for s in rare:
        segs = body.split(s)
        say("\nsplitting on %r gives %d segments; first 14 as counts of %s:"
            % (s, len(segs), " ".join(x for x in syms if x != s)))
        for seg in segs[:14]:
            c = Counter(seg)
            say("   " + " ".join("%4d" % c[x] for x in syms if x != s)
                + "   " + seg[:50])
    return rare


# ---------------------------------------------------------------- search ---
def assignments_basic(syms, rare):
    """Every way to give each symbol a basic op or nop; inc and out required,
    no op used twice except nop, out must be on a rare symbol."""
    names = list(BASIC_OPS)
    n = len(syms)
    others = [x for x in names if x not in ("inc", "out")]
    for out_sym in rare:
        for inc_sym in syms:
            if inc_sym == out_sym:
                continue
            rest = [s for s in syms if s not in (out_sym, inc_sym)]
            for k in range(len(rest) + 1):
                for active in itertools.combinations(rest, k):
                    for perm in itertools.permutations(others, k):
                        m = {s: "nop" for s in syms}
                        m[out_sym] = "out"
                        m[inc_sym] = "inc"
                        for s, op in zip(active, perm):
                            m[s] = op
                        yield m


def assignments_deep(syms, rare):
    """inc/dec/out fixed on three symbols; up to two of the remaining symbols
    get any extended operation."""
    pool = [x for x in ALL_OPS if x not in ("inc", "dec", "out", "nop")]
    for out_sym in rare:
        for inc_sym, dec_sym in itertools.permutations(
                [s for s in syms if s != out_sym], 2):
            rest = [s for s in syms if s not in (out_sym, inc_sym, dec_sym)]
            for k in (1, 2):
                for active in itertools.combinations(rest, k):
                    for combo in itertools.product(pool, repeat=k):
                        m = {s: "nop" for s in syms}
                        m[out_sym], m[inc_sym], m[dec_sym] = "out", "inc", "dec"
                        for s, op in zip(active, combo):
                            m[s] = op
                        yield m


def search(label, gen, syms, progs, results):
    say("\nsearching:", label)
    start = time.time()
    tried = 0
    for m in gen:
        ops = [ALL_OPS[m[s]] for s in syms]
        for direction, prog in progs:
            for wrap in WRAPS:
                tried += 1
                if run(prog, ops, wrap, True) is None:
                    continue
                vals = run(prog, ops, wrap, False)
                sc = score(vals)
                if sc >= 0.9:
                    key = tuple(vals)
                    if key not in results or results[key][0] < sc:
                        results[key] = (sc, dict(m), wrap, direction)
        if tried % 60000 < 6:
            sys.stderr.write("  ... %d tried, %d candidates, %.0fs\n"
                             % (tried, len(results), time.time() - start))
    say("  tried %d interpretations in %.0fs, %d candidates so far"
        % (tried, time.time() - start, len(results)))


# ------------------------------------------------------------- untangle ----
def caesar(text, k):
    res = []
    for c in text:
        if "a" <= c <= "z":
            res.append(chr((ord(c) - 97 + k) % 26 + 97))
        elif "A" <= c <= "Z":
            res.append(chr((ord(c) - 65 + k) % 26 + 65))
        else:
            res.append(c)
    return "".join(res)


def atbash(text):
    res = []
    for c in text:
        if "a" <= c <= "z":
            res.append(chr(219 - ord(c)))
        elif "A" <= c <= "Z":
            res.append(chr(155 - ord(c)))
        else:
            res.append(c)
    return "".join(res)


def with_separators(prog, syms, m, wrap):
    """Re-run, marking where each do-nothing symbol sits in the output."""
    marks = {}
    idle = [s for s in syms if m[s] == "nop"]
    for s in idle:
        out_idx = [i for i, x in enumerate(syms) if m[x] == "out"][0]
        # tag outputs: run manually so we know which symbol produced each value
        a_text = []
        vals_iter = iter(run(prog, [ALL_OPS[m[x]] for x in syms], wrap, False))
        sidx = syms.index(s)
        for sym in prog:
            if sym == out_idx:
                v = next(vals_iter)
                a_text.append(chr(v) if printable(v) else "\u00b7")
            elif sym == sidx:
                a_text.append("|")
        marks[s] = "".join(a_text)
    return marks


def show(rank, vals, info, syms, progs):
    sc, m, wrap, direction = info
    text = to_text(vals)
    say("-" * 72)
    say("#%d  score %.2f   wrap=%s   source=%s" % (rank, sc, wrap, direction))
    say("    mapping: " + "  ".join("%r=%s" % (s, m[s]) for s in syms))
    say("    values : " + " ".join(str(v) for v in vals[:40]))
    say("    TEXT   : " + text)
    if rank > 5:
        return
    say("    reversed: " + text[::-1])
    base = word_hits(text)
    best = max(range(1, 26), key=lambda k: word_hits(caesar(text, k)))
    if word_hits(caesar(text, best)) > base:
        say("    caesar +%d: %s" % (best, caesar(text, best)))
    if word_hits(atbash(text)) > base:
        say("    atbash: " + atbash(text))
    prog = dict(progs)[direction]
    for s, marked in with_separators(prog, syms, m, wrap).items():
        if 0 < marked.count("|") < 0.8 * len(vals):
            say("    with %r shown as | : %s" % (s, marked))


# ------------------------------------------------------------------ main ---
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return
    deep = "--deep" in sys.argv
    top = 15
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])

    raw = open(args[0], "r", errors="replace").read()
    body = "".join(c for c in raw if not c.isspace())
    counts = Counter(body)
    syms = [s for s, _ in counts.most_common()]
    rare = diagnostics(raw, syms, counts)

    if len(syms) > 8:
        say("\nToo many distinct symbols (%d) for the brute force; "
            "send back the diagnostics above." % len(syms))
    elif not rare:
        say("\nNo rare symbol to act as output; send back the diagnostics.")
    else:
        index = {s: i for i, s in enumerate(syms)}
        fwd = [index[c] for c in body]
        progs = [("forward", fwd), ("reversed", fwd[::-1])]
        results = {}
        search("basic operations", assignments_basic(syms, rare),
               syms, progs, results)
        best = max([r[0] for r in results.values()] or [0])
        if deep or best < 2.0:
            if not deep:
                say("  no convincing result yet, so running the deep search")
            search("extended operations", assignments_deep(syms, rare),
                   syms, progs, results)

        say("\n" + "=" * 72)
        say("CANDIDATES (best first)")
        say("=" * 72)
        ranked = sorted(results.items(), key=lambda kv: -kv[1][0])[:top]
        if not ranked:
            say("Nothing decoded to printable text. Send back the diagnostics.")
        for rank, (vals, info) in enumerate(ranked, 1):
            show(rank, list(vals), info, syms, progs)

    with open("solve_report.txt", "w") as fh:
        fh.write("\n".join(_report) + "\n")
    print("\nreport saved to solve_report.txt")


if __name__ == "__main__":
    main()
