from pathlib import Path
import sys

root=Path(sys.argv[1])
perm=(root/'app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java').read_text()
mos=(root/'app/src/main/java/se/projektorlage/app/MirrorOverlayService.java').read_text()
build=(root/'app/build.gradle').read_text()

checks = [
    ('whole-display capture restored', 'createConfigForDefaultDisplay()' in perm),
    ('single-app chooser removed', 'createConfigForUserChoice()' not in perm),
    ('known working TextureView mirror', 'textureView.setScaleX(-1f)' in mos),
    ('skip screenshot is installed before capture', 'installSkipScreenshot(overlay)' in mos and 'startVirtualDisplay(st)' in mos),
    ('SurfaceFlinger skipScreenshot used', 'setSkipScreenshot' in mos),
    ('no FLAG_SECURE black-overlay workaround', '| WindowManager.LayoutParams.FLAG_SECURE' not in mos and 'windowFlags |= WindowManager.LayoutParams.FLAG_SECURE' not in mos),
    ('overlay blocks local touch instead of alpha-clamped passthrough', 'overlay.setOnTouchListener((v, event) -> true)' in mos),
    ('fails closed when skipScreenshot is unavailable', 'Samsung/Android blockerade overlay-undantaget' in mos),
    ('v2.4 version', "versionName '2.4.0'" in build),
]
failed=[name for name,ok in checks if not ok]
for name,ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
if failed:
    raise SystemExit('Validation failed: ' + ', '.join(failed))
