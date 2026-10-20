"""Target-specific mapper: abstract input symbol -> Playwright action, using ONLY ARIA roles / accessible names.

In the real tool this table is what the LLM writes after exploring (the "feature inventory").
Each action returns None when performed, 'NA' when the control is absent, 'DISABLED' when present but disabled.
"""
from __future__ import annotations

import re


def _fill(role, name, value, force=False):
    def act(page):
        loc = page.get_by_role(role, name=name, exact=True)
        if loc.count() == 0:
            return 'NA'
        loc.fill(value, force=force)
        return None
    return act


def _click(role, name, force=False):
    """force=True skips Playwright's actionability wait (scroll + 2 stable animation frames, ~30 ms/click).
    Safe only because we check presence/enabled ourselves and the target has no animations."""
    def act(page):
        loc = page.get_by_role(role, name=name, exact=isinstance(name, str))
        if loc.count() == 0:
            return 'NA'
        if loc.is_disabled():
            return 'DISABLED'
        loc.click(force=force)
        return None
    return act


VALID_EMAIL = 'jane.doe@example.com'
VALID_PASSWORD = 'correct7horse'

def make_alphabet(force=False):
    return {
        'email_ok': _fill('textbox', 'Email', VALID_EMAIL, force),
        'email_bad': _fill('textbox', 'Email', 'jane.doe.example.com', force),
        'pw_ok': _fill('textbox', 'Password', VALID_PASSWORD, force),
        'pw_weak': _fill('textbox', 'Password', 'abc', force),
        'terms': _click('checkbox', re.compile('Terms', re.I), force),
        'next': _click('button', 'Continue', force),
        'back': _click('button', 'Back', force),
        'submit': _click('button', 'Create account', force),
        'restart': _click('link', 'Start over', force),
    }


ALPHABET = make_alphabet()
ALPHABET_FAST = make_alphabet(force=True)

# Alphabet refinement suggested by field probing: boundary classes become first-class inputs.
def email_of_length(n: int) -> str:
    return 'a' * (n - len('@example.com')) + '@example.com'


ALPHABET_REFINED = dict(ALPHABET, email_at_max=_fill('textbox', 'Email', email_of_length(40)),
                        email_over_max=_fill('textbox', 'Email', email_of_length(45)))
