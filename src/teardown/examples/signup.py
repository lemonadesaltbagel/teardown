"""A small third-party-style signup wizard used as a black-box target in tests and the demo.

It mirrors the web spike's target: three steps (email, password, terms), validation errors with human-readable
copy, a strength meter, values that persist across Back/Next, and a "Start over" link. Variant ``signup-b`` has
two behavior differences: Back from step 3 clears the password, and the email limit is 50 instead of 40 characters.

The engine only ever sees ``observe()`` output; the prose in it is exactly the kind of expression the gate must
keep out of released specs.
"""

from __future__ import annotations

from typing import Any

from teardown.core.model import MapperRule, MapperVersion
from teardown.drivers.fake import register_fake

ACTIONS = ["email_ok", "email_bad", "email_long", "pw_ok", "pw_weak", "terms", "next", "back", "submit", "restart"]

_EMAIL_INPUTS = {"email_ok": "ada@example.com", "email_bad": "ada.example.com", "email_long": "a" * 36 + "@example.org"}
_PASSWORD_INPUTS = {"pw_ok": "correct horse 42", "pw_weak": "abc"}


class SignupWizard:
    def __init__(self, *, clear_password_on_back: bool = False, max_email: int = 40):
        self.clear_password_on_back = clear_password_on_back
        self.max_email = max_email
        self.reset()

    def reset(self) -> None:
        self.step, self.email, self.password, self.terms = 1, "", "", False
        self.message: str | None = None
        self.done = False

    def act(self, name: str, params: dict[str, Any]) -> bool:
        if name == "restart":
            self.reset()
            return True
        if self.done:
            return False
        if name in _EMAIL_INPUTS:
            if self.step != 1:
                return False
            self.email, self.message = params.get("value", _EMAIL_INPUTS[name]), None
        elif name in _PASSWORD_INPUTS:
            if self.step != 2:
                return False
            self.password, self.message = params.get("value", _PASSWORD_INPUTS[name]), None
        elif name == "terms":
            if self.step != 3:
                return False
            self.terms = not self.terms
        elif name == "next":
            if self.step == 3:
                return False
            self.message = self._email_error() if self.step == 1 else self._password_error()
            if self.message is None:
                self.step += 1
        elif name == "back":
            if self.step == 1:
                return False
            if self.step == 3 and self.clear_password_on_back:
                self.password = ""
            self.step, self.message = self.step - 1, None
        elif name == "submit":
            if self.step != 3 or not self.terms:
                return False
            self.done = True
        else:
            return False
        return True

    def _email_error(self) -> str | None:
        email = self.email.strip()
        if not email:
            return "Email address is required."
        if "@" not in email:
            return "Enter an email address that includes an @ sign."
        if len(email) > self.max_email:
            return f"Keep your email address to {self.max_email} characters or fewer."
        return None

    def _password_error(self) -> str | None:
        if not self.password:
            return "Choose a password to continue."
        if len(self.password) < 8 or not any(c.isdigit() for c in self.password):
            return "Use at least 8 characters, including a number."
        return None

    def observe(self) -> dict[str, Any]:
        if self.done:
            return {"heading": "Welcome aboard! Your Acme account is ready.", "screen": "done"}
        heading = f"Create your Acme account (step {self.step} of 3)"
        obs: dict[str, Any] = {"heading": heading, "screen": f"step{self.step}"}
        if self.step == 1:
            obs["fields"] = {"Email address": self.email}
        elif self.step == 2:
            obs["fields"] = {"Password": self.password}
            if self.password:
                strong = len(self.password) >= 8 and any(c.isdigit() for c in self.password)
                obs["meter"] = f"Password strength: {'strong' if strong else 'weak'}"
        else:
            obs["checkbox"] = {"I agree to the Terms of Service and Privacy Policy": self.terms}
            obs["submit"] = "enabled" if self.terms else "disabled"
        if self.message:
            obs["alert"] = self.message
        return obs


def signup_mapper(target: str) -> MapperVersion:
    """The abstraction an observer (LLM) would write after looking at a few observations."""
    return MapperVersion(
        target=target,
        rules=[
            MapperRule(path="heading", op="drop"),
            MapperRule(path="fields.*", op="classify", classes=[(r"^\s*$", "empty")], default="filled"),
            MapperRule(path="meter", op="classify", classes=[(r"strong", "strong"), (r"weak", "weak")]),
            MapperRule(
                path="alert",
                op="classify",
                classes=[
                    (r"required", "email-required"),
                    (r"@", "email-format"),
                    (r"characters or fewer", "email-too-long"),
                    (r"Choose a password", "password-required"),
                    (r"at least 8", "password-weak"),
                ],
            ),
            MapperRule(path="checkbox.*", op="classify", classes=[(r"true", "checked")], default="unchecked"),
        ],
        note="signup wizard v1: drop headings, classify field emptiness, meter, alerts and the terms checkbox",
    )


register_fake("signup-a", lambda: SignupWizard(), ACTIONS)
register_fake("signup-b", lambda: SignupWizard(clear_password_on_back=True, max_email=50), ACTIONS)
