from pathlib import Path
import sys

root = Path(sys.argv[1])
perm = (root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java").read_text()
mos = (root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java").read_text()
main = (root / "app/src/main/java/se/projektorlage/app/MainActivity.java").read_text()
build = (root / "app/build.gradle").read_text()

checks = [
    ("Android user-choice capture", "createConfigForUserChoice()" in perm),
    ("no forced whole-display capture", "createConfigForDefaultDisplay()" not in perm),
    ("explicit app selection guidance", "Välj EN APP" in perm and "Hela skärmen" in perm),
    ("simple TextureView output", "new TextureView(this)" in mos),
    ("horizontal mirror", "setScaleX(-1f)" in mos),
    ("no gray/white overlay boost", "light_boost_percent\", 0" in perm and "setBackgroundColor(Color.WHITE)" not in mos),
    ("true max window brightness", "BRIGHTNESS_OVERRIDE_FULL" in mos),
    ("no FLAG_SECURE", "FLAG_SECURE" not in mos),
    ("no skip screenshot hidden API", "setSkipScreenshot" not in mos),
    ("no HiddenApiBypass", "HiddenApiBypass" not in mos and "hiddenapibypass" not in build),
    ("whole-display feedback guard", "WHOLE_DISPLAY_SELECTED" in mos and "containsProbeMarker" in mos),
    ("probe uses one VirtualDisplay", mos.count("createVirtualDisplay(") == 1),
    ("probe retargets same VirtualDisplay", "virtualDisplay.setSurface(mirrorSurface)" in mos),
    ("output hidden until first real frame", "textureView.setAlpha(0f)" in mos and "textureView.setAlpha(1f)" in mos),
    ("app capture must verify before ready", "app_capture_verified" in mos and "mirror_ready" in mos),
    ("v2.7 version", "versionCode 27" in build and "versionName '2.7.0'" in build),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)

if failed:
    raise SystemExit("Validation failed: " + ", ".join(failed))
