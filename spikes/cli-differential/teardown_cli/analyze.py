"""Normalization, Diffy-style noise calibration, differential comparison, claim mining.

Observation abstraction levels (strict -> lenient):
  L0 raw          rc, stdout bytes, stderr bytes, fs diff
  L1 norm-text    as L0 but stderr with program-name prefix / usage dumps / 'Try --help' removed
  L2 behavior     rc exact, stdout bytes, stderr PRESENCE, errno classes in stderr, fs diff
  L2b +locus      L2 + which of OUR argv tokens the diagnostic blames
  L3 coarse       success-vs-failure, stdout bytes, fs diff
L2 is the primary definition of "behavioral difference": exact diagnostic prose is expression,
"refuses with a diagnostic and exit status N" is behavior.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections import Counter, defaultdict

from .impls import IMPLS

ERRNO = {  # libc strerror strings: system-defined, shared by all implementations
    "ENOENT": "No such file or directory", "EISDIR": "Is a directory", "EACCES": "Permission denied",
    "EROFS": "Read-only file system", "ENOTDIR": "Not a directory", "EILSEQ": "Invalid or incomplete multibyte",
}


# ----------------------------------------------------------------------------- normalization

def norm_stderr(text: str, impl: str, cmd: str, help_lines: frozenset = frozenset()) -> str:
    lines, dumped = [], False
    for ln in text.splitlines():
        if help_lines and ln.strip() in help_lines:   # busybox dumps its --help on usage errors
            dumped = True
            continue
        if re.match(r"^(Try '.*--help'|For more information, try|Usage: |BusyBox v\d)", ln):
            continue
        for pfx in IMPLS[impl].progname_prefixes:
            ln = re.sub("^" + pfx.format(cmd=re.escape(cmd)), "", ln)
        ln = re.sub(r"^error: ", "", ln)
        lines.append(ln.strip())
    return "\n".join([l for l in lines if l] + (["<usage>"] if dumped else []))


def blamed_args(stderr: str, argv: list[str]) -> list[str]:
    """argv tokens (that WE supplied) echoed quoted in the diagnostic: the 'error locus'.
    Captures which input was rejected without keeping the diagnostic's prose."""
    return sorted({a for a in argv if len(a) >= 2 and (f"'{a}'" in stderr or f"‘{a}’" in stderr)})


def rc_class(rc: int | None) -> str:
    if rc is None:
        return "none"
    if rc == 0:
        return "ok"
    if rc >= 128:
        return f"sig{rc - 128}"
    return "fail"


def abstract(o: dict, cmd: str, argv: list[str] = (), help_lines: frozenset = frozenset()) -> dict:
    se = o["stderr"]
    return {
        "rc": o["rc"], "rc_class": rc_class(o["rc"]),
        "stdout_sha": hashlib.sha256(o["stdout"].encode("latin-1")).hexdigest()[:12],
        "stdout_empty": o["stdout"] == "",
        "stderr_raw": se, "stderr_norm": norm_stderr(se, o["impl"], cmd, help_lines),
        "stderr_present": se != "",
        "errno": sorted(k for k, v in ERRNO.items() if v in se),
        "blamed": blamed_args(se, list(argv)),
        "fs": json.dumps(o["fs"], sort_keys=True),
    }


LEVELS = {
    "L0_raw": ("rc", "stdout_sha", "stderr_raw", "fs"),
    "L1_normtext": ("rc", "stdout_sha", "stderr_norm", "fs"),
    "L2_behavior": ("rc", "stdout_sha", "stderr_present", "errno", "fs"),
    "L2b_locus": ("rc", "stdout_sha", "stderr_present", "errno", "fs", "blamed"),
    "L3_coarse": ("rc_class", "stdout_sha", "fs"),
}


def key(a: dict, level: str) -> tuple:
    return tuple(json.dumps(a[f]) for f in LEVELS[level])


def noise_mask(run1: dict[str, dict], run2: dict[str, dict]) -> dict[str, list[str]]:
    """probe -> fields that differ between two runs of the SAME implementation."""
    out = {}
    for pid, a in run1.items():
        b = run2.get(pid)
        if b is None:
            continue
        diff = [f for f in ("rc", "stdout_sha", "stderr_raw", "fs") if a[f] != b[f]]
        if diff:
            out[pid] = diff
    return out


# ----------------------------------------------------------------------------- diff kinds

def diff_kind(r: dict, x: dict) -> str | None:
    """Behavior-level (L2) difference category between reference r and candidate x."""
    if key(r, "L2_behavior") == key(x, "L2_behavior"):
        return None
    rok, xok = r["rc"] == 0, x["rc"] == 0
    if (r["rc_class"].startswith("sig") or x["rc_class"].startswith("sig")) and r["rc_class"] != x["rc_class"]:
        return "terminated_by_signal_differs"
    if not rok and xok:
        return "ref_refuses_cand_accepts"
    if rok and not xok:
        return "ref_accepts_cand_refuses"
    if r["rc"] != x["rc"]:
        return "both_refuse_exit_status_differs"
    if r["fs"] != x["fs"]:
        return "side_effect_differs"
    if r["stdout_sha"] != x["stdout_sha"]:
        return "stdout_differs" + ("" if rok else "_on_failure")
    if r["stderr_present"] != x["stderr_present"]:
        return "diagnostic_presence_differs"
    if r["errno"] != x["errno"]:
        return "error_condition_differs"
    return "other"


def ref_tags(r: dict) -> list[str]:
    """Observation-derived condition tags of the REFERENCE run, so claims can be conditioned on
    outcomes ("whenever the reference refuses ...") and not only on input factors."""
    t = [f"ref.rc={r['rc']}"]
    if r["errno"]:
        t.append("ref.errno=" + "+".join(r["errno"]))
    return t


def obs_class(a: dict, kind: str) -> dict:
    """The part of an observation that a claim of this diff-kind talks about."""
    d = {"exit": a["rc"], "class": {"ok": "accepts", "fail": "refuses"}.get(a["rc_class"], a["rc_class"])}
    if kind in ("stdout_differs", "stdout_differs_on_failure", "side_effect_differs"):
        return d
    d.update({"stdout": "empty" if a["stdout_empty"] else "non-empty", "diagnostic": a["stderr_present"]})
    if a["errno"]:
        d["errno"] = a["errno"]
    return d


# ----------------------------------------------------------------------------- clustering

def _cands(tags: list[str]) -> list[tuple[str, ...]]:
    t = [x for x in tags if not x.startswith(("s:", "style:"))]
    return [(a,) for a in t] + [tuple(sorted(c)) for c in itertools.combinations(t, 2)]


def mine_clusters(group: set[str], universe: dict[str, list[str]], ref: dict, kind: str,
                  min_div: float = 0.5, min_ref_cons: float = 0.9) -> list[dict]:
    """Greedy cover of `group` (probes where a candidate diverges in one way) by conditions =
    conjunctions of <=2 tags (input factors and reference-outcome tags). Acceptable iff
      * the REFERENCE behaves uniformly under it (consistency >= min_ref_cons) -> a claim exists
      * the candidate diverges on a good share of it (>= min_div)             -> it is a difference
    """
    support = defaultdict(set)
    for pid, tags in universe.items():
        for c in _cands(tags):
            support[c].add(pid)
    cls_of = {pid: json.dumps(obs_class(ref[pid], kind), sort_keys=True) for pid in universe}
    remaining, clusters = set(group), []
    while remaining:
        best, best_score, best_top = None, 0.0, None
        for c, pids in support.items():
            hit = len(pids & remaining)
            if not hit:
                continue
            div = len(pids & group) / len(pids)
            if div < min_div:
                continue
            top, n_top = Counter(cls_of[p] for p in pids).most_common(1)[0]
            cons = n_top / len(pids)
            if cons < min_ref_cons:
                continue
            score = hit * div * cons - 0.02 * len(c) - 0.001 * len(pids)
            if score > best_score:
                best, best_score, best_top = c, score, top
        if best is None:  # unexplained remainder: singleton clusters
            for pid in sorted(remaining):
                clusters.append({"condition": ["probe:" + pid], "members": [pid], "support": [pid],
                                 "ref_class": json.loads(cls_of[pid]), "diverging": 1, "ref_confirming": 1})
            break
        pids = support[best]
        clusters.append({"condition": list(best), "members": sorted(pids & remaining), "support": sorted(pids),
                         "ref_class": json.loads(best_top), "diverging": len(pids & group),
                         "ref_confirming": sum(cls_of[p] == best_top for p in pids)})
        remaining -= pids
    return clusters


# ----------------------------------------------------------------------------- claims

def humanize(tag: str) -> str:
    from .probes import VALUES  # only for rendering an example value we generated
    k, _, v = tag.partition(":")
    if tag.startswith("ref."):
        return f"the reference outcome is {tag[4:]}"
    if k == "opt":
        return f"option {v} is given"
    if k == "val" and "=" in v:
        o, cls = v.split("=", 1)
        return f"option {o} has a value of class '{cls}'"
    if k == "val" and " in " in v:
        typ, cls = v.split(" in ", 1)
        return f"a {typ} value of class {cls}"
    if k == "val" and "." in v:
        typ, cls = v.split(".", 1)
        ex = VALUES.get(typ, VALUES["number"]).get(cls)
        return f"a {typ} value of class '{cls}'" + (f" (e.g. {ex!r})" if ex is not None else "")
    return {"in": f"input is '{v}'", "mode": f"input is delivered via {v}", "syn": f"argv has shape '{v}'",
            "form": f"operand form is {v}", "env": f"environment has {v}", "probe": f"exactly probe {v}"}.get(k, tag)


def make_claim(cmd: str, kind: str, cl: dict, cands: dict[str, tuple[dict, dict]], probes: dict) -> dict:
    """cl: the reference-side cluster; cands: impl -> (that impl's cluster with same condition, its observations)."""
    cond, r = cl["condition"], cl["ref_class"]
    cond_txt = " and ".join(humanize(c) for c in cond)
    if kind.startswith("stdout_differs"):
        what = f"{'succeed' if r['class'] == 'accepts' else 'fail'} (exit {r['exit']}) and write exactly the reference output"
    elif r["class"] == "refuses":
        what = f"refuse: exit {r['exit']}, a diagnostic on stderr, stdout {r.get('stdout')}"
    elif r["class"] == "accepts":
        what = f"accept: exit 0, stdout {r.get('stdout', 'as reference')}"
    else:
        what = f"terminate by {r['class']}"
    if kind == "side_effect_differs":
        what += ", leaving exactly the reference filesystem changes"
    ckind = {"ref_refuses_cand_accepts": "refusal", "ref_accepts_cand_refuses": "input-domain",
             "both_refuse_exit_status_differs": "refusal", "side_effect_differs": "side-effect",
             "terminated_by_signal_differs": "refusal"}.get(kind, "output-invariant")
    falsified = {}
    for impl, (c2, obs) in cands.items():
        x = Counter(json.dumps(obs_class(obs[p], kind), sort_keys=True) for p in c2["members"])
        falsified[impl] = {"observed": json.loads(x.most_common(1)[0][0]),
                           "diverging": f"{c2['diverging']}/{len(c2['support'])}"}
    body = {"cmd": cmd, "condition": cond, "kind": kind}
    return {
        "claim_id": "clm_" + hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10],
        "feature": f"{cmd}." + next((c.split(":", 1)[1].split("=")[0] for c in cond if c.startswith("opt:")),
                                    cond[0].split(":", 1)[-1] if cond else "?"),
        "kind": ckind,
        "statement": f"When {cond_txt}, `{cmd}` shall {what}.",
        "condition": {"cmd": cmd, "all_of_tags": cond},
        "expected_observation": r,
        "confidence": {"probes": len(cl["support"]), "confirming": cl["ref_confirming"],
                       "contradicting": len(cl["support"]) - cl["ref_confirming"], "nondeterminism": "none"},
        "status": "corroborated" if cl["ref_confirming"] == len(cl["support"]) else "contested",
        "origin": "observed",
        "differential": {"diff_kind": kind, "falsified_by": falsified},
        "evidence": cl["support"][:15],
        "example_argv": [probes[p]["argv"] for p in cl["members"][:3]],
        "_size": max(len(c2["members"]) for c2, _ in cands.values()),
    }


def merge_value_classes(merged: dict[tuple, dict]) -> dict[tuple, dict]:
    """Fold clusters that differ only in the value class of one typed value into one
    decision-table style condition:  (opt:-F, val:list.one) + (opt:-F, val:list.range) + ...
    -> (opt:-F, val:list in {one, range, ...}).  Only folds when the reference class and the
    set of diverging candidates are the same."""
    buckets = defaultdict(list)
    for k, m in merged.items():
        cmd, dk, cond = k
        vals = [c for c in cond if c.startswith("val:") and "." in c and "=" not in c]
        if len(vals) != 1:
            continue
        rest = tuple(c for c in cond if c != vals[0])
        typ = vals[0][4:].split(".", 1)[0]
        bk = (cmd, dk, rest, typ, tuple(sorted(m["cands"])), json.dumps(m["cl"]["ref_class"], sort_keys=True))
        buckets[bk].append(k)
    out = {k: m for k, m in merged.items()}
    for (cmd, dk, rest, typ, impls, _), keys in buckets.items():
        if len(keys) < 2:
            continue
        classes = sorted(c[4:].split(".", 1)[1] for k in keys for c in k[2] if c.startswith(f"val:{typ}."))
        new_cond = (*rest, f"val:{typ} in {{{','.join(classes)}}}")
        def union(cls):
            return {"condition": list(new_cond),
                    "members": sorted({p for c in cls for p in c["members"]}),
                    "support": sorted({p for c in cls for p in c["support"]}),
                    "ref_class": cls[0]["ref_class"],
                    "diverging": sum(c["diverging"] for c in cls),
                    "ref_confirming": sum(c["ref_confirming"] for c in cls)}
        new = {"cl": union([out[k]["cl"] for k in keys]), "cands": {}}
        for impl in impls:
            new["cands"][impl] = (union([out[k]["cands"][impl][0] for k in keys]), out[keys[0]]["cands"][impl][1])
        for k in keys:
            del out[k]
        out[(cmd, dk, new_cond)] = new
    return out
