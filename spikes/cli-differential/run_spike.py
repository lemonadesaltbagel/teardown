"""End-to-end spike: discover -> generate -> execute (x2 for noise) -> diff -> cluster -> claims.

usage: .venv/bin/python run_spike.py [discover|probe|run|bench|analyze|all]
Artifacts land in out/.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from teardown_cli import analyze as A
from teardown_cli.discover import help_model, letter_scan, merge_models, minimal_invocation, reconcile
from teardown_cli.impls import IMPLS
from teardown_cli.probes import HINTS, generate
from teardown_cli.runner import Probe, load_jsonl, run_batch, run_probes, save_jsonl

CMDS = ["cut", "seq", "sort", "head"]
REF = "gnu"
CANDS = ["uutils", "busybox", "uutils022", "gnu910"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def p(*a):
    print(*a, flush=True)


def discover():
    os.makedirs(f"{OUT}/models", exist_ok=True)
    t0 = time.perf_counter()
    for cmd in CMDS:
        models, scans = {}, {}
        for k, impl in IMPLS.items():
            m = help_model(impl, cmd)
            os.makedirs(f"{OUT}/evidence/help", exist_ok=True)
            open(f"{OUT}/evidence/help/{k}.{cmd}.txt", "w").write(m.pop("_help_text"))
            base = minimal_invocation(impl, cmd, m)
            scans[k] = {"minimal_invocation": base,
                        "letters": letter_scan(impl, cmd, base or [], HINTS[cmd]["takes_files"]),
                        }
            scans[k]["reconcile"] = reconcile(m, scans[k]["letters"])
            models[k] = m
        merged = merge_models({k: models[k] for k in (REF, "uutils", "busybox")})
        # feedback from behavior: an option parsed out of help prose that NO implementation
        # actually accepts (e.g. '-M' from cut's "LIST syntax" paragraph) is a phantom
        for o in merged.values():
            if o["short"] and all(o["short"] in scans[k]["reconcile"]["documented_but_unknown"] for k in o["impls"]):
                o["phantom"] = True
        json.dump({"per_impl": models, "behavior_scan": scans, "merged": merged},
                  open(f"{OUT}/models/{cmd}.json", "w"), indent=1, ensure_ascii=False)
        p(cmd, {k: len(m["options"]) for k, m in models.items()},
          {k: s["reconcile"]["undocumented_but_accepted"] for k, s in scans.items()})
    p(f"discovery: {time.perf_counter() - t0:.1f}s")


def probe():
    os.makedirs(f"{OUT}/probes", exist_ok=True)
    for cmd in CMDS:
        merged = json.load(open(f"{OUT}/models/{cmd}.json"))["merged"]
        ps = generate(cmd, merged)
        save_jsonl(f"{OUT}/probes/{cmd}.jsonl", [x.to_json() for x in ps])
        p(cmd, len(ps), dict(Counter(t for x in ps for t in x.tags if t.startswith("s:"))))


def all_probes() -> list[Probe]:
    return [Probe.from_json(d) for cmd in CMDS for d in load_jsonl(f"{OUT}/probes/{cmd}.jsonl")]


def run():
    """Each impl twice: pass A in generation order, pass B shuffled (order-dependence = reset leak)."""
    os.makedirs(f"{OUT}/results", exist_ok=True)
    probes = all_probes()
    shuffled = probes[:]
    random.Random(1).shuffle(shuffled)
    jobs = [(k, "A", probes) for k in IMPLS] + [(k, "B", shuffled) for k in IMPLS]

    def job(j):
        k, pas, ps = j
        t0 = time.perf_counter()
        obs, timings = run_probes(IMPLS[k], ps, batch_size=300)
        save_jsonl(f"{OUT}/results/{k}.{pas}.jsonl", obs)
        return {"impl": k, "pass": pas, "n": len(ps), "wall_s": round(time.perf_counter() - t0, 2),
                "batches": timings}

    t0 = time.perf_counter()
    with ThreadPoolExecutor(4) as ex:
        stats = list(ex.map(job, jobs))
    total = time.perf_counter() - t0
    json.dump({"jobs": stats, "total_wall_s": total, "parallelism": 4}, open(f"{OUT}/run_stats.json", "w"), indent=1)
    for s in stats:
        p(s["impl"], s["pass"], s["n"], f"{s['wall_s']}s", f"{1000 * s['wall_s'] / s['n']:.1f} ms/probe")
    p(f"total {total:.1f}s for {sum(s['n'] for s in stats)} executions")


def bench():
    """Container-per-probe vs container-per-batch, and reset fidelity between the two."""
    probes = all_probes()
    sample = random.Random(7).sample(probes, 40)
    res = {}
    for k in ("gnu", "busybox"):
        t0 = time.perf_counter()
        single = {}
        for pr in sample:
            o, _ = run_batch(IMPLS[k], [pr])
            single[pr.id] = o[0]
        t_single = time.perf_counter() - t0
        t0 = time.perf_counter()
        batch = {o["probe"]: o for o in run_batch(IMPLS[k], sample)[0]}
        t_batch = time.perf_counter() - t0
        same = sum(single[i] == batch[i] for i in single)
        res[k] = {"n": len(sample), "per_probe_container_ms": round(1000 * t_single / len(sample), 1),
                  "batched_ms": round(1000 * t_batch / len(sample), 2), "identical_obs": same}
        p(k, res[k])
    # raw docker overhead (no-op container)
    t0 = time.perf_counter()
    for _ in range(10):
        os.system("docker run --rm --network none busybox:latest true")
    res["noop_container_ms"] = round(100 * (time.perf_counter() - t0), 1)
    p("noop container", res["noop_container_ms"], "ms")
    json.dump(res, open(f"{OUT}/bench.json", "w"), indent=1)


def _help_lines(impl: str, cmd: str) -> frozenset:
    path = f"{OUT}/evidence/help/{impl}.{cmd}.txt"
    return frozenset(l.strip() for l in open(path).read().splitlines() if len(l.strip()) > 8)


def analyze():
    probes = {d["id"]: d for cmd in CMDS for d in load_jsonl(f"{OUT}/probes/{cmd}.jsonl")}
    cmd_of = {pid: d["cmd"] for pid, d in probes.items()}
    helps = {(k, c): _help_lines(k, c) for k in IMPLS for c in CMDS}
    runs = {}
    for k in IMPLS:
        for pas in "AB":
            runs[(k, pas)] = {o["probe"]: A.abstract(o, cmd_of[o["probe"]], probes[o["probe"]]["argv"],
                                                     helps[(k, cmd_of[o["probe"]])])
                              for o in load_jsonl(f"{OUT}/results/{k}.{pas}.jsonl")}
    # 1. noise calibration (Diffy): same impl, two runs, different order and batch boundaries
    noise = {k: A.noise_mask(runs[(k, "A")], runs[(k, "B")]) for k in IMPLS}
    nondet = set().union(*noise.values())
    report = {"noise": {k: {"n_nondeterministic": len(v), "fields": dict(Counter(f for fs in v.values() for f in fs)),
                            "probes": {pid: {"fields": fs, "argv": probes[pid]["argv"]} for pid, fs in v.items()}}
                        for k, v in noise.items()},
              "excluded_nondeterministic": sorted(nondet)}
    ref = runs[(REF, "A")]
    comparable = [pid for pid in probes if pid not in nondet]
    # 2. agreement per level
    levels = {}
    for cmd in CMDS + ["ALL"]:
        ids = [pid for pid in comparable if cmd == "ALL" or cmd_of[pid] == cmd]
        levels[cmd] = {"n": len(ids)}
        for c in CANDS:
            cand = runs[(c, "A")]
            levels[cmd][c] = {lv: round(100 * sum(A.key(ref[i], lv) == A.key(cand[i], lv) for i in ids) / len(ids), 1)
                              for lv in A.LEVELS}
    report["identical_pct"] = levels
    # 3. diff kinds -> clusters (per candidate) -> claims (merged across candidates by condition)
    merged: dict[tuple, dict] = {}
    kind_counts = {}
    for c in CANDS:
        cand = runs[(c, "A")]
        kinds = defaultdict(lambda: defaultdict(set))
        for pid in comparable:
            dk = A.diff_kind(ref[pid], cand[pid])
            if dk:
                kinds[cmd_of[pid]][dk].add(pid)
        kind_counts[c] = {cmd: {dk: len(g) for dk, g in bk.items()} for cmd, bk in kinds.items()}
        for cmd, by_kind in kinds.items():
            universe = {pid: probes[pid]["tags"] + A.ref_tags(ref[pid]) for pid in comparable if cmd_of[pid] == cmd}
            for dk, group in by_kind.items():
                for cl in A.mine_clusters(group, universe, ref, dk):
                    m = merged.setdefault((cmd, dk, tuple(cl["condition"])), {"cl": cl, "cands": {}})
                    m["cands"][c] = (cl, cand)
    n_before_fold = len(merged)
    merged = A.merge_value_classes(merged)
    claims = [A.make_claim(cmd, dk, m["cl"], m["cands"], probes) for (cmd, dk, _), m in merged.items()]
    claims.sort(key=lambda x: (-x["_size"], x["claim_id"]))
    report["diff_kinds"] = kind_counts
    report["clusters_per_candidate"] = {
        c: {"total": sum(1 for x in claims if c in x["differential"]["falsified_by"]),
            "non_singleton": sum(1 for x in claims if c in x["differential"]["falsified_by"]
                                 and not x["condition"]["all_of_tags"][0].startswith("probe:")),
            "probes_diverging": sum(sum(v.values()) for v in kind_counts[c].values())}
        for c in CANDS}
    report["claims_total"] = len(claims)
    report["clusters_before_value_class_folding"] = n_before_fold
    json.dump(report, open(f"{OUT}/analysis.json", "w"), indent=1, ensure_ascii=False)
    json.dump(claims, open(f"{OUT}/claims.json", "w"), indent=1, ensure_ascii=False)
    p(json.dumps({k: report[k] for k in ("identical_pct", "clusters_per_candidate", "claims_total")}, indent=1))
    p("nondeterministic:", {k: v["n_nondeterministic"] for k, v in report["noise"].items()})


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in [("discover", discover), ("probe", probe), ("run", run), ("bench", bench), ("analyze", analyze)]:
        if step in (name, "all"):
            p(f"== {name}")
            fn()
