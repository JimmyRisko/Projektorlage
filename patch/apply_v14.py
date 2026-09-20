from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

def must_replace(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

# ---- MainActivity: one-tap projector preset ----
s = main.read_text()

s = must_replace(s,
'''        Button enable = makeButton("AKTIVERA PROJEKTOR + FJÄRR");
        enable.setOnClickListener(v -> requestOverlayAndEnable());''',
'''        Button enable = makeButton("STARTA PROJEKTOR");
        enable.setOnClickListener(v -> startProjectorAutomatic());''',
"one tap projector button")

# Explain that advanced controls are optional.
needle = '''        panel.addView(enable, full(0, dp(10)));'''
if needle in s:
    s = s.replace(needle, needle + '''
        panel.addView(text("Ett tryck: rätt bildriktning, maxljus, projektorboost, fjärrserver och Netflix startas automatiskt. Första gången kan Android fråga om behörigheter.", 12, muted(), false), full(0, dp(10)));''', 1)

# Add helper before requestOverlayAndEnable.
anchor = '''    private void requestOverlayAndEnable() {'''
if anchor not in s:
    raise SystemExit("Patch misslyckades: requestOverlayAndEnable anchor")

helper = '''    private void startProjectorAutomatic() {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("rotation_mode", "REVERSE")
                .putInt("light_boost_percent", 12)
                .putBoolean("auto_launch_netflix", true)
                .apply();

        requestOverlayAndEnable();
    }

'''
s = s.replace(anchor, helper + anchor, 1)
main.write_text(s)

# ---- RotationService: when automatic mode reaches the active state, open Netflix ----
s = svc.read_text()
needle2 = '''            startRemoteServer();
            setEnabled(true);'''
replacement2 = '''            startRemoteServer();
            setEnabled(true);

            android.content.SharedPreferences autoPrefs = getSharedPreferences("state", MODE_PRIVATE);
            if (ACTION_ENABLE.equals(action) && autoPrefs.getBoolean("auto_launch_netflix", false)) {
                autoPrefs.edit().putBoolean("auto_launch_netflix", false).apply();
                new Handler(Looper.getMainLooper()).postDelayed(this::openNetflix, 700);
            }'''
s = must_replace(s, needle2, replacement2, "automatic Netflix launch")
svc.write_text(s)

# ---- Version ----
b = build.read_text()
b = b.replace("versionCode 13", "versionCode 14", 1)
b = b.replace("versionName '1.3.0'", "versionName '1.4.0'", 1)
build.write_text(b)

print("v1.4 one-tap projector patch applied")
