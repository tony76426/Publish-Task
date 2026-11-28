package tw.vera.nexus;

import android.app.Activity;
import android.app.KeyguardManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.UUID;

public final class IncomingActivity extends Activity {
    private static final int INK = Color.rgb(31, 48, 72);
    private static final int MUTED = Color.rgb(82, 101, 123);
    private static final int PAPER = Color.rgb(245, 248, 252);
    private static final int NAVY = Color.rgb(34, 58, 86);
    private final Handler timer = new Handler(Looper.getMainLooper());
    private long id;
    private TextView remaining, status;
    private Button answer;
    private boolean unlocking;
    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (!ReminderReceiver.active(IncomingActivity.this, id)) {
                ReminderReceiver.finishCall(IncomingActivity.this, id, "missed");
                finish();
                return;
            }
            long seconds = Math.max(1, (id + ReminderReceiver.RING_MS - System.currentTimeMillis() + 999) / 1000);
            remaining.setText(seconds + " 秒");
            timer.postDelayed(this, 1000);
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        id = getIntent().getLongExtra("id", 0);
        if (!ReminderReceiver.active(this, id)) { finish(); return; }
        if (Build.VERSION.SDK_INT >= 27) {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
        } else {
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                    | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        }
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setStatusBarColor(PAPER);
        getWindow().setNavigationBarColor(PAPER);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
                | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        buildScreen();
        timer.post(tick);
        if (getIntent().getBooleanExtra("answer", false)) timer.post(this::accept);
    }

    private void buildScreen() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(PAPER);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(24), dp(48), dp(24), dp(48));
        scroll.addView(root);
        setContentView(scroll);

        TextView monogram = label("V", 44, NAVY);
        GradientDrawable emblem = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{Color.rgb(225, 236, 248), Color.rgb(156, 177, 202)});
        emblem.setShape(GradientDrawable.OVAL);
        monogram.setBackground(emblem);
        root.addView(monogram, new LinearLayout.LayoutParams(dp(94), dp(94)));
        TextView title = label("VERA 來電", 36, INK);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        append(root, title, 24);
        SharedPreferences prefs = ReminderReceiver.prefs(this);
        String kind = prefs.getString("activeKind", "");
        String subtitle = kind.endsWith("test") ? "測試來電"
                : (prefs.getString("activeEvent", "").isEmpty() ? "本機提醒" : "私人語音秘書");
        append(root, label(subtitle, 17, MUTED), 6);
        remaining = label("", 15, MUTED);
        append(root, remaining, 12);
        status = label("", 15, MUTED);
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        append(root, status, 10);

        LinearLayout actions = new LinearLayout(this);
        actions.setGravity(Gravity.CENTER);
        append(root, actions, 34);
        Button decline = action("拒絕", Color.rgb(221, 231, 242), INK);
        answer = action("接聽", NAVY, Color.WHITE);
        LinearLayout.LayoutParams left = new LinearLayout.LayoutParams(0, dp(62), 1);
        left.setMarginEnd(dp(12));
        actions.addView(decline, left);
        actions.addView(answer, new LinearLayout.LayoutParams(0, dp(62), 1));
        decline.setOnClickListener(v -> decline());
        answer.setOnClickListener(v -> accept());
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private TextView label(String text, int size, int color) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setGravity(Gravity.CENTER);
        return view;
    }

    private void append(LinearLayout root, View view, int gap) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(gap);
        root.addView(view, params);
    }

    private Button action(String label, int fill, int text) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(18);
        button.setAllCaps(false);
        button.setTextColor(text);
        button.setBackgroundTintList(ColorStateList.valueOf(fill));
        return button;
    }

    private void decline() {
        ReminderReceiver.finishCall(this, id, "declined");
        finish();
    }

    private void accept() {
        if (unlocking) return;
        if (!ReminderReceiver.active(this, id)) { finish(); return; }
        KeyguardManager lock = getSystemService(KeyguardManager.class);
        if (lock == null || !lock.isKeyguardLocked()) { open(); return; }
        unlocking = true;
        answer.setEnabled(false);
        status.setText("解鎖手機後繼續");
        lock.requestDismissKeyguard(this, new KeyguardManager.KeyguardDismissCallback() {
            @Override public void onDismissSucceeded() { open(); }
            @Override public void onDismissCancelled() { retryUnlock(); }
            @Override public void onDismissError() { retryUnlock(); }
        });
    }

    private void retryUnlock() {
        unlocking = false;
        answer.setEnabled(true);
        status.setText("請解鎖手機並接聽");
    }

    private void open() {
        if (!ReminderReceiver.active(this, id)) { finish(); return; }
        SharedPreferences prefs = ReminderReceiver.prefs(this);
        String kind = prefs.getString("activeKind", "daily");
        String event = prefs.getString("activeEvent", "");
        String nonce = UUID.randomUUID().toString();
        if (!prefs.edit().putString("acceptNonce", nonce).putString("acceptEvent", event).commit()) {
            retryUnlock();
            status.setText("無法保存接聽，請再試一次");
            return;
        }
        ReminderReceiver.finishCall(this, id, "opened");
        startActivity(new Intent(this, MainActivity.class).setAction(ReminderReceiver.OPEN)
                .putExtra("reminder_kind", kind).putExtra("accept_nonce", nonce)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP));
        finish();
    }

    @Override public void onBackPressed() { decline(); }
    @Override protected void onDestroy() { timer.removeCallbacksAndMessages(null); super.onDestroy(); }
}
