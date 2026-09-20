from pathlib import Path
import sys

root = Path(sys.argv[1])
mos = (root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java").read_text()
svc = (root / "app/src/main/java/se/projektorlage/app/RotationService.java").read_text()
perm = (root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java").read_text()
build = (root / "app/build.gradle").read_text()

enable_block = svc[svc.find("if (Settings.canDrawOverlays(this))"):svc.find("if (Settings.canDrawOverlays(this))")+1200]
kick_block = svc[svc.find("private void startBrightnessKick()"):svc.find("private void stopBrightnessKick()")]

checks = [
    ("v2.7 app-only capture retained", "createConfigForUserChoice()" in perm and "WHOLE_DISPLAY_SELECTED" in mos),
    ("TextureView architecture retained", "new TextureView(this)" in mos),
    ("horizontal mirror retained", "textureView.setScaleX(-1f)" in mos),
    ("no per-window brightness override", "BRIGHTNESS_OVERRIDE_NONE" in mos and "BRIGHTNESS_OVERRIDE_FULL" not in mos),
    ("startup uses brightness passthrough", "preserveCurrentBrightnessState()" in enable_block),
    ("startup does not force brightness", "forceProjectorBrightness()" not in enable_block),
    ("brightness kick disabled", "forceProjectorBrightness();" not in kick_block),
    ("stale brightness backup cleared", '.putBoolean("brightness_backup_valid", false)' in svc),
    ("no v2.8 RenderEffect", "RenderEffect" not in mos and "RuntimeShader" not in mos),
    ("no v2.9 GLSurfaceView", "GLSurfaceView" not in mos),
    ("single VirtualDisplay guard retained", mos.count("createVirtualDisplay(") == 1),
    ("v2.11 version", "versionCode 31" in build and "versionName '2.11.0'" in build),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)

if failed:
    raise SystemExit("Validation failed: " + ", ".join(failed))
