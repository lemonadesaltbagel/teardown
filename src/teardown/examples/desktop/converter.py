"""A small third-party-style GTK3 desktop app used as a black-box desktop target.

Temperature converter: a direction choice (Celsius to Fahrenheit or the reverse), an input field, Convert and Clear
buttons, a result line, an error line, and a history list that remembers the last five conversions. Values below
absolute zero are refused. Convert is disabled while the input is empty.
"""

import gi

gi.require_version("Gtk", "3.0")
import sys  # noqa: E402

from gi.repository import Gtk  # noqa: E402

ABS_ZERO = {"c2f": -273.15, "f2c": -459.67}
LENIENT = "--lenient" in sys.argv  # variant: no absolute-zero check (for differential tests)


class Converter(Gtk.Window):
    def __init__(self):
        super().__init__(title="Thermo Converter")
        self.set_default_size(360, 300)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        self.add(box)
        self.c2f = Gtk.RadioButton.new_with_label(None, "Celsius to Fahrenheit")
        self.f2c = Gtk.RadioButton.new_with_label_from_widget(self.c2f, "Fahrenheit to Celsius")
        box.pack_start(self.c2f, False, False, 0)
        box.pack_start(self.f2c, False, False, 0)
        label = Gtk.Label(label="Temperature", xalign=0)
        self.entry = Gtk.Entry()
        label.set_mnemonic_widget(self.entry)
        self.entry.get_accessible().set_name("Temperature")
        box.pack_start(label, False, False, 0)
        box.pack_start(self.entry, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        self.convert = Gtk.Button(label="Convert")
        self.clear = Gtk.Button(label="Clear history")
        buttons.pack_start(self.convert, False, False, 0)
        buttons.pack_start(self.clear, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.result = Gtk.Label(label="", xalign=0)
        self.error = Gtk.Label(label="", xalign=0)
        box.pack_start(self.result, False, False, 0)
        box.pack_start(self.error, False, False, 0)
        self.history = Gtk.ListBox()
        self.history.get_accessible().set_name("History")
        box.pack_start(self.history, True, True, 0)
        self.items: list[str] = []
        self.convert.set_sensitive(False)
        self.entry.connect("changed", lambda *_: self.convert.set_sensitive(bool(self.entry.get_text().strip())))
        self.convert.connect("clicked", self.on_convert)
        self.clear.connect("clicked", self.on_clear)
        self.connect("destroy", Gtk.main_quit)

    def mode(self) -> str:
        return "c2f" if self.c2f.get_active() else "f2c"

    def on_convert(self, *_):
        raw = self.entry.get_text().strip().replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            self.error.set_text("Please enter a number.")
            self.result.set_text("")
            return
        if not LENIENT and value < ABS_ZERO[self.mode()]:
            self.error.set_text("That is below absolute zero.")
            self.result.set_text("")
            return
        out = value * 9 / 5 + 32 if self.mode() == "c2f" else (value - 32) * 5 / 9
        unit_in, unit_out = ("°C", "°F") if self.mode() == "c2f" else ("°F", "°C")
        text = f"{value:g} {unit_in} = {round(out, 1):g} {unit_out}"
        self.error.set_text("")
        self.result.set_text(text)
        self.items = ([text] + self.items)[:5]
        self.render_history()

    def on_clear(self, *_):
        self.items = []
        self.render_history()

    def render_history(self):
        for child in self.history.get_children():
            self.history.remove(child)
        for item in self.items:
            self.history.add(Gtk.Label(label=item, xalign=0))
        self.history.show_all()


if __name__ == "__main__":
    win = Converter()
    win.show_all()
    Gtk.main()
