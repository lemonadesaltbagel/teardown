"""Observer-side probe hints for the jq benchmark (dirty side).

Written by the observer from general knowledge of the tool's interface, NOT from the hidden test suite: the
benchmark's integrity depends on the probe corpus being independent of ``hidden/jq.test``. In production an LLM
observer proposes these classes; here they are hand-written for reproducibility.
"""

from __future__ import annotations

FILTERS: dict[str, str] = {
    # paths and access
    "identity": ".", "field": ".a", "field_missing": ".zz", "nested": ".b.c", "quoted_field": '."a"',
    "optional_field": ".a?", "index": ".[0]", "neg_index": ".[-1]", "slice": ".[1:3]", "slice_open": ".[2:]",
    "iterate": ".[]", "iterate_opt": ".[]?", "recurse": "..", "recurse_fn": "[recurse] | length",
    "keys": "keys", "keys_unsorted": "keys_unsorted", "has": 'has("a")', "in": '"a" | in({"a":1})',
    "paths": "[paths]", "leaf_paths": "[leaf_paths]", "getpath": 'getpath(["b","c"])',
    "setpath": 'setpath(["a"]; 9)', "delpaths": 'delpaths([["a"]])', "del": "del(.a)",
    "to_entries": "to_entries", "from_entries": '[{"key":"x","value":1}] | from_entries',
    "with_entries": "with_entries(.value |= tostring)",
    # construction
    "array_cons": "[.[]?]", "object_cons": "{a: 1, b: .}", "object_shorthand": "{a}",
    "object_dynamic_key": '{("k" + "1"): 2}', "object_multi": "{a: (1,2)}", "string_interp": '"v=\\(.)"',
    # arithmetic and comparison
    "add_numbers": "1 + 2", "add_strings": '"a" + "b"', "add_arrays": "[1] + [2]", "add_objects": '{"a":1} + {"b":2}',
    "add_null": "null + 1", "sub": "10 - 3", "mul": "3 * 4", "div": "7 / 2", "mod": "7 % 3",
    "div_zero": "1 / 0", "mod_zero": "1 % 0", "str_mul": '"ab" * 3', "obj_mul": '{"a":{"b":1}} * {"a":{"c":2}}',
    "str_div": '"a,b,c" / ","', "arr_sub": "[1,2,3,2] - [2]", "cmp": "[1 < 2, 2 <= 2, 3 > 4, 1 == 1.0, 1 != 2]",
    "type_order": "[null, false, 0, \"\", [], {}] | sort", "and_or": "[true and false, true or false, (null | not)]",
    "add_mismatch": '1 + "a"', "sub_mismatch": '{} - 1',
    # conditionals and control
    "if": 'if . == null then "n" else "v" end', "if_elif": "if 1 > 2 then 1 elif 2 > 1 then 2 else 3 end",
    "alternative": ".missing // \"default\"", "alt_false": "false // 7", "try": "try error(\"x\") catch .",
    "try_no_catch": '[.[]? | try (if . == 2 then error("e") else . end)]', "error_obj": 'try error({"a":1}) catch .a',
    "error_uncaught": 'error("boom")', "label_break": "[label $f | 1, 2, break $f, 3]",
    "reduce": "reduce (1,2,3) as $x (0; . + $x)", "foreach": "[foreach (1,2,3) as $x (0; . + $x)]",
    "foreach_extract": "[foreach (1,2,3) as $x (0; . + $x; . * 10)]", "limit": "[limit(2; 1,2,3)]",
    "first_last": "[first(1,2,3), last(1,2,3)]", "range": "[range(3)]", "range2": "[range(1;7;2)]",
    "until": "0 | until(. >= 5; . + 2)", "while": "[1 | while(. < 20; . * 3)]", "repeat": "[limit(3; 1 | repeat(. * 2))]",
    "empty": "[1, empty, 2]", "comma": "1, 2", "pipe": "[1,2] | length", "as_binding": ". as $v | [$v, $v]",
    "destructure": '[1,[2,3]] as [$a, [$b]] | {$a, $b}', "def": "def f(g): [g, g]; f(1)",
    "def_recursive": "def fac: if . <= 1 then 1 else . * (. - 1 | fac) end; 5 | fac",
    "optional_op": '[.[]? | .a?]', "reduce_obj": "reduce ([\"a\",1],[\"b\",2])[] as [$k,$v] ({}; .[$k] = $v)",
    # updates
    "update": ".a |= 5", "update_add": ".a += 1", "update_each": "[1,2] | .[] |= . * 2", "assign": ".a = .b",
    "update_missing": ".x.y |= 1", "update_empty": "[1,2,3] | (.[] | select(. == 2)) |= empty",
    # builtins: arrays
    "length": "length", "utf8bytelength": '"é" | utf8bytelength', "map": "[1,2,3] | map(. + 1)",
    "map_values": '{"a":1} | map_values(. + 1)', "select": "[.[]? | select(type == \"number\")]",
    "sort": "[3,1,2] | sort", "sort_by": '[{"a":2},{"a":1}] | sort_by(.a)', "group_by": "[1,2,1] | group_by(.)",
    "unique": "[1,2,1] | unique", "unique_by": '["ab","c","de"] | unique_by(length)', "min_max": "[[3,1,2] | min, max]",
    "min_empty": "[] | min", "reverse": "[1,2,3] | reverse", "contains": '"foobar" | contains("bar")',
    "inside": '"bar" | inside("foobar")', "indices": '[1,2,1] | indices(1)', "index_str": '"a,b,a" | index("a"), rindex("a")',
    "flatten": "[1,[2,[3]]] | flatten", "flatten_depth": "[1,[2,[3]]] | flatten(1)", "add": "[1,2,3] | add",
    "add_empty": "[] | add", "any_all": "[[true,false] | any, all]", "join": '["a","b"] | join("-")',
    "join_mixed": '["a",1,null] | join(",")', "transpose": "[[1,2],[3]] | transpose", "combinations": "[[1,2],[3,4]] | [combinations]",
    "tostream": "[{\"a\":[1]} | tostream]", "fromstream": "fromstream(1 | truncate_stream([[0],1],[[1,0],2],[[1,0]],[[1]]))",
    "walk": "[1,[2]] | walk(if type == \"number\" then . + 1 else . end)", "splits": '[ "a1b2c" | splits("[0-9]") ]',
    "input_line": "[inputs]", "env": "env | type", "builtins_type": "builtins | length > 10",
    "getpath_missing": 'getpath(["x","y"])', "paths_filter": '[paths(type == "number")]', "isvalid": "[1, \"a\"] | map(tostring)",
    "del_multi": "[1,2,3,4] | del(.[0,2])", "to_entries_arr": "[\"a\"] | to_entries", "has_index": "[1] | has(0)",
    "limit_zero": "[limit(0; 1,2)]", "nth": "[nth(1; 1,2,3)]", "first_empty": "[first(empty)]",
    "infinite": "[infinite, -infinite] | map(. > 0)", "nan": "nan | isnan", "nan_sort": "[nan, 1] | sort | .[1]",
    "splits_empty": '"" | [splits(",")]', "getpath_null": 'null | getpath(["a"])', "ascii": "65 | [.] | implode",
    # builtins: strings and formats
    "tostring": "[1, \"1\", [1]] | map(tostring)", "tonumber": '"12.5" | tonumber', "tonumber_bad": '"x" | tonumber',
    "type": "[null,true,1,\"a\",[],{}] | map(type)", "ascii_case": '"aBc" | ascii_downcase, ascii_upcase',
    "ltrimstr": '"foobar" | ltrimstr("foo"), rtrimstr("bar")', "startswith": '"foobar" | startswith("foo"), endswith("x")',
    "split": '"a,b,,c" | split(",")', "explode_implode": '"héllo" | explode | implode', "explode": '"hé" | explode',
    "test": '"foo123" | test("[0-9]+")', "test_flags": '"FOO" | test("foo"; "i")', "match": '"abc" | match("b") | .offset',
    "capture": '"x=1" | capture("(?<k>[a-z])=(?<v>[0-9])")', "scan": '[ "a1b22" | scan("[0-9]+") ]',
    "sub": '"aaa" | sub("a"; "b")', "gsub": '"aaa" | gsub("a"; "b")', "gsub_named": '"a1" | gsub("(?<d>[0-9])"; "<\\(.d)>")',
    "regex_bad": '"a" | test("(")', "base64": '"hi" | @base64', "base64d": '"aGk=" | @base64d', "csv": '[1,"a,b",null] | @csv',
    "tsv": '[1,"a\\tb"] | @tsv', "html": '"<&>" | @html', "uri": '"a b&c" | @uri', "sh": '"it\'s" | @sh',
    "json_fmt": "[1,\"a\"] | @json", "text_fmt": "[1] | @text", "format_interp": '@base64 "x\\(.)y"',
    "tojson_fromjson": '[1,{"a":2}] | tojson | fromjson', "fromjson_bad": '"{" | fromjson', "ascii_only": '"é" | @json',
    "ltrimstr_nonstr": "1 | ltrimstr(\"a\")", "string_index": '"abc" | .[1:]', "string_length": '"héllo" | length',
    "number_format": "[1.0, 1.5, 100000000000000000000, 0.1 + 0.2, 1e1000, -0]", "large_int": "12345678901234567890",
    "dates": '0 | todate', "strftime": '0 | strftime("%Y-%m-%dT%H:%M:%SZ")', "fromdate": '"1970-01-02T00:00:00Z" | fromdate',
    "mktime": '[1970,0,1,0,0,0,0,0] | mktime', "gmtime": "86400 | gmtime", "math": "[16 | sqrt, floor, (2.7 | ceil), (4 | pow(.;2)), (100 | log10)]",
    "abs_like": "[-3, 3] | map(fabs)", "significand": "8 | significand", "splits_regex": '"a, b" | [splits(", *")]',
    "tojson_unicode": '"\\u00e9" | tojson', "ascii_downcase_nonascii": '"É" | ascii_downcase',
    "getpath_bad": '1 | getpath(["a"])', "keys_bad": "1 | keys", "iterate_bad": "1 | .[]", "index_bad": '{"a":1} | .[0]',
    "field_on_array": "[1] | .a", "has_bad": '1 | has("a")', "implode_bad": '"a" | implode',
    "env_var": "$ENV | type", "loc": "$__loc__", "input_filename": "input_filename", "halt_error": '"bye\\n" | halt_error',
    "halt_error_code": '{"a":1} | halt_error(3)', "halt": "1, halt, 2", "getpath_arr": '[[1]] | getpath([0,0])',
    "splits_null": "null | [.[]?]", "ltrimstr_full": '"foo" | ltrimstr("foo")', "tostring_obj": '{"a":[1]} | tostring',
    "object_key_order": '{"b":1, "a":2}', "object_dup_key": '{"a":1, "a":2}', "array_index_float": "[1,2,3] | .[1.7]",
    "slice_neg": "[1,2,3,4] | .[-2:]", "slice_null": "null | .[1:2]", "assign_slice": "[1,2,3] | .[1:] = [9]",
    "recurse_cond": "[2 | recurse(. * .; . < 100)]", "getpath_nested_null": '{"a":null} | .a.b',
    "error_null": "try error(null) catch .", "error_message": 'try (1 | error) catch .', "ltrim_type": '[1,"a"] | map(type)',
    "min_by": '[{"a":3},{"a":1}] | min_by(.a), max_by(.a)', "splits_map": '"a b" | split(" ") | map(length)',
    "tostream_rt": '[1,[2]] | [tostream] | fromstream(.[])', "env_path": "$ENV.HOME | type", "input": "input",
    "debug": "1 | debug | . + 1", "stderr": '"x" | stderr | length', "ltrimstr_regex": '"a.b" | split(".")',
    "test_array_form": '"abc" | test(["B", "i"])', "sub_flags": '"aAa" | sub("a"; "x"; "gi")', "ascii_table": "[range(65;70)] | implode",
    "getpath_paths": '[paths] | length', "tojson_nan": "[nan] | tojson", "isinfinite": "[infinite | isinfinite, (1 | isinfinite)]",
    "isnormal": "[0, 1] | map(isnormal)", "splits_unicode": '"a→b" | split("→")', "abs_tostring": "-1.5 | tostring",
    "add_object_null": "{} + null", "multiply_null": "null * 2", "infinite_tostring": "infinite | tostring",
    "keys_order": '{"b":1,"a":2,"c":3} | keys', "sort_strings": '["b","a","B"] | sort', "sort_objects": '[{"b":1},{"a":2}] | sort',
    "unique_objects": '[{"a":1},{"a":1}] | unique', "group_by_strings": '["a","b","a"] | group_by(.) | map(length)',
    # syntax and compile errors
    "syntax_unclosed": "[1,", "syntax_bad_token": ".a ||| .b", "unknown_function": "nosuchfn", "wrong_arity": "map",
    "undefined_var": "$nope", "bad_format": "@nosuchformat", "empty_program": "", "comment": ".a # comment",
    "keyword_as_field": ".and", "reserved_def": "def if: 1; 1", "string_bad_escape": '"\\q"', "unbalanced_brace": "{a:1",
}

INPUT_SAMPLES: dict[str, str] = {
    "obj": '{"a":1,"b":{"c":[1,2,{"d":"x"}]},"e":null}\n',
    "arr": "[1,2,3,4,5]\n",
    "mixed_arr": '[1,"a",null,true,{"k":"v"},[2]]\n',
    "str": '"hello"\n',
    "null": "null\n",
    "stream": '1 "two" [3] {"four":4}\n',
    "bad_json": '{"a":\n',
    "nan_like": '[NaN, 1]\n',
    "big_num": '[100000000000000000001, 1.0, 1e2, -0.0]\n',
}


def hints() -> dict:
    return {
        "cmd": "jq",
        "base": ["."],
        "selector_options": [],
        "takes_files": True,
        "default_input": "obj",
        "sweep_inputs": ["obj", "arr"],
        "inputs": list(INPUT_SAMPLES),
        "pair_inputs": ["obj", "arr", "stream"],
        "operand_type": "jqfilter",
        "operand_forms": [["{v}"]],
        "operand_options": [["-c"], []],
        "unicode_argv": [["-c", "."], ["-r", ".[]?"]],
        "skip_options": ["-L", "--seq", "--stream-errors", "--rawfile", "--slurpfile", "--from-file", "-f", "--run-tests",
                         "--debug-dump-disasm", "--debug-trace", "--debug-trace=all", "-C", "--color-output"],
        "extra_inputs": INPUT_SAMPLES,
        "extra_values": {"jqfilter": FILTERS},
    }
