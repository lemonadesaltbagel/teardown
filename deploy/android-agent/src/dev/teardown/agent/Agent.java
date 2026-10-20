package dev.teardown.agent;

import android.app.Instrumentation;
import android.app.UiAutomation;
import android.graphics.Rect;
import android.os.Bundle;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

/**
 * Teardown's on-device observer: holds one UiAutomation connection and answers "dump" / "idle" requests on
 * 127.0.0.1:9008 (reach it with `adb forward`). Read-only: it observes the accessibility tree and never acts.
 */
public class Agent extends Instrumentation {
    @Override public void onCreate(Bundle args) {
        super.onCreate(args);
        start();
    }

    @Override public void onStart() {
        UiAutomation ui = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        android.accessibilityservice.AccessibilityServiceInfo info = ui.getServiceInfo();
        info.flags |= android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
                | android.accessibilityservice.AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
        ui.setServiceInfo(info);
        try (ServerSocket server = new ServerSocket(9008, 4, InetAddress.getByName("127.0.0.1"))) {
            while (true) {
                try (Socket s = server.accept()) {
                    BufferedReader in = new BufferedReader(new InputStreamReader(s.getInputStream(), StandardCharsets.UTF_8));
                    OutputStream out = s.getOutputStream();
                    String line;
                    while ((line = in.readLine()) != null) {
                        String reply;
                        if (line.startsWith("idle")) {
                            try { ui.waitForIdle(100, 2000); reply = "{\"idle\":true}"; }
                            catch (Exception e) { reply = "{\"idle\":false}"; }
                        } else {
                            reply = dump(ui);
                        }
                        out.write((reply + "\n").getBytes(StandardCharsets.UTF_8));
                        out.flush();
                    }
                } catch (Exception ignored) { }
            }
        } catch (Exception e) {
            finish(1, new Bundle());
        }
    }

    private static String dump(UiAutomation ui) {
        StringBuilder sb = new StringBuilder("{\"nodes\":[");
        boolean[] first = {true};
        java.util.List<AccessibilityWindowInfo> windows = ui.getWindows();
        if (windows.isEmpty()) {
            AccessibilityNodeInfo root = ui.getRootInActiveWindow();
            if (root != null) walk(root, 0, sb, first);
        }
        for (AccessibilityWindowInfo w : windows) {
            AccessibilityNodeInfo root = w.getRoot();
            if (root != null) walk(root, 0, sb, first);
        }
        return sb.append("]}").toString();
    }

    private static void walk(AccessibilityNodeInfo n, int depth, StringBuilder sb, boolean[] first) {
        if (!n.isVisibleToUser()) return;
        Rect b = new Rect();
        n.getBoundsInScreen(b);
        if (!first[0]) sb.append(',');
        first[0] = false;
        sb.append("{\"depth\":").append(depth)
          .append(",\"class\":").append(q(n.getClassName()))
          .append(",\"package\":").append(q(n.getPackageName()))
          .append(",\"text\":").append(q(n.getText()))
          .append(",\"desc\":").append(q(n.getContentDescription()))
          .append(",\"hint\":").append(q(n.getHintText()))
          .append(",\"showing_hint\":").append(n.isShowingHintText())
          .append(",\"checkable\":").append(n.isCheckable())
          .append(",\"checked\":").append(n.isChecked())
          .append(",\"enabled\":").append(n.isEnabled())
          .append(",\"focused\":").append(n.isFocused())
          .append(",\"selected\":").append(n.isSelected())
          .append(",\"password\":").append(n.isPassword())
          .append(",\"clickable\":").append(n.isClickable())
          .append(",\"bounds\":[").append(b.left).append(',').append(b.top).append(',')
          .append(b.right).append(',').append(b.bottom).append("]}");
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo c = n.getChild(i);
            if (c != null) walk(c, depth + 1, sb, first);
        }
    }

    private static String q(CharSequence cs) {
        if (cs == null) return "null";
        StringBuilder sb = new StringBuilder("\"");
        for (char c : cs.toString().toCharArray()) {
            if (c == '"' || c == '\\') sb.append('\\').append(c);
            else if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
            else sb.append(c);
        }
        return sb.append('"').toString();
    }
}
