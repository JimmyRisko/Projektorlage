from pathlib import Path
import re, sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

def must_replace(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

# ---------------- MainActivity ----------------
s = main.read_text()

s = s.replace('makeButton("STÄNG PROJEKTORLÄGE")',
              'makeButton("STOPPA & ÅTERSTÄLL MOBILEN")', 1)
s = s.replace('makeButton("STÄNG PROJEKTORLÄGET PÅ ANDRA MOBILEN")',
              'makeButton("STOPPA & ÅTERSTÄLL PROJEKTORMOBILEN")', 1)

# Make the remote status explicit about full restore.
s = s.replace(
    'else if ("STOP".equals(command)) remoteStatus.setText("Fjärrservern stoppas");',
    'else if ("STOP".equals(command)) remoteStatus.setText("Projektorläget stoppas och mobilen återställs");',
    1
)

# Add clear help under local stop button.
needle = '''        disable.setOnClickListener(v -> disableProjectorMode());
        panel.addView(disable, full(0, dp(12)));'''
replacement = '''        disable.setOnClickListener(v -> disableProjectorMode());
        panel.addView(disable, full(0, dp(8)));
        panel.addView(text("Återställer rotation, ljusstyrka, overlays och nätverkslås och stänger tjänsten helt.", 12, muted(), false), full(0, dp(12)));'''
if needle in s:
    s = s.replace(needle, replacement, 1)

main.write_text(s)

# ---------------- RotationService ----------------
s = svc.read_text()

# Make the existing remote STOP semantics explicit and support RESET_PHONE alias.
s = must_replace(s,
'''            case "STOP":
                new Handler(Looper.getMainLooper()).postDelayed(this::shutdownEverything, 350);
                return "OK|STOPPING";''',
'''            case "STOP":
            case "RESET_PHONE":
                new Handler(Looper.getMainLooper()).postDelayed(this::shutdownEverything, 350);
                return "OK|STOPPING";''',
"remote reset alias")

# Replace shutdownEverything with a deliberately idempotent full reset.
pattern = re.compile(r'''    private void shutdownEverything\(\) \{.*?\n    \}\n\n    private String getOrCreatePin\(\)''', re.S)
match = pattern.search(s)
if not match:
    raise SystemExit("Patch misslyckades: shutdownEverything block")

new_shutdown = '''    private void shutdownEverything() {
        // Mark the mode disabled first so watchdogs/network callbacks cannot revive it.
        setEnabled(false);

        stopHealthWatchdog();
        stopRemoteServer();
        releaseConnectivityLocks();

        // Stop any experimental screen-mirroring overlay/service too.
        try {
            stopService(new Intent(this, MirrorOverlayService.class));
        } catch (Exception ignored) {
        }

        // Restore every system-level setting that Projektorläge may have changed.
        restoreOriginalRotationSettings();
        restoreProjectorBrightness();

        // Remove all windows/overlays last so nothing remains over other apps.
        removeLightBoostOverlay();
        removeOrientationOverlay();

        unregisterNetworkCallback();

        try {
            stopForeground(STOP_FOREGROUND_REMOVE);
        } catch (Exception ignored) {
        }
        stopSelf();
    }

    private String getOrCreatePin()'''
s = s[:match.start()] + new_shutdown + s[match.end():]

# Harden onDestroy: this is the critical crash/kill path that previously could
# leave system rotation changed.
pattern = re.compile(r'''    @Override\n    public void onDestroy\(\) \{.*?\n    \}\n''', re.S)
m = pattern.search(s)
if not m:
    raise SystemExit("Patch misslyckades: onDestroy")

new_destroy = '''    @Override
    public void onDestroy() {
        setEnabled(false);
        stopHealthWatchdog();
        stopRemoteServer();
        releaseConnectivityLocks();
        unregisterNetworkCallback();

        try {
            stopService(new Intent(this, MirrorOverlayService.class));
        } catch (Exception ignored) {
        }

        restoreOriginalRotationSettings();
        restoreProjectorBrightness();
        removeLightBoostOverlay();
        removeOrientationOverlay();

        super.onDestroy();
    }
'''
s = s[:m.start()] + new_destroy + s[m.end():]

# If the app is swiped away, restore the phone instead of leaving projector state behind.
insert_anchor = '''    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }'''
if insert_anchor not in s:
    raise SystemExit("Patch misslyckades: onBind anchor")

insert = '''    @Override
    public void onTaskRemoved(Intent rootIntent) {
        shutdownEverything();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }'''
s = s.replace(insert_anchor, insert, 1)

# Notification must expose a clear emergency restore action even while Netflix is open.
s = s.replace('"Stäng",\n                        disable', '"STOPPA & ÅTERSTÄLL",\n                        disable', 1)
s = s.replace('.setContentText("Låst landskapsriktning + fjärrkontroll på lokala nätverket")',
              '.setContentText("Fjärr aktiv. Tryck STOPPA & ÅTERSTÄLL för normal mobil igen.")', 1)

svc.write_text(s)

# ---------------- Version ----------------
b = build.read_text()
b = b.replace("versionCode 11", "versionCode 12", 1)
b = b.replace("versionName '1.1.0'", "versionName '1.2.0'", 1)
build.write_text(b)

print("v1.2 full restore patch applied")
