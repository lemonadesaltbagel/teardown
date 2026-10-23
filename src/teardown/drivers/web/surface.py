"""The user-facing Playwright surface as page pairs: what a role/label/text-based test suite can tell apart.

Each case is two pages that differ in exactly one thing a user-facing locator or assertion can check. A web
abstraction records that thing when the two pages give different symbols. ``audit`` runs every case under an
abstraction version; the observer guide's "what a symbol records" section is kept in step with it.

Not part of the surface, by design: CSS classes and styles, element ids, test ids, JavaScript properties and
`href` values. A user-facing suite does not address them, and a clone is free to differ there.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HEAD = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Surface</title></head><body>'
_IMG = "data:image/gif;base64,R0lGODlhAQABAAAAACw="


@dataclass(frozen=True)
class Case:
    id: str
    checks: str  # the Playwright locator or assertion that tells the pages apart
    a: str
    b: str


CASES: list[Case] = [
    # roles and names
    Case("role", 'get_by_role("link", name="Open")', '<button>Open</button>', '<a href="#o">Open</a>'),
    Case("heading-level", 'get_by_role("heading", level=3)', "<h3>Readings</h3>", "<h4>Readings</h4>"),
    Case("heading-deep", 'get_by_role("heading", name="Readings")', "<h4>Readings</h4><p>x</p>", "<p>x</p>"),
    Case("main", 'get_by_role("main")', "<main><p>Body</p></main>", "<div><p>Body</p></div>"),
    Case("article", 'get_by_role("article", name="FN-101")',
         '<article aria-label="FN-101"><p>Body</p></article>', "<div><p>Body</p></div>"),
    Case("list", 'get_by_role("listitem")', "<ul><li>Alta Ridge</li></ul>", "<p>Alta Ridge</p>"),
    Case("image", 'get_by_alt_text("Fog net")', f'<img alt="Fog net" src="{_IMG}"><p>x</p>', "<p>x</p>"),
    Case("progress", 'get_by_role("progressbar") / to_have_attribute("aria-valuenow")',
         '<progress aria-label="Season" value="30" max="100"></progress>',
         '<progress aria-label="Season" value="60" max="100"></progress>'),
    Case("checked-mixed", 'get_by_role("checkbox", checked=...) / to_be_checked',
         '<div role="checkbox" aria-checked="mixed" tabindex="0">All nets</div>',
         '<div role="checkbox" aria-checked="false" tabindex="0">All nets</div>'),
    Case("expanded", 'get_by_role("button", expanded=True)', '<button aria-expanded="true">Filters</button>',
         '<button aria-expanded="false">Filters</button>'),
    Case("pressed", 'get_by_role("button", pressed=True)', '<button aria-pressed="true">Map</button>',
         '<button aria-pressed="false">Map</button>'),
    Case("selected-tab", 'get_by_role("tab", selected=True)',
         '<div role="tablist"><button role="tab" aria-selected="true">A</button>'
         '<button role="tab" aria-selected="false">B</button></div>',
         '<div role="tablist"><button role="tab" aria-selected="false">A</button>'
         '<button role="tab" aria-selected="true">B</button></div>'),
    Case("listbox-options", 'get_by_role("listbox") / get_by_role("option")',
         '<select multiple aria-label="Ridges"><option>Alta</option><option>Bruma</option></select>',
         '<select multiple aria-label="Ridges"><option>Alta</option><option>Cerro</option></select>'),
    # how many, and where
    Case("count", 'get_by_role("button", name="Delete") / to_have_count(2)',
         "<button>Delete</button><button>Delete</button>", "<button>Delete</button>"),
    Case("in-dialog", 'get_by_role("dialog").get_by_role("button", name="OK")',
         '<div role="dialog" aria-label="Confirm"><p>Sure?</p><button>OK</button></div>',
         '<div role="dialog" aria-label="Confirm"><p>Sure?</p></div><button>OK</button>'),
    Case("in-navigation", 'get_by_role("navigation").get_by_role("link", name="Nets")',
         '<nav aria-label="Main"><a href="#n">Nets</a></nav>', '<nav aria-label="Main"></nav><a href="#n">Nets</a>'),
    Case("in-listitem", 'get_by_role("listitem").filter(has_text="B").get_by_role("button")',
         "<ul><li>A <button>Delete</button></li><li>B</li></ul>",
         "<ul><li>A</li><li>B <button>Delete</button></li></ul>"),
    Case("in-group", 'get_by_role("group", name="Net actions").get_by_role("button")',
         '<div role="group" aria-label="Net actions"><button>Retire</button></div>',
         '<div role="group" aria-label="Net actions"></div><button>Retire</button>'),
    Case("row-header", 'get_by_role("rowheader")',
         '<table aria-label="T"><tr><th>Day</th></tr><tr><th scope="row">Day 12</th></tr></table>',
         '<table aria-label="T"><tr><th>Day</th></tr><tr><td>Day 12</td></tr></table>'),
    # labels, placeholders, titles
    Case("placeholder", 'get_by_placeholder("e.g. FN-101")',
         '<label>Code <input placeholder="e.g. FN-101"></label>', "<label>Code <input></label>"),
    Case("title-attr", 'get_by_title("Season day")', '<p><span title="Season day">D80</span></p>',
         "<p><span>D80</span></p>"),
    # values and field state
    Case("value", 'to_have_value("Alta")', '<label>Ridge <input value="Alta"></label>',
         '<label>Ridge <input value="Bruma"></label>'),
    Case("value-number", 'to_have_value("12")', '<label>Count <input type="number" value="12"></label>',
         '<label>Count <input type="number" value="13"></label>'),
    Case("value-textarea", 'to_have_value(...)', "<label>Note <textarea>Torn mesh</textarea></label>",
         "<label>Note <textarea>Torn frame</textarea></label>"),
    Case("editable", "to_be_editable", '<label>Code <input value="FN-1" readonly></label>',
         '<label>Code <input value="FN-1"></label>'),
    Case("required", 'to_have_attribute("aria-required") / required',
         '<label>Code <input required value="FN-1"></label>', '<label>Code <input value="FN-1"></label>'),
    Case("masked", 'to_have_attribute("type", "password")', '<label>Password <input type="password"></label>',
         '<label>Password <input type="text"></label>'),
    Case("aria-invalid", 'to_have_attribute("aria-invalid", "true")',
         '<label>Litres <input aria-invalid="true"></label>', "<label>Litres <input></label>"),
    Case("error-message", "to_have_accessible_error_message",
         '<label>Litres <input aria-invalid="true" aria-errormessage="e"></label><p id="e">Too much</p>',
         '<label>Litres <input aria-invalid="true"></label><p id="e">Too much</p>'),
    Case("description", "to_have_accessible_description",
         '<button aria-describedby="d">Retire</button><p id="d">Cannot be undone</p>',
         '<button>Retire</button><p id="d">Cannot be undone</p>'),
    Case("current", 'to_have_attribute("aria-current", "page")',
         '<nav aria-label="M"><a href="#a" aria-current="page">Nets</a></nav>',
         '<nav aria-label="M"><a href="#a">Nets</a></nav>'),
    Case("sort", 'to_have_attribute("aria-sort", "ascending")',
         '<table aria-label="T"><tr><th aria-sort="ascending">Day</th></tr><tr><td>1</td></tr></table>',
         '<table aria-label="T"><tr><th aria-sort="descending">Day</th></tr><tr><td>1</td></tr></table>'),
    Case("disabled", "to_be_disabled", "<button disabled>Save</button>", "<button>Save</button>"),
    Case("checked", "to_be_checked", '<label><input type="checkbox" checked> Damaged</label>',
         '<label><input type="checkbox"> Damaged</label>'),
    # text as text assertions read it
    Case("text", 'get_by_text("Active")', "<div>Active</div>", "<div>Retired</div>"),
    Case("text-inline", 'to_have_text("Signed in as Otto")', "<p>Signed in as <b>Otto</b></p>",
         "<p>Signed in as</p><p>Otto</p>"),
    Case("hidden", "to_be_hidden", '<p>Saved</p><p hidden>Draft</p>', "<p>Saved</p><p>Draft</p>"),
    Case("focus-heading", 'get_by_role("heading", name="Programme") / to_be_focused',
         '<h2 tabindex="-1" id="f">Programme</h2><h2 tabindex="-1">Details</h2>'
         '<script>document.getElementById("f").focus()</script>',
         '<h2 tabindex="-1">Programme</h2><h2 tabindex="-1" id="f">Details</h2>'
         '<script>document.getElementById("f").focus()</script>'),
    Case("status", 'get_by_role("status")', '<p role="status">Saved.</p>', "<p>Saved.</p>"),
    Case("alert", 'get_by_role("alert")', '<p role="alert">Failed.</p>', "<p>Failed.</p>"),
]


# Pages a user-facing suite cannot tell apart: an abstraction must give them the same symbol, or a clone that
# differs only in implementation would fail verification.
SAME: list[Case] = [
    Case("class-id-testid", "(implementation)", '<p class="a" id="x" data-testid="t">Saved</p>', "<p>Saved</p>"),
    Case("wrapper", "(implementation)", "<div><div><p>Saved</p></div></div>", "<p>Saved</p>"),
    Case("inline-span", 'to_have_text("Signed in as Otto")', "<p>Signed in as <span>Otto</span></p>",
         "<p>Signed in as Otto</p>"),
    Case("href", "(implementation)", '<a href="/nets?page=1">Nets</a>', '<a href="/nets">Nets</a>'),
    Case("label-kind", 'get_by_label("Code")', "<label>Code <input></label>",
         '<label for="c">Code</label><input id="c">'),
    Case("button-kind", 'get_by_role("button", name="Save")', '<button type="submit">Save</button>',
         '<input type="submit" value="Save">'),
    Case("style", "(implementation)", '<p style="color: red">Saved</p>', "<p>Saved</p>"),
]


def write_pages(root: Path) -> None:
    for case in [*CASES, *SAME]:
        for side in ("a", "b"):
            (root / f"{case.id}.{side}.html").write_text(_HEAD + getattr(case, side) + "</body></html>")


def _without_path(symbol: Any) -> Any:
    return {k: v for k, v in symbol.items() if k != "path"} if isinstance(symbol, dict) else symbol


def audit(versions: list[str], *, root: Path) -> dict[str, dict[str, bool]]:
    """{case id: {version: the two pages give different symbols}}. Every CASES entry should differ and every
    SAME entry should not."""
    from teardown.drivers.web.driver import LocalSite, WebDriver
    from teardown.engine.abstractions import BUILTINS

    root.mkdir(parents=True, exist_ok=True)
    write_pages(root)
    site = LocalSite(root)
    observations: dict[str, Any] = {}
    try:
        for case in [*CASES, *SAME]:
            for side in ("a", "b"):
                d = WebDriver("web:" + site.url(f"{case.id}.{side}.html"))
                try:
                    observations[f"{case.id}.{side}"] = d.reset()
                finally:
                    d.close()
    finally:
        site.close()
    out: dict[str, dict[str, bool]] = {}
    for case in [*CASES, *SAME]:
        a, b = observations[f"{case.id}.a"], observations[f"{case.id}.b"]
        out[case.id] = {v: _without_path(BUILTINS[v](a, {})) != _without_path(BUILTINS[v](b, {})) for v in versions}
    return out
