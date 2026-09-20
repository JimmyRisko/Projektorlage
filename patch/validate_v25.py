from pathlib import Path
import sys

root=Path(sys.argv[1])
perm=(root/'app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java').read_text()
mos=(root/'app/src/main/java/se/projektorlage/app/MirrorOverlayService.java').read_text()
svc=(root/'app/src/main/java/se/projektorlage/app/RotationService.java').read_text()
build=(root/'app/build.gradle').read_text()

checks = [
    ('whole-display capture', 'createConfigForDefaultDisplay()' in perm),
    ('Netflix gated behind verified mirror', 'waitForMirrorThenLaunchNetflix' in perm and 'prefs.getBoolean("mirror_ready", false)' in perm and 'prefs.getBoolean("overlay_excluded", false)' in perm),
    ('GLSurfaceView output', 'new GLSurfaceView(this)' in mos),
    ('public SurfaceView SurfaceControl path', 'glView.getSurfaceControl()' in mos),
    ('no ViewRootImpl reflection', 'getViewRootImpl' not in mos and 'Class.forName("android.view.ViewRootImpl")' not in mos),
    ('no BLAST reflection', 'BLASTBufferQueue' not in mos),
    ('setSkipScreenshot only hidden operation', 'setSkipScreenshot' in mos),
    ('no FLAG_SECURE overlay', 'FLAG_SECURE' not in mos),
    ('translucent root avoids black capture rectangle', 'PixelFormat.TRANSLUCENT' in mos),
    ('mirror after SurfaceTexture transform', 'vTexCoord = vec2(1.0 - tc.x, tc.y)' in mos),
    ('capture waits for excluded output surface', 'skipScreenshotInstalled' in mos and 'maybeStartCapture()' in mos),
    ('real frame readiness', 'renderedFrames == 2' in mos and 'putBoolean("mirror_ready", true)' in mos),
    ('rotation readback retained', 'getDefaultDisplay().getRotation()' in svc),
    ('brightness readback retained', 'putBoolean("brightness_verified", verified)' in svc),
    ('Android 10+ minimum', 'minSdk 29' in build),
    ('v2.5 version', "versionName '2.5.0'" in build),
]
failed=[name for name,ok in checks if not ok]
for name,ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
if failed:
    raise SystemExit('Validation failed: ' + ', '.join(failed))
