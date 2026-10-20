"""Black-box interface discovery.

Two sources, kept separate so they can be compared:
  1. `--help` text  -> option model (STRUCTURE only: names, aliases, arity, metavar->type,
     operand forms). Descriptions are dropped; only a hash is kept so changes are detectable.
  2. behavior       -> letter scan: is `-X` accepted at all? does it consume the next argv?
The two disagreeing is itself a finding (undocumented options, help that lies about arity).
"""
from __future__ import annotations

import hashlib
import re
import string

from .impls import Impl
from .runner import Probe, run_batch

# ----------------------------------------------------------------------------- help parsing

_ALIAS = re.compile(
    r"""^(?P<name>--?[A-Za-z0-9][\w-]*)          # -x / --long
        (?:
            (?P<opt>\[=?<?(?P<m1>[^\]>]+)>?(?:\.\.\.)?\])   # [=ARG] / [=<ARG>...]  optional
          | =(?P<m2>\S+)                                   # =ARG                   required
          | \ <(?P<m3>[^>]+)>(?:\.\.\.)?                   # ' <ARG>'               required (clap)
          | \ (?P<m4>(?!-)\S+)                             # ' ARG'                 required (busybox)
        )?$""",
    re.X,
)


_TYPE_RULES = [  # (predicate on UPPERCASED metavar, type) -- first match wins
    (lambda m: "LIST" in m, "list"),
    (lambda m: "FORMAT" in m, "format"),
    (lambda m: "KEY" in m or m.startswith("START") or m.startswith("N[,"), "keydef"),
    (lambda m: m in ("WHEN", "WORD", "SORT", "CHECK", "TRIMMED"), "enum"),
    (lambda m: m in ("SIZE",) or re.fullmatch(r"(\[-\])?-?(N|NUM)(\[[A-Z]+\])?", m) is not None, "size"),
    (lambda m: any(k in m for k in ("NUM", "MERGE", "THREADS")) or m == "N", "int"),
    (lambda m: m in ("F", "FILE", "DIR", "PROG", "FILENAME", "NUL_FILE"), "path"),
]


def _metavar_type(mv: str | None, name: str) -> str:
    """Map a metavar to a value-class family. Heuristic -- the weakest link of discovery:
    clap metavars are often just the lowercased option name (<key>, <sort>), busybox uses
    mini-grammars (N[bkm], N[,M]), GNU uses KEYDEF/LIST that only the prose explains."""
    if mv is None:
        return "none"
    m = mv.upper().strip("<>=")
    for pred, t in _TYPE_RULES:
        if pred(m):
            return t
    return "string"


def _spec_part(line: str) -> str | None:
    """Return the leading option-spec part of a help line, or None if it is not an option line."""
    s = line.rstrip("\n")
    stripped = s.lstrip(" \t")
    if not stripped.startswith("-") or len(s) - len(stripped) > 12:
        return None
    # spec ends at a TAB or at 2+ spaces (GNU/clap), or end of line (clap puts desc on next line)
    m = re.match(r"^(.*?)(?:\t|  +|$)", stripped)
    spec = m.group(1).strip()
    if len(spec.split(" ")) > 2 and not re.search(r"<|, ", spec):
        # busybox irregular: "-k N[,M] Sort by Nth field" -> keep option + first metavar-ish token
        toks = spec.split(" ")
        spec = toks[0] + (" " + toks[1] if len(toks) > 1 and re.match(r"^[-\[]?[A-Z]", toks[1]) else "")
    return spec


def parse_help(text: str, cmd: str) -> dict:
    lines = text.splitlines()
    usage, options, prev_usage = [], {}, False
    for ln in lines:
        u = re.match(r"^\s*(?:Usage:|or:)?\s*" + re.escape(cmd) + r"\b\s*(.*)$", ln)
        if u and (ln.lstrip().startswith(("Usage:", "or:")) or (prev_usage and ln.startswith(" "))):
            usage.append(u.group(1).strip())
            prev_usage = True
            continue
        prev_usage = False
        spec = _spec_part(ln)
        if not spec:
            continue
        aliases = []
        for part in re.split(r",\s+", spec):
            m = _ALIAS.match(part.strip())
            if not m:
                continue
            mv = m.group("m1") or m.group("m2") or m.group("m3") or m.group("m4")
            arity = "optional" if m.group("opt") else ("required" if mv else "none")
            if m.group("m2") and m.group("m2").islower():
                # GNU "--check=quiet": a pinned literal value, not a metavar
                aliases.append({"name": m.group("name"), "arity": "none", "metavar": None,
                                "pinned": m.group("m2")})
                continue
            aliases.append({"name": m.group("name"), "arity": arity, "metavar": mv})
        if not aliases:
            continue
        # canonical key: first long name, else the short name
        key = aliases[0]["name"]
        pinned = [f'{a["name"]}={a["pinned"]}' for a in aliases if a.get("pinned")]
        arity = next((a["arity"] for a in aliases if a["arity"] != "none"), "none")
        mv = next((a["metavar"] for a in aliases if a["metavar"]), None)
        entry = options.setdefault(key, {"names": [], "arity": arity, "metavar": mv,
                                          "type": _metavar_type(mv, key), "forms": 0})
        entry["forms"] += 1   # e.g. busybox lists "-n N" and "-n -N" separately
        entry.setdefault("pinned_values", []).extend(pinned)
        for a in aliases:
            # "--check=quiet" style: an alias that pins an enum value
            if a["name"] not in entry["names"]:
                entry["names"].append(a["name"])
    operands = [_operands(u) for u in usage]
    return {
        "cmd": cmd,
        "usage_forms": operands,
        "options": options,
        "help_sha": hashlib.sha256(text.encode()).hexdigest()[:16],  # prose is NOT stored
    }


def _strip_option_groups(u: str) -> str:
    """Remove {...} groups and [-...] groups (with nesting) from a synopsis."""
    out, i = [], 0
    while i < len(u):
        if u[i] == "{" or (u[i] == "[" and u[i + 1:i + 2] == "-"):
            depth, j, brace = 0, i, u[i] == "{"
            while j < len(u):
                if not brace and depth >= 1 and u[j] == " " and u[j + 1:j + 2] == "[":
                    break  # unbalanced synopsis (busybox sort -k): a new group ends this one
                depth += u[j] in "[{"
                depth -= u[j] in "]}"
                j += 1
                if depth == 0:
                    break
            out.append(" ")
            i = j
        else:
            out.append(u[i])
            i += 1
    return "".join(out)


def _operands(usage: str) -> list[dict]:
    """'[OPTION]... FIRST INCREMENT LAST' -> [{name, optional, repeat}] (options stripped)."""
    out = []
    # drop option groups like [-nrug], {-b|c LIST | ...}, [-o FILE]
    u = _strip_option_groups(usage)
    for tok in re.findall(r"\[?[A-Z][A-Z_]*\]?(?:\.\.\.)?", u):
        name = tok.strip("[].")
        if name in ("OPTION", "OPTIONS"):
            continue
        out.append({"name": name, "optional": tok.startswith("["), "repeat": tok.endswith("...")})
    return out


def help_model(impl: Impl, cmd: str) -> dict:
    obs, _ = run_batch(impl, [Probe("help", cmd, ["--help"])])
    o = obs[0]
    text = o["stdout"] or o["stderr"]          # busybox prints help on stderr
    m = parse_help(text, cmd)
    m.update({"impl": impl.key, "help_rc": o["rc"], "help_stream": "stdout" if o["stdout"] else "stderr",
              "_help_text": text})  # evidence only: caller moves it to the dirty-side evidence store
    return m


# ----------------------------------------------------------------------------- behavior scan

LETTERS = string.ascii_letters + string.digits
SENTINEL = "zz_sentinel"


def minimal_invocation(impl: Impl, cmd: str, help_m: dict, stdin: bytes = b"a\n") -> list[str] | None:
    """Find the smallest argv that succeeds on a trivial input, so option probes are not
    masked by 'you must specify X' errors (cut needs a list; seq needs an operand)."""
    cands: list[list[str]] = [[]]
    for o in help_m["options"].values():
        short = next((n for n in o["names"] if re.fullmatch(r"-\w", n)), None)
        if short and o["arity"] == "required":
            cands.append([short, "1"])
    cands += [["1"], ["1", "2"]]
    obs = run_batch(impl, [Probe(f"m{i}", cmd, c, stdin) for i, c in enumerate(cands)])[0]
    for c, o in zip(cands, obs):
        if o["rc"] == 0:
            return c
    return None


def letter_scan(impl: Impl, cmd: str, base: list[str], takes_files: bool = True) -> dict:
    """For every -X (in front of a known-good `base` argv): accepted? consumes next argv?
    Reference 'unknown option' observation = bogus option '-@'; letter X is unknown iff its
    observation equals the reference with '@' replaced by X (exit code and stderr)."""
    probes = [Probe("ref", cmd, ["-@", *base], b"a\n"),
              Probe("ref_stdin", cmd, base, b"a\n"),
              Probe("ref_file", cmd, [*base, SENTINEL], b"a\n", {SENTINEL: b"Q\n"})]
    for ch in LETTERS:
        probes.append(Probe(f"L_{ch}", cmd, [f"-{ch}", *base], b"a\n"))
        if takes_files:
            # SENTINEL exists as a file containing "Q"; stdin holds "a". Whether the output is
            # derived from Q or from a tells us whether -X consumed the next argv.
            probes.append(Probe(f"A_{ch}", cmd, [*base, f"-{ch}", SENTINEL], b"a\n", {SENTINEL: b"Q\n"}))
    obs = {o["probe"]: o for o in run_batch(impl, probes)[0]}
    ref = obs["ref"]
    res = {}
    for ch in LETTERS:
        o = obs[f"L_{ch}"]
        if o["rc"] == ref["rc"] and o["stderr"] == ref["stderr"].replace("@", ch):
            continue
        entry = {"accepted": o["rc"] == 0}
        if takes_files:
            a = obs[f"A_{ch}"]
            entry["consumes_next"] = (False if a["stdout"] == obs["ref_file"]["stdout"] else
                                      True if a["stdout"] == obs["ref_stdin"]["stdout"] else
                                      None)  # None = undetermined (option changed the output)
        res[f"-{ch}"] = entry
    return res


def reconcile(help_m: dict, scan: dict) -> dict:
    """Compare help-derived structure with behavior-derived structure."""
    documented = {n for o in help_m["options"].values() for n in o["names"] if re.fullmatch(r"-\w", n)}
    arity = {n: o["arity"] for o in help_m["options"].values() for n in o["names"]}
    found = set(scan)
    mism = []
    for n, e in scan.items():
        if n in arity and e.get("consumes_next") is not None:
            help_says = arity[n] == "required"
            if help_says != e["consumes_next"]:
                mism.append({"opt": n, "help_arity": arity[n], "behavior_consumes_next": e["consumes_next"]})
    return {
        "undocumented_but_accepted": sorted(found - documented),
        "documented_but_unknown": sorted(documented - found),
        "arity_mismatch": mism,
    }


def merge_models(models: dict[str, dict]) -> dict:
    """Union option model across implementations, keyed by short name when present."""
    merged: dict[str, dict] = {}
    for impl, m in models.items():
        for key, o in m["options"].items():
            short = next((n for n in o["names"] if re.fullmatch(r"-\w", n)), None)
            longs = [n for n in o["names"] if n.startswith("--")]
            k = short or key
            e = merged.setdefault(k, {"short": short, "long": [], "arity": {}, "type": {}, "impls": []})
            for l in longs:
                if l not in e["long"]:
                    e["long"].append(l)
            e["arity"][impl] = o["arity"]
            e["type"][impl] = o["type"]
            e["impls"].append(impl)
    return merged
