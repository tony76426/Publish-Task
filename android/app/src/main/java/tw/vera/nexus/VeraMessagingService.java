package tw.vera.nexus;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;
import java.util.Map;
import java.util.UUID;

public final class VeraMessagingService extends FirebaseMessagingService {
    @Override public void onNewToken(String token) {
        PushEnrollment.refresh(this);
    }

    @Override public void onMessageReceived(RemoteMessage message) {
        Map<String, String> data = message.getData();
        if (!"vera_call".equals(data.get("type")) || !PushEnrollment.enabled(this) || MainActivity.loadLogin(this).isEmpty()) return;
        String event = data.get("event_id");
        long expiry;
        try {
            if (event == null || !UUID.fromString(event).toString().equals(event)) return;
            expiry = Long.parseLong(data.get("expires_at"));
        } catch (IllegalArgumentException ignored) {
            return;
        }
        long now = System.currentTimeMillis();
        if (expiry <= now || expiry - now > 60_000 || !PushEnrollment.remember(this, event, expiry)) return;
        String kind = "true".equals(data.get("test")) ? "remote-test" : "remote";
        PushEnrollment.report(this, event, "received");
        // The existing receiver enforces notification permissions and quiet hours.
        // Never retry a remote event locally after its expiry.
        ReminderReceiver.ring(this, kind, true, event);
    }
}
