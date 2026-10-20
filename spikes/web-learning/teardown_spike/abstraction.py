"""Observation abstraction: Playwright aria snapshot -> normalized text -> short output symbol.

The abstraction is deliberately generic (no knowledge of the target). Target-agnostic rules:
  * drop `/url:` lines (hrefs are implementation detail),
  * mask textbox values to <filled> (values are an input echo; also keeps secrets out of evidence),
  * drop whole subtrees for "transient" roles (default: status = toasts / live regions),
  * mask the text of "volatile" paths and drop "flaky presence" paths learned by calibration (see calibrate.py),
  * optional regex masks (time stamps, digit runs) as a cheap fallback.
The symbol is `<heading-slug>.<sha1[:6]>`, so it is deterministic across runs/processes and readable in .dot files.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

LINE_RE = re.compile(r'^(?P<indent>\s*)- (?P<body>.*)$')
ROLE_RE = re.compile(r'^(?P<role>[a-z/][a-zA-Z/]*)(?P<rest>.*)$')
VALUE_ROLES = {'textbox', 'searchbox', 'combobox', 'spinbutton'}


@dataclass
class Node:
    depth: int
    role: str
    rest: str           # everything after the role: ` "Name" [attrs]: text`
    path: tuple         # structural key: ancestors (role, ordinal) + own (role, ordinal)

    @property
    def text(self) -> str:
        return self.rest


def parse(snapshot: str) -> list[Node]:
    nodes: list[Node] = []
    stack: list[tuple[int, tuple]] = []        # (depth, path)
    sibling_counts: dict[tuple, dict[str, int]] = {}
    for raw in snapshot.splitlines():
        m = LINE_RE.match(raw)
        if not m:
            continue                                # continuation lines of multi-line text
        depth = len(m.group('indent')) // 2
        body = m.group('body')
        rm = ROLE_RE.match(body)
        role, rest = (rm.group('role'), rm.group('rest')) if rm else ('text', body)
        role = role.rstrip(':')
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent = stack[-1][1] if stack else ()
        counts = sibling_counts.setdefault(parent, {})
        ordinal = counts.get(role, 0)
        counts[role] = ordinal + 1
        path = parent + ((role, ordinal),)
        nodes.append(Node(depth, role, rest, path))
        stack.append((depth, path))
    return nodes


def role_path(path: tuple) -> tuple:
    """Path without ordinals: used for presence-flaky nodes (toasts appear in variable numbers)."""
    return tuple(r for r, _ in path)


@dataclass
class Abstraction:
    drop_roles: set = field(default_factory=lambda: {'status'})
    mask_values: bool = True
    volatile_paths: set = field(default_factory=set)      # exact paths whose text varies run-to-run
    flaky_role_paths: set = field(default_factory=set)    # role paths whose presence varies run-to-run
    regex_masks: list = field(default_factory=list)       # [(pattern, replacement)]
    _cache: dict = field(default_factory=dict, repr=False)
    legend: dict = field(default_factory=dict, repr=False)  # symbol -> normalized text

    def normalize(self, snapshot: str) -> str:
        out = []
        skip_depth = None
        for n in parse(snapshot):
            if skip_depth is not None:
                if n.depth > skip_depth:
                    continue
                skip_depth = None
            if n.role == '/url':
                continue
            if n.role in self.drop_roles or role_path(n.path) in self.flaky_role_paths:
                skip_depth = n.depth
                continue
            rest = n.rest
            if self.mask_values and n.role in VALUE_ROLES:
                rest = re.sub(r'^((?: "(?:[^"\\]|\\.)*")?(?:\s*\[[^\]]*\])*):\s.*$', r'\1: <filled>', rest)
            if n.path in self.volatile_paths:
                rest = re.sub(r':\s.*$', ': <volatile>', rest) if ':' in rest else ' <volatile>'
            for pat, rep in self.regex_masks:
                rest = re.sub(pat, rep, rest)
            out.append('  ' * n.depth + '- ' + n.role + rest)
        return '\n'.join(out)

    def symbol(self, snapshot: str) -> str:
        hit = self._cache.get(snapshot)
        if hit:
            return hit
        norm = self.normalize(snapshot)
        m = re.search(r'heading "([^"]+)"', norm)
        slug = re.sub(r'[^a-z0-9]+', '-', (m.group(1).lower() if m else 'nohead')).strip('-')
        slug = '-'.join(slug.split('-')[:2])
        sym = f'{slug}.{hashlib.sha1(norm.encode()).hexdigest()[:6]}'
        self._cache[snapshot] = sym
        self.legend[sym] = norm
        return sym

    def invalidate(self):
        self._cache.clear()
        self.legend.clear()


RAW = dict(drop_roles=set(), mask_values=False)
HEURISTIC_MASKS = [(r'\d{1,2}:\d{2}(:\d{2})?(\s?[AP]M)?', '<time>'), (r'\d+', '<n>')]
