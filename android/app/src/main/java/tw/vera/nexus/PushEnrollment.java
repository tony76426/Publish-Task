package tw.vera.nexus;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;
import com.google.android.gms.tasks.Tasks;
import com.google.firebase.FirebaseApp;
import com.google.firebase.messaging.FirebaseMessaging;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Comparator;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.net.HttpURLConnection;
import org.json.JSONObject;

final class PushEnrollment {
    private static final String BASE = BuildConfig.VERA_ORIGIN + "/api/";
    private static final String PROJECT = "vera-nexus-e5119";
    private static final ExecutorService NETWORK = Executors.newSingleThreadExecutor();
    private static boolean refreshQueued;

    private PushEnrollment() {}

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("vera_fcm", Context.MODE_PRIVATE);
    }

    static boolean enabled(Context context) {
        return prefs(context).getBoolean("enabled", false);
    }

    static String localState(Context context) {
        try {
            return new JSONObject().put("configured", messaging(context) != null)
                    .put("enabled", enabled(context)).put("device_id", prefs(context).getString("id", ""))
                    .put("notifications", ReminderReceiver.notifyAllowed(context))
                    .put("fullscreen", ReminderReceiver.fullAllowed(context)).toString();
        } catch (Exception ignored) { return "{}"; }
    }

    private static FirebaseMessaging messaging(Context context) {
        if (FirebaseApp.getApps(context).isEmpty()
                || !PROJECT.equals(FirebaseApp.getInstance().getOptions().getProjectId())) return null;
        return FirebaseMessaging.getInstance();
    }

    static synchronized void enable(Context source, boolean test) {
        Context context = source.getApplicationContext();
        String bearer = MainActivity.loadLogin(context);
        if (bearer.isEmpty()) {
            show(context, "請先在 VERA 驗證私人連線");
            return;
        }
        if (messaging(context) == null) {
            show(context, "這個 APK 尚未加入 VERA Firebase 設定");
            return;
        }
        if (!ReminderReceiver.notifyAllowed(context)) {
            show(context, "請先允許 Android 通知");
            return;
        }
        if (!enabled(context) && !prefs(context).edit()
                .putString("id", UUID.randomUUID().toString()).putBoolean("enabled", true).commit()) {
            show(context, "無法儲存此裝置的推播設定");
            return;
        }
        String enrollment = prefs(context).getString("id", "");
        PushSyncJob.schedule(context);
        NETWORK.execute(() -> {
            if (!enrollment.equals(prefs(context).getString("id", "")) ||
                    !bearer.equals(MainActivity.loadLogin(context))) return;
            try {
                String id = register(context, bearer);
                if (!enrollment.equals(id) || !enabled(context) ||
                        !enrollment.equals(prefs(context).getString("id", ""))) return;
                if (!test) {
                    show(context, "此裝置已註冊雲端推播");
                    return;
                }
                JSONObject data = new JSONObject().put("device_id", id)
                        .put("event_id", UUID.randomUUID().toString()).put("test", true);
                int status = request("POST", "cloud/calls", bearer, data);
                if (status == 202) show(context, "測試來電已排入雲端，請查看遠端推播紀錄");
                else if (status == 503) show(context, "Render 尚未設定 Firebase 發送憑證");
                else show(context, "推播測試未完成（HTTP " + status + "）");
            } catch (Exception ignored) {
                show(context, "推播測試未完成，請檢查網路和私人連線");
            }
        });
    }

    static synchronized void refresh(Context source) {
        Context context = source.getApplicationContext();
        if (!enabled(context) || refreshQueued || messaging(context) == null) return;
        PushSyncJob.schedule(context);
        refreshQueued = true;
        NETWORK.execute(() -> {
            try {
                synchronize(context);
            } finally {
                synchronized (PushEnrollment.class) { refreshQueued = false; }
            }
        });
    }

    static void syncJob(Context source, Consumer<Boolean> completed) {
        Context context = source.getApplicationContext();
        NETWORK.execute(() -> {
            boolean ok = synchronize(context);
            new Handler(Looper.getMainLooper()).post(() -> completed.accept(ok));
        });
    }

    private static boolean synchronize(Context context) {
        if (!enabled(context)) return true;
        String bearer = MainActivity.loadLogin(context);
        if (bearer.isEmpty()) return true;
        try {
            return register(context, bearer) != null && flush(context);
        } catch (Exception ignored) {
            return false;
        }
    }

    private static String register(Context context, String bearer) throws Exception {
        String id = prefs(context).getString("id", "");
        FirebaseMessaging firebase = messaging(context);
        if (id.isEmpty() || firebase == null || !enabled(context)) return null;
        String token = Tasks.await(firebase.getToken(), 15, TimeUnit.SECONDS);
        if (!enabled(context) || !id.equals(prefs(context).getString("id", ""))) return null;
        int status = request("PUT", "push/device", bearer, new JSONObject().put("device_id", id).put("token", token));
        if (status != 204) throw new IllegalStateException("Enrollment rejected");
        if (enabled(context)) firebase.setAutoInitEnabled(true);
        return id;
    }

    static synchronized boolean disable(Context source, String bearer, boolean notify) {
        Context context = source.getApplicationContext();
        SharedPreferences p = prefs(context);
        String id = p.getString("id", "");
        if (id.isEmpty() && !enabled(context)) {
            if (notify) show(context, "遠端推播已關閉");
            return true;
        }
        if (!p.edit().putBoolean("enabled", false).commit()) return false;
        PushSyncJob.cancel(context);
        receipts(context).edit().clear().apply();
        NETWORK.execute(() -> {
            boolean revoked = false;
            try {
                if (!id.isEmpty() && !bearer.isEmpty()) {
                    revoked = request("DELETE", "push/device", bearer, new JSONObject().put("device_id", id)) == 204;
                }
            } catch (Exception ignored) {
                // Local opt-out remains in force when the network is unavailable.
            }
            try {
                FirebaseMessaging firebase = messaging(context);
                if (firebase != null) {
                    firebase.setAutoInitEnabled(false);
                    Tasks.await(firebase.deleteToken(), 15, TimeUnit.SECONDS);
                    revoked = true;
                }
            } catch (Exception ignored) {
                // Retry remote revocation by tapping disable again.
            }
            synchronized (PushEnrollment.class) {
                if (revoked && !enabled(context) && id.equals(p.getString("id", ""))) {
                    p.edit().remove("id").apply();
                }
            }
            if (notify) show(context, revoked ? "已停用此裝置的遠端推播" : "已在手機停用；遠端撤銷尚未確認");
        });
        return true;
    }

    private static SharedPreferences receipts(Context context) {
        return context.getSharedPreferences("vera_fcm_receipts", Context.MODE_PRIVATE);
    }

    static synchronized void report(Context source, String event, String state) {
        if (event == null || event.isEmpty() || !enabled(source)) return;
        Context context = source.getApplicationContext();
        SharedPreferences outbox = receipts(context);
        String key = event + "/" + state;
        if (outbox.contains(key)) return;
        Map<String, ?> pending = outbox.getAll();
        SharedPreferences.Editor changes = outbox.edit();
        if (pending.size() >= 120) {
            pending.entrySet().stream().min(Comparator.comparingLong(entry -> (Long) entry.getValue()))
                    .ifPresent(entry -> changes.remove(entry.getKey()));
        }
        if (changes.putLong(key, System.currentTimeMillis()).commit()) {
            NETWORK.execute(() -> flush(context));
        }
    }

    private static boolean flush(Context context) {
        if (!enabled(context)) return true;
        String bearer = MainActivity.loadLogin(context);
        String id = prefs(context).getString("id", "");
        if (bearer.isEmpty() || id.isEmpty()) return false;
        SharedPreferences outbox = receipts(context);
        try {
            java.util.List<Map.Entry<String, ?>> jobs = new java.util.ArrayList<>(outbox.getAll().entrySet());
            jobs.sort(Comparator.<Map.Entry<String, ?>>comparingLong(entry -> (Long) entry.getValue())
                    .thenComparingInt(entry -> entry.getKey().endsWith("/received") ? 0 :
                            entry.getKey().endsWith("/ringing") ? 1 : 2));
            for (Map.Entry<String, ?> entry : jobs) {
                if (!enabled(context) || !id.equals(prefs(context).getString("id", ""))) return false;
                String key = entry.getKey();
                String[] fields = key.split("/", 2);
                if (fields.length != 2) { outbox.edit().remove(key).apply(); continue; }
                int status = request("PUT", "cloud/receipt", bearer, new JSONObject()
                        .put("device_id", id).put("event_id", fields[0]).put("state", fields[1]));
                if (status == 204 || status == 404 || status == 409) outbox.edit().remove(key).apply();
                else return false;
            }
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    static synchronized boolean remember(Context context, String event, long expiry) {
        if (!enabled(context)) return false;
        SharedPreferences events = context.getSharedPreferences("vera_fcm_events", Context.MODE_PRIVATE);
        if (events.contains(event)) return false;
        SharedPreferences.Editor update = events.edit();
        long now = System.currentTimeMillis();
        int live = 0;
        for (Map.Entry<String, ?> entry : events.getAll().entrySet()) {
            if (entry.getValue() instanceof Long && (Long) entry.getValue() > now) live++;
            else update.remove(entry.getKey());
        }
        return live < 100 && update.putLong(event, expiry).commit();
    }

    private static int request(String method, String path, String bearer, JSONObject payload) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(BASE + path).openConnection();
        try {
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(16000);
            conn.setInstanceFollowRedirects(false);
            conn.setRequestMethod(method);
            conn.setRequestProperty("Authorization", "Bearer " + bearer);
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            conn.setDoOutput(true);
            byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(body.length);
            try (OutputStream stream = conn.getOutputStream()) { stream.write(body); }
            return conn.getResponseCode();
        } finally {
            conn.disconnect();
        }
    }

    private static void show(Context context, String message) {
        new Handler(Looper.getMainLooper()).post(() -> Toast.makeText(context, message, Toast.LENGTH_LONG).show());
    }
}
