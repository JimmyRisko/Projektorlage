from pathlib import Path
import sys

root = Path(sys.argv[1])
mos = (root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java").read_text()
perm = (root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java").read_text()
svc = (root / "app/src/main/java/se/projektorlage/app/RotationService.java").read_text()
build = (root / "app/build.gradle").read_text()

checks = [
    ("single-app capture retained", "createConfigForUserChoice()" in perm and "WHOLE_DISPLAY_SELECTED" in mos),
    ("SurfaceView output", "new SurfaceView(this)" in mos),
    ("TextureView code removed", "new TextureView(" not in mos and "private TextureView textureView" not in mos and "SurfaceTexture st" not in mos),
    ("horizontal mirror retained", "surfaceView.setScaleX(-1f)" in mos),
    ("no OpenGL renderer", "GLSurfaceView" not in mos and "GLES20" not in mos),
    ("brightness passthrough retained", "BRIGHTNESS_OVERRIDE_NONE" in mos and "projector_brightness_passthrough" in svc),
    ("same VirtualDisplay retarget", mos.count("createVirtualDisplay(") == 1 and "virtualDisplay.setSurface(output)" in mos),
    ("probe retained", "containsProbeMarker" in mos),
    ("surface lifecycle stable", "SURFACE_LIFECYCLE_FOLLOWS_ATTACHMENT" in mos),
    ("v2.12 version", "versionCode 32" in build and "versionName '2.12.0'" in build),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)

if failed:
    raise SystemExit("Validation failed: " + ", ".join(failed))
