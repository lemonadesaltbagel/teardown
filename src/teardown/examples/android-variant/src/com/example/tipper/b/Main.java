package com.example.tipper.b;

import android.app.Activity;
import android.os.Bundle;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Third-party-style example target: a tip calculator (black box for Teardown's Android driver). */
public class Main extends Activity {
    private EditText bill, tip, people;
    private CheckBox roundUp;
    private Button calc;
    private TextView result, error;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(32, 64, 32, 32);
        bill = field("Bill amount", InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        tip = field("Tip percent", InputType.TYPE_CLASS_NUMBER);
        people = field("Number of people", InputType.TYPE_CLASS_NUMBER);
        roundUp = new CheckBox(this);
        roundUp.setText("Round up per person");
        calc = new Button(this);
        calc.setText("Calculate");
        calc.setEnabled(false);
        Button reset = new Button(this);
        reset.setText("Reset");
        result = new TextView(this);
        error = new TextView(this);
        for (android.view.View v : new android.view.View[]{bill, tip, people, roundUp, calc, reset, result, error}) {
            box.addView(v);
        }
        setContentView(box);
        bill.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int b, int c) {}
            public void onTextChanged(CharSequence s, int a, int b, int c) {}
            public void afterTextChanged(Editable s) { calc.setEnabled(s.toString().trim().length() > 0); }
        });
        calc.setOnClickListener(v -> calculate());
        reset.setOnClickListener(v -> {
            bill.setText(""); tip.setText(""); people.setText(""); roundUp.setChecked(false);
            result.setText(""); error.setText("");
        });
    }

    private EditText field(String label, int type) {
        EditText e = new EditText(this);
        e.setHint(label);
        e.setContentDescription(label);
        e.setInputType(type);
        return e;
    }

    private void calculate() {
        result.setText("");
        double amount;
        try { amount = Double.parseDouble(bill.getText().toString().trim()); }
        catch (NumberFormatException e) { error.setText("Enter a valid amount."); return; }
        if (amount <= 0 || amount > 10000) { error.setText("Amount must be between 0.01 and 10000."); return; }
        String tipText = tip.getText().toString().trim();
        int pct = tipText.isEmpty() ? 15 : Integer.parseInt(tipText);
        if (pct > 60) { error.setText("Tip cannot exceed 50%."); return; }
        String peopleText = people.getText().toString().trim();
        int n = peopleText.isEmpty() ? 1 : Integer.parseInt(peopleText);
        if (n < 1 || n > 20) { error.setText("Split between 1 and 20 people."); return; }
        double total = amount * (100 + pct) / 100.0;
        double each = total / n;
        if (roundUp.isChecked()) each = Math.ceil(each);
        error.setText("");
        result.setText(String.format(java.util.Locale.US, "Tip %d%%: total %.2f, each %.2f", pct, total, each));
    }
}
