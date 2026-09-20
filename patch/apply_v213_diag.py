from pathlib import Path
import sys

root = Path(sys.argv[1])
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
build = root / "app/build.gradle"

s = mirror.read_text()

# Diagnostic-only additions. Do not alter the v2.11 capture/rendering path.
s = s.replace(
    "import android.os.Looper;\n",
    "import android.os.Looper;\nimport android.os.SystemClock;\n",
    1)

s = s.replace(
    "    private int captureHeight;\n    private int densityDpi;\n",
    "    private int captureHeight;\n    private int densityDpi;\n"
    "    private long diagnosticStartElapsed;\n"
    "    private int diagnosticResizeCount;\n"
    "    private int diagnosticVisibilityCount;\n",
    1)

old_stop = '''        public void onStop() {
            if (!intentionalStop) {
                setMirrorError("Skärmdelningen stoppades.", "PROJECTION_STOPPED");
            }
            stopSelf();
        }'''
new_stop = '''        public void onStop() {
            recordDiagnosticEvent("projection_stop",
                    "intentional=" + intentionalStop);
            if (!intentionalStop) {
                setMirrorError("Skärmdelningen stoppades.", "PROJECTION_STOPPED");
            }
            stopSelf();
        }'''
if old_stop not in s:
    raise SystemExit("diag: onStop block not found")
s = s.replace(old_stop, new_stop, 1)

old_resize = '''        public void onCapturedContentResize(int width, int height) {
            if (width <= 0 || height <= 0) return;
            captureWidth = width;
            captureHeight = height;'''
new_resize = '''        public void onCapturedContentResize(int width, int height) {
            diagnosticResizeCount++;
            recordDiagnosticEvent(
                    "capture_resize_" + diagnosticResizeCount,
                    width + "x" + height);
            if (width <= 0 || height <= 0) return;
            captureWidth = width;
            captureHeight = height;'''
if old_resize not in s:
    raise SystemExit("diag: resize block not found")
s = s.replace(old_resize, new_resize, 1)

old_vis = '''        public void onCapturedContentVisibilityChanged(boolean isVisible) {
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("captured_content_visible", isVisible)
                    .apply();
        }'''
new_vis = '''        public void onCapturedContentVisibilityChanged(boolean isVisible) {
            diagnosticVisibilityCount++;
            recordDiagnosticEvent(
                    "capture_visibility_" + diagnosticVisibilityCount,
                    Boolean.toString(isVisible));
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("captured_content_visible", isVisible)
                    .apply();
        }'''
if old_vis not in s:
    raise SystemExit("diag: visibility block not found")
s = s.replace(old_vis, new_vis, 1)

# Start diagnostic clock when the real v2.11 service starts.
old_fg = '''        startForeground(NOTIFICATION_ID, buildNotification());

        int resultCode'''
new_fg = '''        startForeground(NOTIFICATION_ID, buildNotification());

        diagnosticStartElapsed = SystemClock.elapsedRealtime();
        diagnosticResizeCount = 0;
        diagnosticVisibilityCount = 0;
        getSharedPreferences("diagnostics", MODE_PRIVATE).edit().clear().apply();
        recordDiagnosticEvent("service_start", getDisplaySnapshot());

        int resultCode'''
if old_fg not in s:
    raise SystemExit("diag: foreground anchor not found")
s = s.replace(old_fg, new_fg, 1)

# Log key existing stages, without changing sequencing.
s = s.replace(
'''        projection.registerCallback(projectionCallback, mainHandler);
        createMirrorOverlay();''',
'''        projection.registerCallback(projectionCallback, mainHandler);
        recordDiagnosticEvent("projection_acquired", getDisplaySnapshot());
        createMirrorOverlay();''',
1)

s = s.replace(
'''            if (probeFrames >= 5) {
                probeFinished = true;
                appCaptureVerified = true;''',
'''            if (probeFrames >= 5) {
                probeFinished = true;
                appCaptureVerified = true;
                recordDiagnosticEvent("app_capture_verified", getDisplaySnapshot());''',
1)

s = s.replace(
'''            virtualDisplay.setSurface(mirrorSurface);

            if (probeReader != null) {''',
'''            virtualDisplay.setSurface(mirrorSurface);
            recordDiagnosticEvent("mirror_surface_active", getDisplaySnapshot());

            if (probeReader != null) {''',
1)

# Add diagnostics helpers immediately before setMirrorError.
anchor = "    private void setMirrorError(String message, String code) {"
if anchor not in s:
    raise SystemExit("diag: helper anchor not found")

helpers = r'''    private String getDisplaySnapshot() {
        try {
            android.view.Display display = getDisplay();
            if (display == null) {
                display = ((WindowManager) getSystemService(WINDOW_SERVICE))
                        .getDefaultDisplay();
            }

            android.util.DisplayMetrics metrics = new android.util.DisplayMetrics();
            display.getRealMetrics(metrics);

            return "display=" + metrics.widthPixels + "x" + metrics.heightPixels
                    + ",density=" + metrics.densityDpi
                    + ",rotation=" + display.getRotation()
                    + ",refresh=" + display.getRefreshRate()
                    + ",brightnessMode=" + android.provider.Settings.System.getInt(
                            getContentResolver(),
                            android.provider.Settings.System.SCREEN_BRIGHTNESS_MODE,
                            -1)
                    + ",brightness=" + android.provider.Settings.System.getInt(
                            getContentResolver(),
                            android.provider.Settings.System.SCREEN_BRIGHTNESS,
                            -1);
        } catch (Throwable t) {
            return "snapshot_error=" + t.getClass().getSimpleName();
        }
    }

    private void recordDiagnosticEvent(String name, String value) {
        try {
            long elapsed = diagnosticStartElapsed == 0L
                    ? 0L
                    : SystemClock.elapsedRealtime() - diagnosticStartElapsed;
            long wall = System.currentTimeMillis();

            android.content.SharedPreferences prefs =
                    getSharedPreferences("diagnostics", MODE_PRIVATE);
            int index = prefs.getInt("event_count", 0) + 1;

            prefs.edit()
                    .putInt("event_count", index)
                    .putString("event_" + index,
                            elapsed + "ms|" + wall + "|" + name + "|" + value)
                    .apply();

            android.util.Log.i(
                    "ProjektorDiag",
                    elapsed + "ms " + name + " " + value);
        } catch (Throwable ignored) {
        }
    }

'''
s = s.replace(anchor, helpers + anchor, 1)

mirror.write_text(s)

# Add a diagnostic report to the existing main screen without changing capture behavior.
m = main.read_text()

# Use fully-qualified clipboard classes below so this diagnostic patch
# does not depend on the import layout of MainActivity.

# Insert helper methods before onDestroy if present, otherwise before final class brace.
insert_anchor = "    @Override\n    protected void onDestroy()"
if insert_anchor not in m:
    insert_anchor = "\n}"
diag_methods = r'''    private String buildDiagnosticReport() {
        android.content.SharedPreferences prefs =
                getSharedPreferences("diagnostics", MODE_PRIVATE);
        int count = prefs.getInt("event_count", 0);
        StringBuilder out = new StringBuilder();
        out.append("Projektorläge diagnostik v2.13\n");
        for (int i = 1; i <= count; i++) {
            String event = prefs.getString("event_" + i, "");
            if (event != null && !event.isEmpty()) {
                out.append(i).append(". ").append(event).append("\n");
            }
        }
        return out.toString();
    }

    private void copyDiagnosticReport() {
        String report = buildDiagnosticReport();
        android.content.ClipboardManager cm =
                (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (cm != null) {
            cm.setPrimaryClip(android.content.ClipData.newPlainText(
                    "Projektorläge diagnostik", report));
            android.widget.Toast.makeText(
                    this,
                    "Diagnostiken är kopierad. Klistra in den i chatten.",
                    android.widget.Toast.LENGTH_LONG).show();
        }
    }

'''
m = m.replace(insert_anchor, diag_methods + insert_anchor, 1)

# Add a long-press diagnostic action to the existing start button if discoverable.
# This does not alter normal tap behavior.
candidates = ["startButton", "btnStart", "startProjectorButton"]
hooked = False
for name in candidates:
    marker = name + ".setOnClickListener"
    pos = m.find(marker)
    if pos >= 0:
        # Add the long click before normal click listener.
        m = m[:pos] + name + '''.setOnLongClickListener(v -> {
            copyDiagnosticReport();
            return true;
        });
        ''' + m[pos:]
        hooked = True
        break

# If names differ, leave report in SharedPreferences/logcat; build remains diagnostic.
main.write_text(m)

b = build.read_text()
b = b.replace("versionCode 31", "versionCode 33", 1)
b = b.replace("versionName '2.11.0'", "versionName '2.13.0-diag'", 1)
build.write_text(b)

print("v2.13 diagnostic instrumentation applied; UI hook=" + str(hooked))
