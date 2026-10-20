"""CLI probe planning: value classes, input classes, delivery modes, argv-syntax edges, pairwise combinations.

Planning is two-phase, per the CLI spike's lesson that mixing several invalid values in one probe makes blame
ambiguous:

1. ``plan_sweep`` varies one factor at a time (each option across every value class, each input across delivery
   modes, syntax edges, locale). Running it tells which value classes each option *accepts*.
2. ``plan_pairwise`` builds 2-way covering arrays over accepted classes only. Rejected classes stay single-fault.

Every argv element is tagged with the factor that produced it, so results can be folded back into decision tables.
The tables below are type-indexed and command-independent; the observer supplies the per-command
:class:`ProbeHints` (which an LLM proposes in production).
"""

from __future__ import annotations

import itertools
import random

from pydantic import BaseModel, ConfigDict, Field

from teardown.core.ids import content_id
from teardown.drivers.cli.invocation import Invocation

VALUES: dict[str, dict[str, str]] = {
    "list": {
        "one": "2", "multi": "1,3", "range": "1-2", "open_end": "2-", "open_start": "-2",
        "zero": "0", "zero_range": "0-2", "reversed": "3-1", "empty": "", "dash": "-",
        "double_comma": "1,,2", "overlap": "1-3,2-4", "dup": "2,2", "unsorted": "3,1",
        "space_sep": "1 2", "nonnum": "a", "huge": "18446744073709551616", "big32": "4294967296",
        "beyond": "99", "plus": "+1", "lead_zero": "02", "lead_ws": " 1", "trail_comma": "1,",
        "unicode_digit": "\u0661", "double_dash": "1--2",
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
        "flags": "%0#10.3f", "a": "%a", "wrapped": "x%gy", "trail_pct": "%g%",
    },
    "keydef": {
        "one": "1", "two": "2", "one_one": "1,1", "num": "2n", "num_end": "2,2n", "char": "1.2",
        "char_range": "1.2,1.3", "zero": "0", "end_zero": "1,0", "char_zero": "1.0", "nonnum": "a",
        "neg": "-1", "rev": "2r", "blank": "1b", "reversed": "3,1", "empty": "", "three": "1,2,3",
        "dot": "1.", "num_rev": "2nr", "beyond": "99", "bad_opt": "1Z",
    },
    "enum": {"empty": "", "bogus": "xyz"},
    "path": {"new": "out.txt", "inplace": "in.txt", "missing": "missing.txt", "dir": ".", "empty": "",
             "nodir": "sub/out.txt"},
    "number": {
        "one": "1", "zero": "0", "neg": "-1", "ten": "10", "half": "1.5", "tenth": "0.1",
        "exp": "1e2", "hex": "0x10", "inf": "inf", "nan": "nan", "neg_zero": "-0", "empty": "",
        "nonnum": "abc", "huge": "1e20", "bigint": "99999999999999999999", "trail_zero": "1.000",
        "lead_ws": " 1", "plus": "+1", "comma": "1,5", "hexfloat": "0x1p3", "underscore": "1_0",
        "unicode_digit": "\u0661", "neg_tenth": "-0.1",
    },
}

INPUTS: dict[str, str] = {
    "tsv": "a\tb\tc\n1\t2\t3\n",
    "colon": "a:b:c\n1:2:3\n",
    "nodelim": "abc\nxyz\n",
    "mixed": "a:b\nnodelim\n:x:\n",
    "empty": "",
    "no_eol": "a:b\n1:2",
    "crlf": "a:b\r\n1:2\r\n",
    "utf8": "\u00e9:\u00fc:\u6f22\n\u00f1\u00f6:\u5b57:x\n".encode().decode("latin-1"),
    "blank_lines": "\n\n:\n",
    "nul": "a:b\0c:d\n",
    "invalid_utf8": "\xff\xfe:a\n\xc3:b\n",
    "long_line": "x" * 70000 + ":y\n",
    "numbers": "10\n9\n-1\n1e3\n0x10\nabc\n 5\n05\n1.5\n-0\n\n+3\n",
    "dups": "b\na\nb\nA\na\n",
    "ws_fields": "1 2 3\n  4  5\n\t6\t7\n",
    "many_lines": "".join(f"{i}\n" for i in range(20)),
    "json": '{"a":1,"b":[1,2,{"c":null}],"d":"x"}\n',
}

DELIVERY_MODES = ("stdin", "file", "dash", "two_files", "missing", "dir", "file_and_missing")
NEVER_PROBE = {"--help", "--version"}  # prose output: help text is expression, captured once at discovery


class Probe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    invocation: Invocation
    tags: list[str] = Field(default_factory=list)

    @staticmethod
    def make(cmd: str, args: list[str], *, stdin: str | None = None, files: dict[str, str] | None = None,
             env: dict[str, str] | None = None, tags: list[str] | None = None, stdout_mode: str = "pipe",
             stdin_mode: str | None = None, file_modes: dict[str, str] | None = None) -> Probe:
        inv = Invocation(argv=[cmd, *args], stdin=stdin, files=files or {}, env=env or {},
                         stdin_mode=stdin_mode or ("pipe" if stdin is not None else "null"), stdout_mode=stdout_mode,
                         file_modes=file_modes or {})
        return Probe(id=content_id("prb", inv.model_dump(mode="json"))[:24], invocation=inv, tags=list(tags or []))


class ProbeHints(BaseModel):
    """Per-command knowledge the observer supplies once; everything else is derived."""

    model_config = ConfigDict(extra="forbid")

    cmd: str
    base: list[str] = Field(default_factory=list, description="Argv that makes the command do its main job.")
    selector_options: list[str] = Field(default_factory=list,
                                        description="Options that replace `base` (e.g. cut's -b/-c/-f).")
    takes_files: bool = True
    default_input: str | None = "tsv"
    sweep_inputs: list[str | None] = Field(default_factory=lambda: ["tsv"])
    inputs: list[str] = Field(default_factory=lambda: ["tsv", "empty", "no_eol", "crlf", "utf8", "nul"])
    pair_inputs: list[str] = Field(default_factory=lambda: ["tsv"])
    operand_type: str | None = Field(default=None, description="Value type of positional operands, if any.")
    operand_forms: list[list[str]] = Field(
        default_factory=lambda: [["{v}"], ["1", "{v}"], ["{v}", "3"], ["1", "{v}", "3"]],
        description="argv templates for the operand sweep; '{v}' is replaced by each value of `operand_type`.")
    operand_options: list[list[str]] = Field(default_factory=lambda: [[]],
                                             description="Option prefixes the operand sweep is repeated with.")
    stdio_modes: bool = Field(default=True, description="Probe closed/full stdout and closed stdin.")
    file_faults: bool = Field(default=True, description="Probe unreadable input files (alone, and before a readable "
                                                        "one: does the command go on after the error?).")
    extra_argv: dict[str, list[str]] = Field(
        default_factory=dict, description="Observer-designed probes: class name -> argv (run on default_input).")
    mutation_lines: dict[str, str] = Field(
        default_factory=dict, description="Lines to insert into the default input (name -> line), e.g. comment- or "
        "header-like lines, escapes, odd field counts.")
    mutation_argv: list[list[str]] = Field(default_factory=list,
                                           description="argv variants the input mutations run with (default: base)")
    unicode_argv: list[list[str]] = Field(default_factory=list)
    skip_options: list[str] = Field(default_factory=list)
    extra_inputs: dict[str, str] = Field(default_factory=dict, description="Observer-supplied input samples.")
    extra_values: dict[str, dict[str, str]] = Field(default_factory=dict, description="type -> class -> value")
    option_values: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="option name -> class -> value; overrides the type-based classes")

    def input(self, name: str) -> str:
        return self.extra_inputs.get(name, INPUTS.get(name, ""))

    def values(self, type_: str, option: str | None = None) -> dict[str, str]:
        if option and option in self.option_values:
            return dict(self.option_values[option])
        return {**VALUES.get(type_, VALUES["string"]), **self.extra_values.get(type_, {})}


class _ProbeSet:
    def __init__(self, cmd: str):
        self.cmd, self.probes, self._seen = cmd, [], set()

    def add(self, args, stdin=None, files=None, env=None, tags=()):
        probe = Probe.make(self.cmd, list(args), stdin=stdin, files=files, env=env, tags=list(tags))
        if probe.id not in self._seen:
            self._seen.add(probe.id)
            self.probes.append(probe)


def _deliver(args: list[str], data: str | None, mode: str):
    if data is None:
        return args, None, {}
    return {
        "stdin": (args, data, {}),
        "file": (args + ["in.txt"], None, {"in.txt": data}),
        "dash": (args + ["-"], data, {}),
        "two_files": (args + ["in.txt", "in2.txt"], None, {"in.txt": data, "in2.txt": "Z:Y\tX\n"}),
        "missing": (args + ["missing.txt"], data, {}),
        "dir": (args + ["."], data, {}),
        "file_and_missing": (args + ["in.txt", "missing.txt"], None, {"in.txt": data}),
    }[mode]


def probe_options(model: dict, hints: ProbeHints) -> list[dict]:
    """Options worth probing: short name preferred, phantoms and prose-only options skipped."""
    out = []
    skip = NEVER_PROBE | set(hints.skip_options)
    for key, o in model["options"].items():
        names = o["names"]
        short = next((n for n in names if len(n) == 2 and n.startswith("-")), None)
        longs = [n for n in names if n.startswith("--")]
        name = short or (longs[0] if longs else key)
        if o.get("phantom") or name in skip or (longs and longs[0] in skip):
            continue
        out.append({"name": name, "long": longs, "arity": o["arity"], "type": o["type"]})
    return out


def _with_base(args: list[str], opt: str, hints: ProbeHints) -> list[str]:
    if hints.base and (opt == hints.base[0] or opt in hints.selector_options):
        return args
    return args + hints.base


def plan_sweep(model: dict, hints: ProbeHints) -> list[Probe]:
    ps = _ProbeSet(hints.cmd)
    params = probe_options(model, hints)
    din = hints.input(hints.default_input) if hints.default_input else None

    for iname in hints.sweep_inputs:  # S1: one option x every value class
        data = hints.input(iname) if iname else None
        itag = [f"in:{iname}"] if iname else []
        for p in params:
            if p["arity"] == "none":
                a, i, f = _deliver(_with_base([p["name"]], p["name"], hints), data, "stdin")
                ps.add(a, i, f, tags=["s:sweep", f"opt:{p['name']}", "val:flag", *itag])
                continue
            for vname, v in hints.values(p["type"], p["name"]).items():
                styles = ("sep", "attached") if vname in ("empty", "zero", "neg", "open_start") else ("sep",)
                for style in styles:
                    argv = [p["name"], v] if style == "sep" else [p["name"] + v]
                    mode = "file" if p["type"] == "path" else "stdin"
                    a, i, f = _deliver(_with_base(argv, p["name"], hints), data, mode)
                    ps.add(a, i, f, tags=["s:sweep", f"opt:{p['name']}", f"val:{p['type']}.{vname}",
                                          f"style:{style}", *itag])

    if hints.takes_files:  # S3: inputs x delivery modes
        for iname in hints.inputs:
            for mode in ("stdin", "file"):
                a, i, f = _deliver(list(hints.base), hints.input(iname), mode)
                ps.add(a, i, f, tags=["s:inputs", f"in:{iname}", f"mode:{mode}"])
        for mode in DELIVERY_MODES[2:]:
            a, i, f = _deliver(list(hints.base), din, mode)
            ps.add(a, i, f, tags=["s:inputs", f"mode:{mode}"])
        ps.add(list(hints.base), None, tags=["s:inputs", "in:devnull", "mode:stdin"])
    if hints.operand_type:  # positional operands, one form at a time, optionally over inputs
        inputs = hints.sweep_inputs if hints.takes_files or hints.default_input else [None]
        for prefix in hints.operand_options:
            for form_index, form in enumerate(hints.operand_forms):
                position = form.index("{v}") + 1 if "{v}" in form else 0
                for vname, v in hints.values(hints.operand_type).items():
                    argv = [*prefix, *(v if t == "{v}" else t for t in form)]
                    for iname in inputs:
                        data = hints.input(iname) if iname else None
                        tags = ["s:operands", f"form:{form_index}", f"val:op{position}.{vname}",
                                *([f"opts:{' '.join(prefix)}"] if prefix else []), *([f"in:{iname}"] if iname else [])]
                        ps.add(argv, data, tags=tags)
        for n in ([], ["1", "2", "3", "4"]):
            ps.add(n, tags=["s:operands", f"form:arity{len(n)}"])

    # S4: argv-syntax edges
    base = list(hints.base)
    first_long = next((p for p in params if p["long"] and p["arity"] == "required"), None)
    flag = next((p for p in params if p["arity"] == "none"), None)
    syntax: list[tuple[list[str], str]] = [
        (["--teardown-bogus", *base], "unknown_long"), (["-@", *base], "unknown_short"),
        ([*base, "--"], "dashdash_end"), (["--", *base], "dashdash_first"), (base[:1], "missing_arg"),
        ([*base, *base], "repeated"),
    ]
    if first_long:
        ln, val = first_long["long"][0], (base[1] if len(base) > 1 else "1")
        syntax += [([f"{ln}={val}"], "long_eq"), ([ln, val], "long_sep"), ([f"{ln[:5]}={val}"], "long_abbrev"),
                   ([f"{ln}="], "long_eq_empty")]
    if flag and hints.takes_files:
        syntax.append(([*base, "in.txt", flag["name"]], "opt_after_operand"))
    for argv, kind in syntax:
        files = {"in.txt": din} if (din is not None and "in.txt" in argv) else {}
        stdin = din if not files else None
        ps.add(argv, stdin, files, tags=["s:syntax", f"syn:{kind}"])
        if kind == "opt_after_operand":
            ps.add(argv, stdin, files, env={"POSIXLY_CORRECT": "1"}, tags=["s:syntax", f"syn:{kind}", "env:posix"])

    if din:  # S8: input mutations of the default input
        for mname, data in mutations(din, hints.mutation_lines).items():
            for argv in hints.mutation_argv or [list(hints.base)]:
                tags = ["s:mutation", f"mut:{mname}", *([f"argv:{' '.join(argv)}"] if argv != hints.base else [])]
                ps.add(list(argv), data, tags=tags)

    for cname, argv in hints.extra_argv.items():  # S7: observer-designed probes (orderings, combinations, ...)
        files = {"in.txt": din, "in2.txt": din} if din is not None and any(a.startswith("in") for a in argv) else {}
        ps.add(list(argv), None if files else din, files, tags=["s:designed", f"case:{cname}"])

    if hints.stdio_modes:  # S6: stdio edge modes on the main invocation
        for mode, kwargs in (("stdout:closed", {"stdout_mode": "closed"}), ("stdout:full", {"stdout_mode": "full"}),
                             ("stdin:closed", {"stdin_mode": "closed"})):
            probe = Probe.make(hints.cmd, list(hints.base), stdin=din if "stdin_mode" not in kwargs else None,
                               tags=["s:stdio", f"stdio:{mode}"], **kwargs)
            if probe.id not in ps._seen:
                ps._seen.add(probe.id)
                ps.probes.append(probe)

    if hints.file_faults and hints.takes_files and din is not None:  # S6b: permission faults on file operands
        for fault, args, files, modes in (
                ("unreadable", ["in.txt"], {"in.txt": din}, {"in.txt": "000"}),
                ("unreadable_then_readable", ["locked.txt", "in.txt"], {"locked.txt": din, "in.txt": din},
                 {"locked.txt": "000"})):
            probe = Probe.make(hints.cmd, [*hints.base, *args], files=files, file_modes=modes,
                               tags=["s:fault", f"fault:{fault}"])
            if probe.id not in ps._seen:
                ps._seen.add(probe.id)
                ps.probes.append(probe)

    for argv in hints.unicode_argv:  # S5: locale
        for loc in ("C", "C.UTF-8"):
            data = hints.input("utf8") if hints.takes_files else None
            a, i, f = _deliver(list(argv), data, "stdin")
            ps.add(a, i, f, env={"LC_ALL": loc}, tags=["s:env", f"env:LC_ALL={loc}", "in:utf8"])
    return ps.probes


def accepted_classes(probes: list[Probe], symbols: list[dict],
                     default_input: str | None = None) -> dict[str, list[str]]:
    """From sweep results: option -> value classes that exited 0 on every probe of that class (only probes on
    ``default_input`` count when given: other inputs may lack the fields an expression refers to)."""
    seen: dict[tuple[str, str], list[bool]] = {}
    for probe, sym in zip(probes, symbols, strict=True):
        opt = next((t[4:] for t in probe.tags if t.startswith("opt:")), None)
        val = next((t[4:] for t in probe.tags if t.startswith("val:")), None)
        inp = next((t[3:] for t in probe.tags if t.startswith("in:")), None)
        if default_input and inp not in (None, default_input):
            continue
        if opt and val and "s:sweep" in probe.tags:
            seen.setdefault((opt, val), []).append(isinstance(sym, dict) and sym.get("exit") == 0)
    out: dict[str, list[str]] = {}
    for (opt, val), oks in sorted(seen.items()):
        if all(oks):
            out.setdefault(opt, []).append(val)
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
            for n in order:
                def gain(v, n=n, row=row):
                    return sum(((n, v, m, row[m]) in uncovered) or ((m, row[m], n, v) in uncovered) for m in row)
                row[n] = max(range(len(params[n])), key=lambda v, gain=gain: (gain(v), rng.random()))
            cov = sum((x, row[x], y, row[y]) in uncovered for x, y in itertools.combinations(names, 2))
            if cov > best_cov:
                best, best_cov = row, cov
        for x, y in itertools.combinations(names, 2):
            uncovered.discard((x, best[x], y, best[y]))
        rows.append({n: params[n][v] for n, v in best.items()})
    return rows


def plan_pairwise(model: dict, hints: ProbeHints, accepted: dict[str, list[str]], *, max_classes: int = 4,
                  seed: int = 0) -> list[Probe]:
    """2-way covering array over options x *accepted* value classes (+ input, + delivery mode)."""
    ps = _ProbeSet(hints.cmd)
    grid: dict[str, list] = {}
    for p in probe_options(model, hints):
        if p["type"] == "path":
            continue
        if p["arity"] == "none":
            if "flag" in accepted.get(p["name"], []):
                grid[p["name"]] = [None, ("flag", None)]
            continue
        classes = [c for c in accepted.get(p["name"], []) if c != "flag"][:max_classes]
        values = hints.values(p["type"], p["name"])
        if classes:
            grid[p["name"]] = [None] + [(c, values[c.split(".", 1)[1]]) for c in classes
                                        if c.split(".", 1)[1] in values]
    if len(grid) < 2:
        return []
    if hints.takes_files and hints.pair_inputs:
        grid["@input"] = hints.pair_inputs
        grid["@mode"] = ["stdin", "file"]
    for row in pairwise(grid, seed=seed):
        argv, tags, selector = [], ["s:pairwise"], False
        for name, v in row.items():
            if name.startswith("@") or v is None:
                continue
            tags.append(f"opt:{name}")
            if v[1] is None:
                argv.append(name)
            else:
                argv += [name, v[1]]
                tags.append(f"val:{name}={v[0]}")
            selector |= name in hints.selector_options or (bool(hints.base) and name == hints.base[0])
        if not selector:
            argv += hints.base
        data = hints.input(row["@input"]) if "@input" in row else None
        a, i, f = _deliver(argv, data, row.get("@mode", "stdin"))
        extra = [f"in:{row['@input']}", f"mode:{row['@mode']}"] if data is not None else []
        ps.add(a, i, f, tags=tags + extra)
    return ps.probes


def mutations(data: str, lines: dict[str, str] | None = None) -> dict[str, str]:
    """Generic edits of a line-oriented input; ``lines`` are inserted at the start, the middle and the end."""
    rows = data.splitlines(keepends=False)
    eol = "\n"
    body = eol.join(rows) + (eol if data.endswith(("\n", "\r")) else "")
    mid = max(1, len(rows) // 2)
    out = {
        "no_final_newline": body.rstrip("\r\n"),
        "crlf": "\r\n".join(rows) + "\r\n",
        "bom": "\xef\xbb\xbf" + body,
        "blank_line_middle": eol.join(rows[:mid] + [""] + rows[mid:]) + eol,
        "whitespace_line_middle": eol.join(rows[:mid] + ["   \t "] + rows[mid:]) + eol,
        "trailing_spaces": eol.join(r + "   " for r in rows) + eol,
        "leading_spaces": eol.join("  " + r for r in rows) + eol,
        "duplicate_first": eol.join(rows[:1] + rows) + eol,
        "duplicate_last": eol.join(rows + rows[-1:]) + eol,
        "first_line_only": (rows[0] + eol) if rows else "",
        "drop_first": eol.join(rows[1:]) + eol,
        "invalid_utf8_line": eol.join(rows[:mid] + ["\xff\xfe"] + rows[mid:]) + eol,
        "double_blank_end": body + eol + eol,
    }
    for name, line in (lines or {}).items():
        out[f"{name}@start"] = eol.join([line] + rows) + eol
        out[f"{name}@middle"] = eol.join(rows[:mid] + [line] + rows[mid:]) + eol
        out[f"{name}@end"] = eol.join(rows + [line]) + eol
    return out
