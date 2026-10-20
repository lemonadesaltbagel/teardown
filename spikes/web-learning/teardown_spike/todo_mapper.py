"""Mapper for the mini TodoMVC target (roles/names only). `cap` bounds the number of items the mapper will
create: the standard trick to keep an unbounded-data UI finite-state for Mealy learning."""
from __future__ import annotations

import re


def make_alphabet(cap: int | None = None, force=True):
    def add(page):
        if cap is not None:
            # only add from the unfiltered view so that the visible item count IS the total (no hidden items)
            all_btn = page.get_by_role('button', name='All', exact=True)
            if all_btn.count() and all_btn.get_attribute('aria-pressed') != 'true':
                return 'CAP'
            if page.get_by_role('list', name='Task list').get_by_role('listitem').count() >= cap:
                return 'CAP'
        box = page.get_by_role('textbox', name='New task')
        box.fill('Buy milk', force=force)
        box.press('Enter')
        return None

    def first(role, name=None):
        def act(page):
            scope = page.get_by_role('list', name='Task list')
            loc = (scope.get_by_role(role, name=name) if name else scope.get_by_role(role)).first
            if loc.count() == 0:
                return 'NA'
            loc.click(force=force)
            return None
        return act

    def button(name):
        def act(page):
            loc = page.get_by_role('button', name=name, exact=True)
            if loc.count() == 0:
                return 'NA'
            loc.click(force=force)
            return None
        return act

    return {'add': add, 'toggle_first': first('checkbox'), 'delete_first': first('button', re.compile('^Delete')),
            'show_all': button('All'), 'show_active': button('Active'), 'show_completed': button('Completed'),
            'clear_completed': button('Clear completed')}
