"""Automatic probe generation from a discovered option model.

Inputs:  merged option model (discover.merge_models) + a small per-command HINTS dict.
Output:  list[Probe], each tagged with its generating factors so differences can later be
         clustered back onto factors ("opt:-f", "val:list.zero", "in:crlf", "mode:file").

Strategies
  S1 value sweep      one valued option x every boundary class of its type
  S2 pairwise         greedy 2-way covering array over options (+input class, +delivery mode)
  S3 input sweep      canonical argv x every input class x delivery mode
  S4 syntax           argv-parsing edge cases (abbrev longs, '--', permutation, missing arg ...)
  S5 env              locale variants on unicode inputs

The VALUE CLASSES and INPUTS tables are type-indexed and command-independent: this is the
part an LLM would propose in the real system ("equivalence classes per input").
"""
from __future__ import annotations

import hashlib
import itertools
import random

from .runner import Probe

# ----------------------------------------------------------------------------- value classes
VALUES: dict[str, dict[str, str]] = {
    "list": {
        "one": "2", "multi": "1,3", "range": "1-2", "open_end": "2-", "open_start": "-2",
        "zero": "0", "zero_range": "0-2", "reversed": "3-1", "empty": "", "dash": "-",
        "double_comma": "1,,2", "overlap": "1-3,2-4", "dup": "2,2", "unsorted": "3,1",
        "space_sep": "1 2", "nonnum": "a", "huge": "18446744073709551616", "big32": "4294967296",
        "beyond": "99", "plus": "+1", "lead_zero": "02", "lead_ws": " 1", "trail_comma": "1,",
        "unicode_digit": "\u0661", "double_dash": "1--2", "open_both": "-",
    },
    "int": {
        "zero": "0", "one": "1", "neg": "-1", "huge": "99999999999999999999", "nonnum": "abc",
        "empty": "", "float": "1.5", "hex": "0x10", "plus": "+1", "lead_ws": " 1",
    },
    "size": {
        "zero": "0", "one": "1", "three": "3", "neg": "-1", "neg_zero": "-0", "neg_big": "-99",
        "huge": "99999999999999999999", "i64max1": "9223372036854775808", "k": "1k", "K": "1K",
        "kB": "1kB", "b": "1b", "KiB": "1KiB", "M": "1M", "Q": "1Q", "bad_suffix": "1x",
        "empty": "", "nonnum": "abc", "float": "1.5", "plus": "+2", "lead_ws": " 2", "hex": "0x10",
        "suffix_only": "k",
    },
    "string": {
        "colon": ":", "empty": "", "multi": "ab", "tab": "\t", "utf8": "\u00e9", "backslash": "\\",
        "space": " ", "esc_t": "\\t", "newline": "\n", "percent": "%",
    },
    "format": {
        "g": "%g", "f": "%f", "prec": "%.2f", "e": "%e", "s": "%s", "d": "%d", "x": "%x",
        "empty": "", "nodir": "abc", "two": "%g%g", "pct": "%%", "width": "%5g", "left": "%-5g|",
        "flags": "%0#10.3f", "L": "%Lg", "a": "%a", "quote": "%'g", "wrapped": "x%gy", "trail_pct": "%g%",
    },
    "keydef": {
        "one": "1", "two": "2", "one_one": "1,1", "num": "2n", "num_end": "2,2n", "char": "1.2",
        "char_range": "1.2,1.3", "zero": "0", "end_zero": "1,0", "char_zero": "1.0", "nonnum": "a",
        "neg": "-1", "rev": "2r", "blank": "1b", "reversed": "3,1", "empty": "", "three": "1,2,3",
        "dot": "1.", "num_rev": "2nr", "beyond": "99", "bad_opt": "1Z",
    },
    "enum": {"empty": "", "bogus": "xyz"},
    "path": {
        "new": "out.txt", "inplace": "in.txt", "missing": "missing.txt", "dir": ".", "empty": "",
        "nodir": "sub/out.txt", "readonly": "/etc/passwd",
    },
    "number": {  # positional numeric operands (seq)
        "one": "1", "zero": "0", "neg": "-1", "ten": "10", "half": "1.5", "tenth": "0.1",
        "exp": "1e2", "hex": "0x10", "inf": "inf", "nan": "nan", "neg_zero": "-0", "empty": "",
        "nonnum": "abc", "huge": "1e20", "bigint": "99999999999999999999", "trail_zero": "1.000",
        "lead_ws": " 1", "plus": "+1", "comma": "1,5", "hexfloat": "0x1p3", "underscore": "1_0",
        "unicode_digit": "\u0661", "neg_tenth": "-0.1", "big_prec": "1.0000000000000000001",
    },
}

INPUTS: dict[str, bytes] = {
    "tsv": b"a\tb\tc\n1\t2\t3\n",
    "colon": b"a:b:c\n1:2:3\n",
    "nodelim": b"abc\nxyz\n",
    "mixed": b"a:b\nnodelim\n:x:\n",
    "empty": b"",
    "no_eol": b"a:b\n1:2",
    "crlf": b"a:b\r\n1:2\r\n",
    "utf8": "\u00e9:\u00fc:\u6f22\n\u00f1\u00f6:\u5b57:x\n".encode(),
    "blank_lines": b"\n\n:\n",
    "nul": b"a:b\0c:d\n",
    "invalid_utf8": b"\xff\xfe:a\n\xc3:b\n",
    "long_line": b"x" * 70000 + b":y\n",
    "numbers": b"10\n9\n-1\n1e3\n0x10\nabc\n 5\n05\n1.5\n-0\n\n+3\n",
    "human": b"1K\n2M\n512\n1k\n1G\nJan\nfeb\nDEC\n",
    "dups": b"b\na\nb\nA\na\n",
    "ws_fields": b"1 2 3\n  4  5\n\t6\t7\n",
    "many_lines": b"".join(b"%d\n" % i for i in range(20)),
}

# Per-command hints: things a human/LLM supplies once. Everything else is derived.
HINTS: dict[str, dict] = {
    "cut": {"base": ["-f", "2"], "default_input": "tsv", "sweep_inputs": ["tsv", "mixed", "utf8"], "takes_files": True,
            "inputs": ["tsv", "colon", "nodelim", "mixed", "empty", "no_eol", "crlf", "utf8",
                       "blank_lines", "nul", "invalid_utf8", "long_line"],
            "pair_inputs": ["tsv", "colon", "mixed", "utf8", "no_eol"],
            "unicode_argv": [["-c", "1"], ["-c", "2-3"], ["-b", "1"], ["-d", "\u00e9", "-f", "1"]]},
    "sort": {"base": [], "default_input": "numbers", "sweep_inputs": ["numbers", "ws_fields", "human"], "takes_files": True,
             "inputs": ["numbers", "human", "dups", "ws_fields", "colon", "empty", "no_eol", "crlf",
                        "utf8", "blank_lines", "nul", "invalid_utf8", "long_line", "tsv"],
             "pair_inputs": ["numbers", "human", "dups", "ws_fields", "colon"],
             "unicode_argv": [[], ["-f"], ["-d"], ["-i"]]},
    "head": {"base": ["-n", "3"], "default_input": "many_lines", "sweep_inputs": ["many_lines", "no_eol", "nul"], "takes_files": True,
             "inputs": ["many_lines", "empty", "no_eol", "crlf", "utf8", "nul", "long_line", "colon"],
             "pair_inputs": ["many_lines", "no_eol", "nul"],
             "unicode_argv": [["-c", "1"], ["-c", "2"]]},
    "seq": {"base": ["3"], "default_input": None, "sweep_inputs": [None], "takes_files": False,
            "operand_type": "number", "inputs": [], "pair_inputs": [],
            "unicode_argv": [["-s", "\u00e9", "3"], ["-f", "%g\u00e9", "2"]]},
}

# options never probed: prose output (help/version) or needs external programs / random input
SKIP_OPTS = {"--help", "--version", "--compress-program", "--random-source", "--files0-from", "-T", "--parallel"}


def _pid(cmd: str, argv: list[str], stdin: bytes | None, files: dict, env: dict) -> str:
    h = hashlib.sha1(repr((cmd, argv, stdin, sorted(files.items()), sorted(env.items()))).encode())
    return cmd + "_" + h.hexdigest()[:10]


class ProbeSet:
    def __init__(self, cmd: str):
        self.cmd, self.probes, self._seen = cmd, [], set()

    def add(self, argv, stdin=None, files=None, env=None, tags=()):
        files, env = files or {}, env or {}
        pid = _pid(self.cmd, argv, stdin, files, env)
        if pid in self._seen:
            return
        self._seen.add(pid)
        self.probes.append(Probe(pid, self.cmd, list(argv), stdin, files, env, list(tags)))


def _deliver(argv: list[str], data: bytes | None, mode: str):
    """Return (argv, stdin, files) for delivering `data` by `mode`."""
    if data is None:
        return argv, None, {}
    return {
        "stdin": (argv, data, {}),
        "file": (argv + ["in.txt"], None, {"in.txt": data}),
        "dash": (argv + ["-"], data, {}),
        "two_files": (argv + ["in.txt", "in2.txt"], None, {"in.txt": data, "in2.txt": b"Z:Y\tX\n"}),
        "missing": (argv + ["missing.txt"], data, {}),
        "dir": (argv + ["."], data, {}),
        "file_and_missing": (argv + ["in.txt", "missing.txt"], None, {"in.txt": data}),
    }[mode]


def _option_params(model: dict, cmd: str) -> list[dict]:
    """Probe-able options: short name preferred (all impls understand it), with type."""
    out = []
    for k, o in model.items():
        names = [o["short"]] if o["short"] else o["long"][:1]
        name = names[0]
        if name in SKIP_OPTS or (o["long"] and o["long"][0] in SKIP_OPTS) or o.get("phantom"):
            continue
        # choose the type/arity GNU reports; else first impl that has it
        ref = "gnu" if "gnu" in o["arity"] else o["impls"][0]
        out.append({"name": name, "long": o["long"], "arity": o["arity"][ref], "type": o["type"][ref],
                    "impls": o["impls"]})
    return out


def pairwise(params: dict[str, list], seed: int = 0) -> list[dict]:
    """Greedy 2-way covering array (AETG-style). params: name -> list of values."""
    rng = random.Random(seed)
    names = list(params)
    uncovered = {(a, i, b, j) for a, b in itertools.combinations(names, 2)
                 for i in range(len(params[a])) for j in range(len(params[b]))}
    rows = []
    while uncovered:
        best, best_cov = None, -1
        for _ in range(30):
            a, i, b, j = rng.choice(sorted(uncovered))
            row = {a: i, b: j}
            order = [n for n in names if n not in row]
            rng.shuffle(order)
            for n in order:  # greedily pick the value covering most uncovered pairs
                def gain(v):
                    return sum(((n, v, m, row[m]) in uncovered) or ((m, row[m], n, v) in uncovered) for m in row)
                row[n] = max(range(len(params[n])), key=lambda v: (gain(v), rng.random()))
            cov = sum((x, row[x], y, row[y]) in uncovered for x, y in itertools.combinations(names, 2))
            if cov > best_cov:
                best, best_cov = row, cov
        for x, y in itertools.combinations(names, 2):
            uncovered.discard((x, best[x], y, best[y]))
        rows.append({n: params[n][v] for n, v in best.items()})
    return rows


def generate(cmd: str, model: dict) -> list[Probe]:
    h = HINTS[cmd]
    ps = ProbeSet(cmd)
    base = h["base"]
    din = INPUTS[h["default_input"]] if h["default_input"] else None
    params = _option_params(model, cmd)
    base_opts = {base[0]} if base and base[0].startswith("-") else set()

    def with_base(argv, opt_name):
        if cmd == "seq":
            return argv + base
        if opt_name in base_opts or (cmd == "cut" and opt_name in ("-b", "-c", "-f", "-F")):
            return argv
        return argv + base

    # S1 value sweep (over a few inputs) ----------------------------------------------
    for iname in h["sweep_inputs"]:
        data = INPUTS[iname] if iname else None
        itag = [f"in:{iname}"] if iname else []
        for p in params:
            if p["arity"] == "none":
                a, i, f = _deliver(with_base([p["name"]], p["name"]), data, "stdin")
                ps.add(a, i, f, tags=["s:sweep", f"opt:{p['name']}", "val:flag", *itag])
                continue
            for vname, v in VALUES.get(p["type"], VALUES["string"]).items():
                styles = ("sep", "attached") if vname in ("empty", "zero", "neg", "open_start") else ("sep",)
                for style in styles:
                    argv = [p["name"], v] if style == "sep" else [p["name"] + v]
                    a, i, f = _deliver(with_base(argv, p["name"]), data, "file" if p["type"] == "path" else "stdin")
                    ps.add(a, i, f, tags=["s:sweep", f"opt:{p['name']}", f"val:{p['type']}.{vname}",
                                          f"style:{style}", *itag])

    # S2 pairwise ----------------------------------------------------------------------
    pp: dict[str, list] = {}
    for p in params:
        if p["type"] == "path" or p["name"] in ("-T", "-S", "-o"):
            continue
        if p["arity"] == "none":
            pp[p["name"]] = [None, "on"]
        else:
            vals = list(VALUES.get(p["type"], VALUES["string"]).items())
            pp[p["name"]] = vals
    rows = []
    for k, picks in enumerate(((0, 2, 4, 5), (1, 3, 6, 7))):   # two covering arrays, different classes
        sub = {n: (v if v[0] is None else [None] + [v[i] for i in picks if i < len(v)]) for n, v in pp.items()}
        if h["pair_inputs"]:
            sub["@input"] = h["pair_inputs"]
            sub["@mode"] = ["stdin", "file"]
        rows += pairwise(sub, seed=k)
    for row in rows:
        argv, tags = [], ["s:pairwise"]
        for n, v in row.items():
            if n.startswith("@") or v is None:
                continue
            if v == "on":
                argv.append(n)
                tags.append(f"opt:{n}")
            else:
                argv += [n, v[1]]
                tags += [f"opt:{n}", f"val:{n}={v[0]}"]
        if cmd == "seq":
            argv += base
        elif cmd == "cut" and not any(x in argv for x in ("-b", "-c", "-f", "-F")):
            argv += base
        data = INPUTS[row["@input"]] if "@input" in row else None
        a, i, f = _deliver(argv, data, row.get("@mode", "stdin"))
        ps.add(a, i, f, tags=tags + ([f"in:{row['@input']}", f"mode:{row['@mode']}"] if data is not None else []))

    # S3 input sweep -------------------------------------------------------------------
    if h["takes_files"]:
        for iname in h["inputs"]:
            for mode in ("stdin", "file"):
                a, i, f = _deliver(list(base), INPUTS[iname], mode)
                ps.add(a, i, f, tags=["s:inputs", f"in:{iname}", f"mode:{mode}"])
        for mode in ("dash", "two_files", "missing", "dir", "file_and_missing"):
            a, i, f = _deliver(list(base), din, mode)
            ps.add(a, i, f, tags=["s:inputs", f"mode:{mode}"])
        ps.add(list(base), None, tags=["s:inputs", "in:devnull", "mode:stdin"])
    else:  # positional numeric operands (seq): sweep each operand form
        nums = VALUES[h.get("operand_type", "number")]
        for vname, v in nums.items():
            ps.add([v], tags=["s:operands", "form:LAST", f"val:LAST.{vname}"])
            ps.add(["1", v], tags=["s:operands", "form:FIRST_LAST", f"val:LAST.{vname}"])
            ps.add([v, "3"], tags=["s:operands", "form:FIRST_LAST", f"val:FIRST.{vname}"])
            ps.add(["1", v, "3"], tags=["s:operands", "form:FIRST_INC_LAST", f"val:INC.{vname}"])
            ps.add(["-w", v, "3"], tags=["s:operands", "opt:-w", "form:FIRST_LAST", f"val:FIRST.{vname}"])
        small = ["1", "0", "-1", "1.5", "0.1", "1e1", "-0", "10"]
        for a, b, c in itertools.product(small, ["1", "-1", "0.5", "0"], small):
            ps.add([a, b, c], tags=["s:operands", "form:FIRST_INC_LAST", "val:combo"])
        for n in ([], ["1"], ["1", "2", "3", "4"]):
            ps.add(n, tags=["s:operands", f"form:arity{len(n)}"])

    # S4 argv-syntax edge cases -----------------------------------------------------------
    first_long = next((p for p in params if p["long"] and p["arity"] == "required"), None)
    flag = next((p for p in params if p["arity"] == "none"), None)
    synt: list[tuple[list[str], str]] = [
        (["--teardown-bogus"] + base, "unknown_long"), (["-@"] + base, "unknown_short"),
        (base + ["--"], "dashdash_end"), (["--"] + base, "dashdash_first"),
        ([p for p in base[:1]], "missing_arg"), (base + base, "repeated"),
    ]
    if first_long:
        ln = first_long["long"][0]
        val = base[1] if len(base) > 1 else "1"
        synt += [([f"{ln}={val}"], "long_eq"), ([ln, val], "long_sep"),
                 ([f"{ln[:5]}={val}"], "long_abbrev"), ([f"{ln}="], "long_eq_empty"),
                 ([ln[:3] + "=" + val], "long_abbrev_ambiguous")]
    if flag and cmd != "seq":
        synt += [(base + ["in.txt", flag["name"]], "opt_after_operand")]
    for argv, kind in synt:
        files = {"in.txt": din} if (din is not None and "in.txt" in argv) else {}
        stdin = din if not files else None
        if cmd == "seq" and kind in ("long_eq", "long_sep", "long_abbrev", "long_eq_empty", "long_abbrev_ambiguous"):
            argv = argv + ["3"]
        ps.add(argv, stdin, files, tags=["s:syntax", f"syn:{kind}"])
        if kind == "opt_after_operand":
            ps.add(argv, stdin, files, env={"POSIXLY_CORRECT": "1"}, tags=["s:syntax", f"syn:{kind}", "env:posix"])
    if cmd == "seq":
        for argv, kind in [(["-1"], "neg_operand_as_opt"), (["--", "-1"], "neg_after_dashdash"),
                           (["-s", ",", "-w", "-f", "%g", "3"], "w_with_f"), (["-s"], "missing_arg")]:
            ps.add(argv, tags=["s:syntax", f"syn:{kind}"])

    # S5 environment: locale on unicode inputs -------------------------------------------
    for argv in h["unicode_argv"]:
        for loc in ("C", "C.UTF-8"):
            data = INPUTS["utf8"] if h["takes_files"] else None
            a, i, f = _deliver(list(argv), data, "stdin")
            ps.add(a, i, f, env={"LC_ALL": loc}, tags=["s:env", f"env:LC_ALL={loc}", "in:utf8"])
    return ps.probes
