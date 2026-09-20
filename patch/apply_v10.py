from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

# --- MainActivity: add projector-light boost controls on the remote ---
s = main.read_text()

s = replace_once(s,
'''        panel.addView(lightRow, full(0, dp(16)));

        Button stop = makeButton("STÄNG PROJEKTORLÄGET PÅ ANDRA MOBILEN");''',
'''        panel.addView(lightRow, full(0, dp(10)));

        panel.addView(text("PROJEKTORBOOST – lyfter mörka Netflix-bilder", 14, muted(), true), full(dp(4), dp(6)));
        LinearLayout boostRow = new LinearLayout(this);
        boostRow.setOrientation(LinearLayout.HORIZONTAL);
        boostRow.setWeightSum(3f);
        Button boostOff = makeButton("BOOST AV");
        Button boost12 = makeButton("+12%");
        Button boost25 = makeButton("+25%");
        boostOff.setOnClickListener(v -> sendRemote("BOOST_0"));
        boost12.setOnClickListener(v -> sendRemote("BOOST_12"));
        boost25.setOnClickListener(v -> sendRemote("BOOST_25"));
        boostRow.addView(boostOff, weighted(dp(4)));
        boostRow.addView(boost12, weighted(dp(4)));
        boostRow.addView(boost25, weighted(0));
        panel.addView(boostRow, full(0, dp(16)));

        Button stop = makeButton("STÄNG PROJEKTORLÄGET PÅ ANDRA MOBILEN");''',
"remote boost row")

s = replace_once(s,
'''            case "BRIGHTNESS": return "ljusstyrka ändrad";
            case "NETFLIX": return "Netflix startas";''',
'''            case "BRIGHTNESS": return "ljusstyrka ändrad";
            case "BOOST_0": return "projektorboost av";
            case "BOOST_12": return "projektorboost +12%";
            case "BOOST_25": return "projektorboost +25%";
            case "NETFLIX": return "Netflix startas";''',
"friendly boost responses")

main.write_text(s)

# --- RotationService: true max system brightness + optional white-lift overlay ---
s = svc.read_text()

s = replace_once(s,
'''    private WindowManager windowManager;
    private View orientationView;''',
'''    private WindowManager windowManager;
    private View orientationView;
    private View lightBoostView;''',
"light boost field")

# Max brightness automatically whenever projector mode is enabled.
s = replace_once(s,
'''        applySavedSystemRotation();

        if (Settings.canDrawOverlays(this)) {
            addOrientationOverlay();
            applySavedOrientation();
            startRemoteServer();
            setEnabled(true);''',
'''        applySavedSystemRotation();

        if (Settings.canDrawOverlays(this)) {
            addOrientationOverlay();
            applySavedOrientation();
            forceProjectorBrightness();
            int savedBoost = getSharedPreferences("state", MODE_PRIVATE).getInt("light_boost_percent", 12);
            setLightBoost(savedBoost);
            startRemoteServer();
            setEnabled(true);''',
"enable brightness boost")

# Commands
s = replace_once(s,
'''            case "BRIGHTNESS_MAX":
                return setBrightness(255);
            case "NETFLIX":''',
'''            case "BRIGHTNESS_MAX":
                return setBrightness(255);
            case "BOOST_0":
                return setLightBoost(0);
            case "BOOST_12":
                return setLightBoost(12);
            case "BOOST_25":
                return setLightBoost(25);
            case "NETFLIX":''',
"boost commands")

# Insert helpers before adjustBrightness.
s = replace_once(s,
'''    private String adjustBrightness(int delta) {''',
'''    private void forceProjectorBrightness() {
        if (!Settings.System.canWrite(this)) return;
        try {
            android.content.SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);
            if (!prefs.getBoolean("brightness_backup_valid", false)) {
                int oldMode = Settings.System.getInt(
                        getContentResolver(),
                        Settings.System.SCREEN_BRIGHTNESS_MODE,
                        Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL);
                int oldBrightness = Settings.System.getInt(
                        getContentResolver(),
                        Settings.System.SCREEN_BRIGHTNESS,
                        128);
                prefs.edit()
                        .putBoolean("brightness_backup_valid", true)
                        .putInt("brightness_backup_mode", oldMode)
                        .putInt("brightness_backup_value", oldBrightness)
                        .apply();
            }
            Settings.System.putInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS_MODE,
                    Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL);
            Settings.System.putInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS,
                    255);
        } catch (Exception ignored) {
        }
    }

    private void restoreProjectorBrightness() {
        if (!Settings.System.canWrite(this)) return;
        android.content.SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);
        if (!prefs.getBoolean("brightness_backup_valid", false)) return;
        try {
            int oldMode = prefs.getInt(
                    "brightness_backup_mode",
                    Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL);
            int oldBrightness = prefs.getInt("brightness_backup_value", 128);
            Settings.System.putInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS,
                    Math.max(1, Math.min(255, oldBrightness)));
            Settings.System.putInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS_MODE,
                    oldMode);
        } catch (Exception ignored) {
        } finally {
            prefs.edit().putBoolean("brightness_backup_valid", false).apply();
        }
    }

    private String setLightBoost(int percent) {
        int clamped = Math.max(0, Math.min(35, percent));
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putInt("light_boost_percent", clamped)
                .apply();

        new Handler(Looper.getMainLooper()).post(() -> applyLightBoost(clamped));

        if (clamped == 0) return "OK|BOOST_0";
        if (clamped <= 12) return "OK|BOOST_12";
        return "OK|BOOST_25";
    }

    private void applyLightBoost(int percent) {
        if (windowManager == null) {
            windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        }

        removeLightBoostOverlay();

        if (percent <= 0 || !Settings.canDrawOverlays(this)) return;

        lightBoostView = new View(this);
        lightBoostView.setBackgroundColor(Color.WHITE);

        int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_SYSTEM_OVERLAY;

        int overlayFlags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON;

        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                type,
                overlayFlags,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.TOP | Gravity.START;
        params.alpha = percent / 100f;
        params.screenBrightness = 1.0f;
        params.setTitle("Projektorläge light boost");

        try {
            windowManager.addView(lightBoostView, params);
        } catch (Exception ignored) {
            lightBoostView = null;
        }
    }

    private void removeLightBoostOverlay() {
        if (lightBoostView != null && windowManager != null) {
            try {
                windowManager.removeView(lightBoostView);
            } catch (Exception ignored) {
            }
        }
        lightBoostView = null;
    }

    private String adjustBrightness(int delta) {''',
"brightness and overlay helpers")

# Ensure boost overlay doesn't null the shared WindowManager when orientation view is removed.
s = replace_once(s,
'''        orientationView = null;
        windowManager = null;
    }''',
'''        orientationView = null;
        if (lightBoostView == null) windowManager = null;
    }''',
"keep window manager for boost")

# Shutdown/restore.
s = replace_once(s,
'''    private void shutdownEverything() {
        stopRemoteServer();
        restoreOriginalRotationSettings();
        removeOrientationOverlay();''',
'''    private void shutdownEverything() {
        stopRemoteServer();
        restoreOriginalRotationSettings();
        restoreProjectorBrightness();
        removeLightBoostOverlay();
        removeOrientationOverlay();''',
"shutdown brightness restore")

# onDestroy may be called without shutdown.
s = replace_once(s,
'''    public void onDestroy() {
        stopRemoteServer();
        removeOrientationOverlay();
        setEnabled(false);
        super.onDestroy();
    }''',
'''    public void onDestroy() {
        stopRemoteServer();
        restoreProjectorBrightness();
        removeLightBoostOverlay();
        removeOrientationOverlay();
        setEnabled(false);
        super.onDestroy();
    }''',
"destroy brightness restore")

svc.write_text(s)

s = build.read_text()
s = s.replace("versionCode 9", "versionCode 10", 1)
s = s.replace("versionName '0.9.0'", "versionName '1.0.0'", 1)
build.write_text(s)

print("v1.0 projector-light patch applied")
