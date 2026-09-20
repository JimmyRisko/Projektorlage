from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
activity = root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

# Main automatic projector mode: never add the white-lift overlay.
s = main.read_text()
s = s.replace('.putInt("light_boost_percent", 12)', '.putInt("light_boost_percent", 0)', 1)
main.write_text(s)

# Mirror launch path: same rule.
s = activity.read_text()
s = s.replace('.putInt("light_boost_percent", 12)', '.putInt("light_boost_percent", 0)', 1)
activity.write_text(s)

# Service fallback must also be zero so old/missing prefs cannot create the veil.
s = svc.read_text()
s = s.replace('getInt("light_boost_percent", 12)', 'getInt("light_boost_percent", 0)', 1)
svc.write_text(s)

# Mirror window itself should request true max brightness, not simulate brightness with white.
s = mirror.read_text()
needle = '        lp.gravity = Gravity.TOP | Gravity.START;\n        lp.setTitle("Projektorläge spegeltest");'
repl = '        lp.gravity = Gravity.TOP | Gravity.START;\n        lp.screenBrightness = 1.0f;\n        lp.setTitle("Projektorläge spegeltest");'
if needle not in s:
    raise SystemExit("Patch misslyckades: mirror window params")
s = s.replace(needle, repl, 1)
mirror.write_text(s)

# Version
b = build.read_text()
b = b.replace("versionCode 18", "versionCode 19", 1)
b = b.replace("versionName '1.8.0'", "versionName '1.9.0'", 1)
build.write_text(b)

print("v1.9 no-gray-veil brightness fix applied")
