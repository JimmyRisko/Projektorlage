from pathlib import Path
import sys

root = Path(sys.argv[1])
perm = (root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java").read_text()
mos = (root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java").read_text()
svc = (root / "app/src/main/java/se/projektorlage/app/RotationService.java").read_text()
build = (root / "app/build.gradle").read_text()

checks = [
    ("v2.7 app-only capture retained", "createConfigForUserChoice()" in perm and "WHOLE_DISPLAY_SELECTED" in mos),
    ("mirror transform retained", "setScaleX(-1f)" in mos),
    ("adaptive brightness preserved", "projector_adaptive_brightness_preserved" in svc and "SCREEN_BRIGHTNESS_MODE_AUTOMATIC" in svc),
    ("manual-mode max still supported", "SCREEN_BRIGHTNESS" in svc and "getDeviceBrightnessMaximum()" in svc),
    ("window brightness full", "BRIGHTNESS_OVERRIDE_FULL" in mos),
    ("SDR HDR-headroom guard", "setDesiredHdrHeadroom(1.0f)" in mos),
    ("black-preserving gamma", "pow(lum, gamma)" in mos and "if (lum <= 0.001) return c" in mos),
    ("no white overlay", "setBackgroundColor(Color.WHITE)" not in mos),
    ("projector profile default", 'getString("picture_profile", "PROJECTOR")' in mos and '.putString("picture_profile", "PROJECTOR")' in perm),
    ("profile switching restored", "applyPictureProfile(profile)" in mos),
    ("working capture probe retained", "containsProbeMarker" in mos and mos.count("createVirtualDisplay(") == 1),
    ("v2.8 version", "versionCode 28" in build and "versionName '2.8.0'" in build),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)

if failed:
    raise SystemExit("Validation failed: " + ", ".join(failed))
