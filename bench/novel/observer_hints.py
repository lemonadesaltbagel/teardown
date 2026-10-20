"""Observer-side probe hints for the novel `quill` benchmark (dirty side).

Written from the tool's public manual and --help only; never from its source or the hidden test suite.
"""

from __future__ import annotations

STAFF = "% name | dept | age | salary | city\nada | eng | 36 | 72000 | Oslo\nbob | ops | 7 | 48000.5 | Rome\ncy | eng | 28 | 41000 | oslo\n" \
        "dee | | 51 | | Lima\n"
NUMS = "% a | b | c\n1 | 2 | x\n007 | -3 | y\n1_000 | 0.5 | \n-0 | 2.50 | z\n"
HEADERLESS = "ada | 1\nbob | 2\n"
DUPS = "% k | v\n1 | a\n1 | b\n2 | c\n\"1\" | d\n"
MESSY = "# comment\n\n% x | y\n  spaced  |  cell  \n a\\|b | c\\\\d\n%not a header | 2\n"
CRLF = "% a | b\r\n1 | 2\r\n"
EMPTY_HEADER_ONLY = "% a | b\n"
BAD_COUNT = "% a | b\n1 | 2 | 3\n"
BAD_HEADER = "% 1a | b\n1 | 2\n"
UNICODE = "% name | n\nstraße | 1\nété | 2\n"

EXPRS = {
    "true": "yes", "false": "no", "num_cmp": "@age > 30", "num_eq": "@age = 36", "text_eq": '@city = "Oslo"',
    "kind_mismatch_eq": '@age = "36"', "contains": '@city ~ "o"', "not_contains": '@city !~ "o"',
    "and_or": "@age > 30 and @dept = \"eng\" or @age < 10", "not": "not @age > 30", "chain_error": "1 < 2 < 3",
    "void_cmp": "@salary > 0", "fallback": "(@salary ?? 0) > 1000", "ternary": '@age > 30 ? yes : no',
    "positional": "@2 = \"eng\"", "ordinal": "@# > 2", "unknown_field": "@nope = 1", "syntax_error": "@age >",
    "unknown_fn": "frob(@age)", "wrong_arity": "len()", "bare_word": "age > 3", "number_result": "@age",
    "text_result": "@name", "void_result": "@salary", "div_zero": "@age / 0 > 1", "text_arith": "@name + 1 > 0",
    "len": "len(@name) = 3", "upper": 'upper(@city) = "OSLO"', "word": 'word("a b c", -1) = "c"',
    "round_half": "round(2.5) = 3", "arith_even": "2.5 + 0 = 2.5", "mod_sign": "-7 % 3 = 2", "pow_assoc": "2 ^ 3 ^ 2 = 512",
    "neg_pow": "-2 ^ 2 = -4", "concat_prec": '1 + 2 .. 3 = "33"', "num_fn": 'num(" 12 ") = 12', "kind_fn": 'kind(@salary) = "void"',
    "clamp_bad": "clamp(1, 5, 2) = 1", "string_escape": '"a\\"b" ~ "\\""', "unterminated": '"abc', "overflow": "10 ^ 15 > 0",
    "big_ok": "10 ^ 14 > 0", "pow_frac": "2 ^ 0.5 > 1", "pow_neg": "2 ^ -3 = 0.125", "zero_neg_pow": "0 ^ -1 = 0",
}
DERIVES = {
    "arith": "total=@salary * 2", "concat": 'label=@name .. "/" .. @dept', "fmt": "pay=fmt(@salary, 2)",
    "round": "r=round(@salary / 3, 2)", "overwrite": "age=@age + 1", "void_prop": "x=@salary + 1",
    "fallback": "x=@salary ?? 0", "initials": "i=initials(@name .. \" x\")", "pad": "p=pad(@name, -6, \".\")",
    "swap": 's=swap(@city, "o", "0")', "occurs": 'o=occurs(@city, "o")', "rev": "r=rev(@name)", "left_right": "l=left(@name, 2) .. right(@name, 1)",
    "kind": "k=kind(@salary)", "num": "n=num(@city)", "text": "t=text(@age)", "minmax": "m=max(@age, 30)",
    "minmax_mixed": 'm=max(@age, "x")', "sign_abs": "s=sign(-3) .. abs(-3)", "floor_ceil": "f=floor(-1.5) .. ceil(-1.5)",
    "division": "d=@age / 7", "sixdp": "d=1 / 3", "bool_out": "b=@age > 30", "bad_name": "1x=@age", "no_equals": "@age",
    "empty_expr": "x=", "unknown_fn": "x=frob(1)", "eval_error": "x=@name * 2", "ordinal": "o=@#", "positional": "p=@1",
    "upper_unicode": 'u=upper("straße")', "word_zero": 'w=word("a b", 0)', "half_even": "h=0.5 + 2", "big": "b=999999999999999 + 1",
}
ROLLS = {
    "count": "dept: n=count()", "sum": "dept: s=sum(@salary)", "mean": "dept: m=mean(@age)", "no_keys": ": n=count(), s=sum(@age)",
    "minmax": "dept: lo=min(@age), hi=max(@age)", "first_last": "dept: f=first(@name), l=last(@name)", "join": "dept: j=join(@name)",
    "distinct": ": d=distinct(@city)", "count_expr": "dept: c=count(@salary)", "multi_key": "dept, city: n=count()",
    "sum_text": "dept: s=sum(@name)", "dup_name": "dept: dept=count()", "no_colon": "dept n=count()", "no_aggs": "dept:",
    "unknown_agg": "dept: x=median(@age)", "unknown_key": "nope: n=count()", "mixed_minmax": ": m=max(@city)",
}
KEEPS = {"one": "name", "two": "name,age", "reorder": "age,name", "drop": "-salary", "drop_two": "-salary,-city",
         "unknown": "nope", "mixed": "name,-age", "empty": "", "dup": "name,name", "positional": "2"}
SORTS = {"one": "age", "desc": "-age", "two": "dept,-age", "text": "city", "void_col": "salary", "desc_void": "-salary",
         "unknown": "nope", "empty": ""}
FIRST_BY = {"one": "dept", "two": "dept,city", "unknown": "nope", "empty": ""}
LIMITS = {"zero": "0", "one": "1", "two": "2", "neg": "-1", "neg_big": "-99", "big": "99", "nonnum": "x", "float": "1.5", "empty": ""}
FORMATS = {"ledger": "ledger", "grid": "grid", "card": "card", "kv": "kv", "bad": "xml", "empty": "", "upper": "GRID"}
MODES = {"abort": "abort", "void": "void", "skip": "skip", "bad": "ignore", "empty": ""}
SEPS = {"pipe": "|", "comma": ",", "tab": "\t", "two": "ab", "empty": "", "space": " ", "backslash": "\\", "percent": "%"}
OUT_FILES = {"new": "out.ql", "nested_missing": "no/such/out.ql", "same_as_input": "in.txt", "empty": ""}


DESIGNED = {  # from the manual's statements about stage order, files, reject/out/tally
    "limit_then_sort": ["-n", "2", "-s", "-age"], "sort_then_limit": ["-s", "-age", "-n", "2"],
    "where_then_derive": ["-w", "@age > 30", "-d", "x=@age * 2"], "derive_then_where": ["-d", "x=@age * 2", "-w", "@x > 60"],
    "keep_then_where_missing": ["-k", "name", "-w", "@age > 1"], "roll_then_sort": ["-r", "dept: n=count()", "-s", "-n"],
    "sort_then_ordinal": ["-s", "-age", "-d", "o=@#"], "roll_ordinal": ["-r", "dept: n=count()", "-d", "o=@#"],
    "two_files": ["in.txt", "in2.txt"], "two_files_ordinal": ["-d", "o=@#", "in.txt", "in2.txt"],
    "reject_where": ["-w", "@age > 30", "--reject", "rej.ql"], "out_tally": ["-o", "out.ql", "-t"],
    "count_where": ["-c", "-w", "@age > 30"], "fail_empty": ["-e", "-w", "no"], "tally_where": ["-t", "-w", "@age > 30"],
    "on_error_void": ["--on-error", "void", "-d", "x=@name * 2"], "on_error_skip": ["--on-error", "skip", "-w", "@name * 2 > 1"],
    "raw_eq": ["--raw", "-w", '@age = "36"'], "loose": ["--loose"], "bundled": ["-cH"], "attached_value": ["-n2"],
    "dash_value": ["-n", "-1"], "long_eq": ["--limit=1"], "grid_noheader": ["-f", "grid", "-H"],
    "card_where": ["-f", "card", "-w", "@age > 30"], "kv_keep": ["-f", "kv", "-k", "name,age"],
    "repeated_stage": ["-w", "@age > 10", "-w", "@age < 40"], "first_by_sorted": ["-s", "age", "-b", "dept"],
    "version": ["--version"], "help_short": ["-h"],
}


def hints() -> dict:
    return {
        "cmd": "quill",
        "base": [],
        "selector_options": [],
        "takes_files": True,
        "default_input": "staff",
        "sweep_inputs": ["staff", "nums"],
        "inputs": ["staff", "nums", "headerless", "dups", "messy", "crlf", "header_only", "bad_count", "bad_header",
                   "unicode", "empty", "no_eol", "invalid_utf8"],
        "pair_inputs": ["staff"],
        "unicode_argv": [["-d", 'u=upper(@name)'], ["-s", "name"]],
        "extra_argv": DESIGNED,
        "extra_inputs": {"staff": STAFF, "nums": NUMS, "headerless": HEADERLESS, "dups": DUPS, "messy": MESSY,
                         "crlf": CRLF, "header_only": EMPTY_HEADER_ONLY, "bad_count": BAD_COUNT,
                         "bad_header": BAD_HEADER, "unicode": UNICODE.encode().decode("latin-1")},
        "option_values": {"-w": EXPRS, "-x": {k: EXPRS[k] for k in ("true", "num_cmp", "syntax_error", "div_zero")},
                          "-d": DERIVES, "-r": ROLLS, "-k": KEEPS, "-s": SORTS, "-b": FIRST_BY, "-n": LIMITS,
                          "-f": FORMATS, "--on-error": MODES, "--sep": SEPS, "-o": OUT_FILES, "--reject": OUT_FILES},
    }
