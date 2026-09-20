from pathlib import Path
import re, sys

root = Path(sys.argv[1])
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

s = svc.read_text()

# Add a short-lived brightness reassertion handler so Netflix/app launches cannot undo max brightness.
if "brightnessKickHandler" not in s:
    anchor = '''    private View lightBoostView;'''
    if anchor not in s:
        raise SystemExit("Patch misslyckades: brightness field anchor")
    s = s.replace(anchor, anchor + '''
    private final Handler brightnessKickHandler = new Handler(Looper.getMainLooper());
    private Runnable brightnessKickRunnable;
    private int brightnessKickCount;''', 1)

# Replace forceProjectorBrightness with a device-aware max instead of hard-coded 255.
pat = re.compile(r'''    private void forceProjectorBrightness\(\) \{.*?\n    \}\n\n    private void restoreProjectorBrightness\(\)''', re.S)
m = pat.search(s)
if not m:
    raise SystemExit("Patch misslyckades: forceProjectorBrightness block")

replacement = '''    private int getDeviceBrightnessMaximum() {
        try {
            int id = getResources().getIdentifier(
                    "config_screenBrightnessSettingMaximum",
                    "integer",
                    "android");
            if (id != 0) {
                int value = getResources().getInteger(id);
                if (value > 0) return value;
            }
        } catch (Exception ignored) {
        }
        return 255;
    }

    private void forceProjectorBrightness() {
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

            int maximum = getDeviceBrightnessMaximum();

            Settings.System.putInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS_MODE,
                    Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL);
            Settings.System.putInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS,
                    maximum);

            prefs.edit()
                    .putInt("projector_brightness_max", maximum)
                    .apply();
        } catch (Exception ignored) {
        }
    }

    private void startBrightnessKick() {
        stopBrightnessKick();
        brightnessKickCount = 0;

        brightnessKickRunnable = new Runnable() {
            @Override
            public void run() {
                boolean enabled = getSharedPreferences("state", MODE_PRIVATE)
                        .getBoolean("enabled", false);
                if (!enabled) {
                    stopBrightnessKick();
                    return;
                }

                forceProjectorBrightness();
                brightnessKickCount++;

                // Re-assert while Netflix is opening; then stop so remote brightness controls
                // are free to change the level afterwards.
                if (brightnessKickCount < 7) {
                    brightnessKickHandler.postDelayed(this, 700);
                } else {
                    stopBrightnessKick();
                }
            }
        };

        brightnessKickHandler.post(brightnessKickRunnable);
    }

    private void stopBrightnessKick() {
        if (brightnessKickRunnable != null) {
            brightnessKickHandler.removeCallbacks(brightnessKickRunnable);
        }
        brightnessKickRunnable = null;
        brightnessKickCount = 0;
    }

    private void restoreProjectorBrightness()'''
s = s[:m.start()] + replacement + s[m.end():]

# Start the brightness kick whenever projector mode is successfully enabled.
needle = '''            forceProjectorBrightness();
            int savedBoost = getSharedPreferences("state", MODE_PRIVATE).getInt("light_boost_percent", 0);'''
repl = '''            forceProjectorBrightness();
            startBrightnessKick();
            int savedBoost = getSharedPreferences("state", MODE_PRIVATE).getInt("light_boost_percent", 0);'''
if needle not in s:
    raise SystemExit("Patch misslyckades: enable brightness start")
s = s.replace(needle, repl, 1)

# Stop reassertion before restoring normal phone state.
s = s.replace(
'''        stopHealthWatchdog();
        stopRemoteServer();
        releaseConnectivityLocks();''',
'''        stopHealthWatchdog();
        stopBrightnessKick();
        stopRemoteServer();
        releaseConnectivityLocks();''',
1)

# There is a second cleanup path in onDestroy.
idx = s.find('''    public void onDestroy() {''')
if idx >= 0:
    tail = s[idx:]
    tail = tail.replace(
'''        stopHealthWatchdog();
        stopRemoteServer();''',
'''        stopHealthWatchdog();
        stopBrightnessKick();
        stopRemoteServer();''',
1)
    s = s[:idx] + tail

svc.write_text(s)

# Mirror window: use Android's explicit full-brightness override constant.
s = mirror.read_text()
s = s.replace(
    "        lp.screenBrightness = 1.0f;",
    "        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL;",
    1
)
mirror.write_text(s)

# Version
b = build.read_text()
b = b.replace("versionCode 21", "versionCode 22", 1)
b = b.replace("versionName '2.1.0'", "versionName '2.2.0'", 1)
build.write_text(b)

print("v2.2 brightness enforcement applied")
