from pathlib import Path
import re, sys

root = Path(sys.argv[1])
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

# v2.11 keeps the exact v2.7 mirroring architecture.
# Only brightness ownership changes: Samsung/Netflix keeps control of panel brightness.
# Projectorläge no longer forces a per-window 100% override or switches system brightness mode.

m = mirror.read_text()
old = "        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL;\n"
if old not in m:
    raise SystemExit("v2.11: mirror brightness override not found")
m = m.replace(old,
              "        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE;\n",
              1)
mirror.write_text(m)

s = svc.read_text()

# Replace startup brightness forcing with a read-only verification step.
old_enable = """            boolean brightnessOk = forceProjectorBrightness();
            startBrightnessKick();
            setLightBoost(0);"""
new_enable = """            boolean brightnessOk = preserveCurrentBrightnessState();
            stopBrightnessKick();
            setLightBoost(0);"""
if old_enable not in s:
    raise SystemExit("v2.11: projector enable brightness block not found")
s = s.replace(old_enable, new_enable, 1)

# Add a non-invasive brightness verifier before forceProjectorBrightness().
anchor = "    private boolean forceProjectorBrightness() {"
if anchor not in s:
    raise SystemExit("v2.11: forceProjectorBrightness anchor not found")

method = r'''    private boolean preserveCurrentBrightnessState() {
        try {
            int mode = Settings.System.getInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS_MODE,
                    Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL);
            int value = Settings.System.getInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS,
                    128);

            // Important: clear any backup left by older experimental builds.
            // Otherwise STOP could restore a stale brightness value and undo
            // Samsung's current video-brightness/HBM state.
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("brightness_backup_valid", false)
                    .putInt("projector_brightness_actual", value)
                    .putInt("projector_brightness_mode_actual", mode)
                    .putBoolean("projector_brightness_passthrough", true)
                    .putBoolean("brightness_verified", true)
                    .apply();

            return true;
        } catch (Exception ignored) {
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("brightness_verified", false)
                    .apply();
            return false;
        }
    }

'''
s = s.replace(anchor, method + anchor, 1)

# The health watchdog must not re-assert brightness either.
# If it calls forceProjectorBrightness(), replace only watchdog/runtime calls,
# leaving the method itself available for explicit remote BRIGHTNESS_MAX.
s = s.replace("                forceProjectorBrightness();\n", "", 1)

svc.write_text(s)

b = build.read_text()
b = b.replace("versionCode 30", "versionCode 31", 1)
b = b.replace("versionName '2.10.0'", "versionName '2.11.0'", 1)
build.write_text(b)

print("v2.11 brightness passthrough fix applied")
