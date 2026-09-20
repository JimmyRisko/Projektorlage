from pathlib import Path
import sys

root = Path(sys.argv[1])
mos = (root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java").read_text()
perm = (root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java").read_text()
svc = (root / "app/src/main/java/se/projektorlage/app/RotationService.java").read_text()
build = (root / "app/build.gradle").read_text()

checks = [
    ("app-only capture retained", "createConfigForUserChoice()" in perm and "WHOLE_DISPLAY_SELECTED" in mos),
    ("TextureView removed", "TextureView" not in mos),
    ("GLSurfaceView renderer", "new GLSurfaceView(this)" in mos and "MirrorRenderer implements GLSurfaceView.Renderer" in mos),
    ("external OES input", "GL_TEXTURE_EXTERNAL_OES" in mos and "samplerExternalOES" in mos),
    ("horizontal mirror retained", "vTexCoord = vec2(1.0 - tc.x, tc.y)" in mos),
    ("GPU luminance lift", "pow(clamp(lum, 0.0, 1.0), uGamma)" in mos),
    ("black floor preserved", "lum <= uShadowFloor" in mos),
    ("no blend dimming", "glDisable(GLES20.GL_BLEND)" in mos),
    ("8-bit RGBA EGL", "setEGLConfigChooser(8, 8, 8, 8, 0, 0)" in mos),
    ("full panel brightness retained", "BRIGHTNESS_OVERRIDE_FULL" in mos),
    ("adaptive Samsung brightness retained", "projector_adaptive_brightness_preserved" in svc),
    ("single VirtualDisplay probe retained", mos.count("createVirtualDisplay(") == 1),
    ("v2.9 version", "versionCode 29" in build and "versionName '2.9.0'" in build),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)

if failed:
    raise SystemExit("Validation failed: " + ", ".join(failed))
