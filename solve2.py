#!/usr/bin/env python3
"""
Piscator probe: start from a mapping that ALMOST works and find what is missing.

1. Fill in the CONFIG block from the best result line of the earlier script.
2. python3 probe.py
3. Everything is also saved to probe_report.txt.

Part A shows which source code produces the '%' (37) outputs.
Part B keeps +1 / -1 / output fixed and tries many meanings for the other
symbols (including the one currently treated as "square"), then ranks them.
"""
import itertools
import re
import time
from collections import Counter

# ------------------------------------------------------------- CONFIG ------
FILENAME = "codex"
INC = "d"            # symbol used as +1 in the best result
DEC = "s"            # symbol used as -1
SQ = "i"             # symbol used as square
OUT = "r"            # symbol used as output
RESET = "exact"      # 'exact', 'range' or 'none' as printed for the best result
DIRECTION = "forward"   # or 'reversed'
BAD = 37             # the value that keeps showing up wrongly ('%')
# ---------------------------------------------------------------------------

_report = []


def say(*parts):
    line = " ".join(str(p) for p in parts)
    print(line)
    _report.append(line)


def rle(seg):
    """Run-length form: 'dddddiis' -> 'd5 i2 s'."""
    return " ".join(m.group(1) + (str(len(m.group(0))) if len(m.group(0)) > 1 else "")
                    for m in re.finditer(r"(.)\1*", seg)) or "(empty)"


def show(v):
    return chr(v) if 32 <= v < 127 else "[%d]" % v


# ------------------------------------------------------------ interpreter --
# op = (kind, arg)
OPS = {"nop": ("nop", 0), "sq": ("sq", 0), "reset": ("set", 0),
       "dbl": ("mul", 2), "half": ("half", 0), "neg": ("neg", 0),
       "store": ("store", 0), "load": ("load", 0), "swap": ("swap", 0),
       "left": ("move", -1), "right": ("move", 1),
       "out_too": ("out", 0), "undo_out": ("back", 0)}
for k in (2, 3, 4, 5, 6, 8, 10, 16, 32, 64):
    OPS["add%d" % k] = ("add", k)
    OPS["sub%d" % k] = ("add", -k)
    OPS["next_x%d" % k] = ("pre", k)
for k in (32, 48, 64, 65, 96, 97, 100):
    OPS["set%d" % k] = ("set", k)

LIMIT = 10 ** 7


def run(code, table, reset):
    a, b, mult, ptr = 0, 0, 1, 0
    tape = {}
    out = []
    for c in code:
        op = table.get(c)
        if op is None:
            continue
        kind, arg = op
        if kind == "nop":
            continue
        if kind == "add":
            a += arg * mult
            mult = 1
        elif kind == "out":
            out.append(a)
            continue
        elif kind == "sq":
            a *= a
        elif kind == "set":
            a = arg
        elif kind == "mul":
            a *= arg
        elif kind == "half":
            a //= 2
        elif kind == "neg":
            a = -a
        elif kind == "pre":
            mult = arg
            continue
        elif kind == "store":
            b = a
            continue
        elif kind == "load":
            a = b
        elif kind == "swap":
            a, b = b, a
        elif kind == "move":
            tape[ptr] = a
            ptr += arg
            a = tape.get(ptr, 0)
            continue
        elif kind == "back":
            if out:
                out.pop()
            continue
        if reset == "exact":
            if a == -1 or a == 256:
                a = 0
        elif reset == "range":
            if a < 0 or a > 255:
                a = 0
        if a > LIMIT or a < -LIMIT:
            return None
    return out


WORDS = """et in est non ad ut cum sed qui quae quod nomen bestia belua piscis
vexillum signum littera litteris minusculis sine spatiis inter hoc haec sunt
monstrum mare maris draco the and flag name beast fish with lowercase is of
that was his he on to for""".split()
GOOD = set(range(65, 91)) | set(range(97, 123)) | {32, 44, 46, 95, 123, 125}


def score(vals):
    if not vals or len(vals) < 8:
        return 0.0
    n = float(len(vals))
    good = sum(v in GOOD for v in vals) / n
    top_share = Counter(vals).most_common(1)[0][1] / n
    text = "".join(chr(v) if 32 <= v < 127 else " " for v in vals).lower()
    text = " " + "".join(c if c.isalpha() else " " for c in text) + " "
    hits = sum(text.count(" " + w + " ") for w in WORDS)
    penalty = max(0.0, top_share - 0.25)        # one value dominating is bad
    return good + min(1.0, hits / max(1.0, n / 25.0)) - penalty


# ------------------------------------------------------------------ main ---
def main():
    raw = open(FILENAME, "r", errors="replace").read()
    code = raw if DIRECTION == "forward" else raw[::-1]
    symbols = [s for s, _ in Counter(c for c in raw if not c.isspace()).most_common()]
    base = {INC: ("add", 1), DEC: ("add", -1), SQ: ("sq", 0), OUT: ("out", 0)}
    unused = [s for s in symbols if s not in base]

    say("=" * 72)
    say("PART A: where do the %r outputs come from?" % chr(BAD))
    say("=" * 72)
    say("mapping: +1=%r -1=%r sq=%r out=%r reset=%s %s; ignored symbols: %s"
        % (INC, DEC, SQ, OUT, RESET, DIRECTION, unused))
    vals = run(code, base, RESET)
    if vals is None:
        say("this mapping blows up; check the CONFIG block")
        vals = []
    segs = code.split(OUT)[:len(vals)]
    n_bad = sum(v == BAD for v in vals)
    say("outputs: %d   equal to %d: %d (%.0f%%)"
        % (len(vals), BAD, n_bad, 100.0 * n_bad / max(1, len(vals))))
    say("most common output values:",
        " ".join("%s x%d" % (show(v), c) for v, c in Counter(vals).most_common(12)))
    say("full text:", "".join(show(v) for v in vals))

    say("\nfirst 45 outputs with the source that produced each one:")
    for i, (v, seg) in enumerate(list(zip(vals, segs))[:45]):
        say("  %3d  %4d %-5s %s" % (i, v, show(v), rle(seg)))

    say("\nsymbol counts per segment, averaged (bad = produced %d):" % BAD)
    for label, pick in (("bad ", [s for v, s in zip(vals, segs) if v == BAD]),
                        ("good", [s for v, s in zip(vals, segs) if v != BAD])):
        if pick:
            say("  %s (%4d segs): " % (label, len(pick)) + "  ".join(
                "%r=%.2f" % (x, sum(s.count(x) for s in pick) / float(len(pick)))
                for x in symbols if x != OUT))
    bad_forms = Counter(rle(s) for v, s in zip(vals, segs) if v == BAD)
    say("\nmost common source forms that give %d:" % BAD)
    for form, c in bad_forms.most_common(8):
        say("  x%-4d %s" % (c, form[:110]))
    gaps = [i for i, v in enumerate(vals) if v == BAD]
    say("positions of first bad outputs:", gaps[:40])

    say("\n" + "=" * 72)
    say("PART B: trying other meanings for %s" % ([SQ] + unused))
    say("=" * 72)
    free = [SQ] + unused
    names = list(OPS)
    results = {}
    start = time.time()

    def attempt(assign):
        table = {INC: ("add", 1), DEC: ("add", -1), OUT: ("out", 0)}
        desc = {}
        for s in free:
            name = assign.get(s, "sq" if s == SQ else "nop")
            table[s] = OPS[name]
            desc[s] = name
        for reset in sorted({RESET, "none"}):
            v = run(code, table, reset)
            if v:
                key = tuple(v)
                sc = score(v)
                if key not in results or results[key][0] < sc:
                    results[key] = (sc, dict(desc), reset)

    for s in free:                                  # change one symbol
        for name in names:
            attempt({s: name})
    for s1, s2 in itertools.combinations(free, 2):  # change two symbols
        for n1 in names:
            for n2 in names:
                attempt({s1: n1, s2: n2})
    say("tried in %.0fs; %d distinct outputs" % (time.time() - start, len(results)))

    ranked = sorted(results.items(), key=lambda kv: -kv[1][0])[:12]
    for rank, (v, (sc, desc, reset)) in enumerate(ranked, 1):
        say("-" * 72)
        say("#%d score %.2f reset=%s  " % (rank, sc, reset)
            + "  ".join("%r=%s" % (s, desc[s]) for s in free)
            + "   (%d outputs, %d are %r)" % (len(v), sum(x == BAD for x in v), chr(BAD)))
        say("   " + "".join(show(x) for x in v))

    with open("probe_report.txt", "w") as fh:
        fh.write("\n".join(_report) + "\n")
    print("\nreport saved to probe_report.txt")


if __name__ == "__main__":
    main()
