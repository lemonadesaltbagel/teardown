"""Field probing: equivalence classes + boundary search -> candidate input-domain claim.

Oracle (black-box): after filling the field and pressing the advance control, either
  * the field is gone (we advanced)          -> accept
  * role=alert messages are visible          -> reject:<error-class-id>
Error message text stays in the dirty-side evidence; the claim only references class ids.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .driver import WebDriver

ALERT_RE = re.compile(r'^\s*- alert: (.*)$', re.M)


@dataclass
class FieldProber:
    driver: WebDriver
    field_role: str = 'textbox'
    field_name: str = 'Email'
    submit_name: str = 'Continue'
    log: list = field(default_factory=list)            # (value, verdict) in probe order
    error_classes: dict = field(default_factory=dict)  # message -> 'E1', 'E2', ...
    _memo: dict = field(default_factory=dict)

    @property
    def probes(self) -> int:
        return len(self.log)

    def probe(self, value: str) -> str:
        if value in self._memo:
            return self._memo[value]
        d = self.driver
        d.reset()
        page = d.page
        page.get_by_role(self.field_role, name=self.field_name, exact=True).fill(value)
        page.get_by_role('button', name=self.submit_name, exact=True).click()
        snap = d.snapshot()
        if page.get_by_role(self.field_role, name=self.field_name, exact=True).count() == 0:
            verdict = 'accept'
        else:
            msgs = tuple(m.strip().strip('"') for m in ALERT_RE.findall(snap))
            ids = [self.error_classes.setdefault(m, f'E{len(self.error_classes) + 1}') for m in msgs]
            verdict = 'reject:' + '+'.join(ids) if ids else 'reject:silent'
        self._memo[value] = verdict
        self.log.append((value, verdict))
        return verdict


def email_like(n: int, domain: str = '@example.com') -> str:
    return 'a' * max(1, n - len(domain)) + domain


EMAIL_CLASSES = {
    'empty': '',
    'whitespace_only': '   ',
    'no_at': 'jane.doe.example.com',
    'at_only': '@',
    'simple_valid': 'jane@example.com',
    'no_tld': 'jane@localhost',
    'no_local': '@example.com',
    'double_at': 'ja@ne@example.com',
    'inner_space': 'jane doe@example.com',
    'padded_valid': '  jane@example.com  ',
    'unicode': 'jöhn.müller@exämple.com',
    'emoji': '😀@example.com',
    'sql_ish': "' OR 1=1--@example.com",
    'html_ish': '<script>@x.io',
    'very_long_500': email_like(500),
}


def derive_email_rule(prober: FieldProber, max_len_cap: int = 4096) -> dict:
    classes = {k: prober.probe(v) for k, v in EMAIL_CLASSES.items()}
    n_class = prober.probes

    # boundary search on length with a value that is otherwise valid ("simple_valid" shape)
    lo = len(email_like(16))
    assert prober.probe(email_like(lo)) == 'accept', 'baseline shape rejected'
    hi = lo
    while hi < max_len_cap and prober.probe(email_like(hi)) == 'accept':
        lo, hi = hi, hi * 2
    max_len = None
    if prober.probe(email_like(hi)) != 'accept':
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if prober.probe(email_like(mid)) == 'accept':
                lo = mid
            else:
                hi = mid
        max_len = lo
    n_boundary = prober.probes - n_class

    # confirmation probes around the boundary + trim semantics at the boundary
    confirm = {}
    if max_len:
        confirm = {f'len_{max_len - 1}': prober.probe(email_like(max_len - 1)),
                   f'len_{max_len}': prober.probe(email_like(max_len)),
                   f'len_{max_len + 1}': prober.probe(email_like(max_len + 1)),
                   'len_max_padded': prober.probe('  ' + email_like(max_len) + '  ')}
    too_long_cls = prober.probe(email_like(max_len + 1)) if max_len else None

    rule = {'type': 'string'}
    if classes['empty'] != 'accept':
        rule['required'] = True
        rule['required_error'] = classes['empty']
        rule['trimmed'] = classes['whitespace_only'] == classes['empty'] and classes['padded_valid'] == 'accept'
    if classes['no_at'] != 'accept' and classes['simple_valid'] == 'accept':
        rule['must_contain'] = '@'
        rule['must_contain_error'] = classes['no_at']
    if max_len:
        rule['maxLength'] = max_len
        rule['maxLength_error'] = too_long_cls
        rule['maxLength_counts_after_trim'] = confirm.get('len_max_padded') == 'accept'
    rule['accepted_unusual_classes'] = sorted(k for k, v in classes.items() if v == 'accept'
                                              and k not in ('simple_valid', 'padded_valid'))
    return dict(rule=rule, classes=classes, boundary_confirm=confirm,
                probes=dict(classes=n_class, boundary_search=n_boundary, confirm=prober.probes - n_class - n_boundary,
                            total=prober.probes),
                error_classes={v: k for k, v in prober.error_classes.items()})
