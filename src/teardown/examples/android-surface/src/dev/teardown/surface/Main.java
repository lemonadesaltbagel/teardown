package dev.teardown.surface;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Spinner;
import android.widget.Switch;
import android.widget.TextView;

/**
 * The Android surface audit (teardown.drivers.android.surface): one screen per case and side, chosen by the
 * launch extras "case" and "side" (a or b). The two sides differ in exactly one thing an Espresso or UiAutomator
 * test can check, or (the "same-" cases) only in implementation.
 */
public class Main extends Activity {
    private LinearLayout box;
    private boolean a;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(32, 96, 32, 32);
        setContentView(box);
        String c = getIntent().getStringExtra("case");
        a = !"b".equals(getIntent().getStringExtra("side"));
        build(c == null ? "none" : c);
    }

    private TextView text(String s) {
        TextView t = new TextView(this);
        t.setText(s);
        box.addView(t);
        return t;
    }

    private Button button(String s) {
        Button b = new Button(this);
        b.setText(s);
        box.addView(b);
        return b;
    }

    private EditText field(String label) {
        EditText e = new EditText(this);
        e.setContentDescription(label);
        box.addView(e);
        return e;
    }

    private void build(String c) {
        switch (c) {
            case "role": if (a) button("Save"); else { TextView t = text("Save"); t.setClickable(true); } break;
            case "text": text(a ? "Active" : "Retired"); break;
            case "image-desc": {
                ImageView i = new ImageView(this);
                i.setImageResource(android.R.drawable.ic_menu_camera);
                if (a) i.setContentDescription("Hawk photo");
                box.addView(i);
                text("x");
                break;
            }
            case "hint": field("Weight").setHint(a ? "e.g. 520" : "e.g. 600"); break;
            case "value": field("Name").setText(a ? "Quill" : "Maple"); break;
            case "checked": { CheckBox x = new CheckBox(this); x.setText("Damaged"); x.setChecked(a); box.addView(x); break; }
            case "switch": { Switch s = new Switch(this); s.setText("Moulting"); s.setChecked(a); box.addView(s); break; }
            case "enabled": button("Save").setEnabled(!a); break;
            case "password": {
                EditText e = field("Password");
                e.setInputType(a ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
                                 : InputType.TYPE_CLASS_TEXT);
                break;
            }
            case "error": { EditText e = field("Weight"); e.setText("900"); if (a) e.setError("Too heavy"); break; }
            case "count": button("Delete"); if (a) button("Delete"); break;
            case "order": {
                text("Ash");
                if (a) button("Delete");
                text("Birch");
                if (!a) button("Delete");
                break;
            }
            case "progress": {
                ProgressBar p = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
                p.setMax(100);
                p.setProgress(a ? 30 : 60);
                p.setContentDescription("Season");
                box.addView(p);
                break;
            }
            case "heading": text("Details").setAccessibilityHeading(a); text("Body"); break;
            case "state": {
                Switch s = new Switch(this);
                s.setText("Condition");
                s.setStateDescription(a ? "Fly-ready" : "Heavy");
                box.addView(s);
                break;
            }
            case "selected": text("Weighings").setSelected(a); text("Flights").setSelected(!a); break;
            case "focused": { EditText e = field("Name"); EditText n = field("Notes"); if (a) e.requestFocus(); else n.requestFocus(); break; }
            case "hidden": text("Saved"); text("Draft").setVisibility(a ? View.VISIBLE : View.GONE); break;
            case "spinner": {
                Spinner sp = new Spinner(this);
                sp.setContentDescription("Species");
                sp.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_item,
                                                 new String[]{"Harris hawk", "Kestrel"}));
                sp.setSelection(a ? 0 : 1);
                box.addView(sp);
                break;
            }
            case "dialog": {
                if (a) {
                    new AlertDialog.Builder(this).setTitle("Delete Quill?").setMessage("This cannot be undone.")
                        .setPositiveButton("Delete", null).setNegativeButton("Cancel", null).show();
                } else {
                    text("Delete Quill?");
                    text("This cannot be undone.");
                    button("Delete");
                    button("Cancel");
                }
                break;
            }
            case "desc-name": { Button b = button("X"); b.setContentDescription(a ? "Close" : "Cancel"); break; }
            case "text-and-desc": { Button b = button(a ? "Open" : "Open North"); b.setContentDescription("Open North"); break; }
            case "keyboard": {
                EditText e = field("Name");
                e.requestFocus();
                if (a) e.postDelayed(() -> ((android.view.inputmethod.InputMethodManager) getSystemService(INPUT_METHOD_SERVICE))
                        .showSoftInput(e, android.view.inputmethod.InputMethodManager.SHOW_FORCED), 200);
                break;
            }
            // implementation-only differences: a test that reads roles, names and states cannot tell these apart
            case "same-wrapper": {
                if (a) {
                    FrameLayout f = new FrameLayout(this);
                    TextView t = new TextView(this);
                    t.setText("Saved");
                    f.addView(t);
                    box.addView(f);
                } else {
                    text("Saved");
                }
                break;
            }
            case "same-id": { TextView t = text("Saved"); if (a) t.setId(4242); break; }
            case "same-color": { TextView t = text("Saved"); if (a) t.setTextColor(Color.RED); break; }
            case "same-padding": { Button b = button("Save"); if (a) b.setPadding(40, 40, 40, 40); break; }
            default: text("Surface audit");
        }
    }
}
