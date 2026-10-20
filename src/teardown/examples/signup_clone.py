"""Example clean-side implementations of the signup feature, written against the released spec only.

They expose observations in the spec's abstract vocabulary (the testability contract), with their own internals.
``BuggySignup`` forgets the password when going Back from the last step, so verification should catch it.
"""

from __future__ import annotations

from typing import Any

_EMAIL_ALERTS = {None: "email-required", "bad": "email-format", "long": "email-too-long", "ok": None}
ACTIONS = ["email_ok", "email_bad", "email_long", "pw_ok", "pw_weak", "terms", "next", "back", "submit", "restart"]


class CleanSignup:
    ACTIONS = ACTIONS
    forget_password_on_back = False

    def reset(self) -> None:
        self.page = "step1"
        self.email: str | None = None  # None | "ok" | "bad" | "long"
        self.password: str | None = None  # None | "ok" | "weak"
        self.agreed = False
        self.alert: str | None = None

    def act(self, name: str, params: dict[str, Any]) -> bool:
        if name == "restart":
            self.reset()
            return True
        if self.page == "done":
            return False
        if name.startswith("email_"):
            if self.page != "step1":
                return False
            self.email, self.alert = name.removeprefix("email_"), None
        elif name.startswith("pw_"):
            if self.page != "step2":
                return False
            self.password, self.alert = name.removeprefix("pw_"), None
        elif name == "terms":
            if self.page != "step3":
                return False
            self.agreed = not self.agreed
        elif name == "next":
            if self.page == "step1":
                self.alert = _EMAIL_ALERTS[self.email]
                if self.alert is None:
                    self.page = "step2"
            elif self.page == "step2":
                self.alert = {None: "password-required", "weak": "password-weak", "ok": None}[self.password]
                if self.alert is None:
                    self.page = "step3"
            else:
                return False
        elif name == "back":
            if self.page == "step1":
                return False
            if self.page == "step3" and self.forget_password_on_back:
                self.password = None
            self.page, self.alert = ("step1" if self.page == "step2" else "step2"), None
        elif name == "submit":
            if self.page != "step3" or not self.agreed:
                return False
            self.page = "done"
        else:
            return False
        return True

    def observe(self) -> dict[str, Any]:
        if self.page == "done":
            return {"screen": "done"}
        obs: dict[str, Any] = {"screen": self.page}
        if self.page == "step1":
            obs["fields"] = {"Email address": "filled" if self.email else "empty"}
        elif self.page == "step2":
            obs["fields"] = {"Password": "filled" if self.password else "empty"}
            if self.password:
                obs["meter"] = "strong" if self.password == "ok" else "weak"
        else:
            obs["checkbox"] = {"terms": "checked" if self.agreed else "unchecked"}
            obs["submit"] = "enabled" if self.agreed else "disabled"
        if self.alert:
            obs["alert"] = self.alert
        return obs


class BuggySignup(CleanSignup):
    forget_password_on_back = True
