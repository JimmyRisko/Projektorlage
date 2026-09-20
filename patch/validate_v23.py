from pathlib import Path
import sys

root=Path(sys.argv[1])
main=(root/'app/src/main/java/se/projektorlage/app/MainActivity.java').read_text()
mpa=(root/'app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java').read_text()
mos=(root/'app/src/main/java/se/projektorlage/app/MirrorOverlayService.java').read_text()
svc=(root/'app/src/main/java/se/projektorlage/app/RotationService.java').read_text()
manifest=(root/'app/src/main/AndroidManifest.xml').read_text()
build=(root/'app/build.gradle').read_text()

checks = [
    ('single-app chooser', 'createConfigForUserChoice()' in mpa),
    ('no forced full-display chooser', 'createConfigForDefaultDisplay()' not in mpa),
    ('post-transform horizontal mirror', 'vTexCoord = vec2(1.0 - tc.x, tc.y)' in mos),
    ('normal texture coordinates', '0f, 1f,\n                 1f, 1f,\n                 0f, 0f,\n                 1f, 0f' in mos),
    ('mirror frame readiness', 'renderedFrames == 2' in mos and 'putBoolean("mirror_ready", true)' in mos),
    ('no secure mirror overlay', 'FLAG_KEEP_SCREEN_ON\n                | WindowManager.LayoutParams.FLAG_SECURE' not in mos),
    ('rotation readback verification', 'putBoolean("rotation_verified", verified)' in svc),
    ('brightness readback verification', 'putBoolean("brightness_verified", verified)' in svc),
    ('dynamic brightness max', 'return setBrightness(getDeviceBrightnessMaximum())' in svc),
    ('legacy white boost disabled', 'return "OK|BOOST_REMOVED"' in svc),
    ('permission activity survives rotation', 'android:configChanges="orientation|screenSize|keyboardHidden"' in manifest),
    ('main activity not manifest-locked portrait', 'android:name=".MainActivity"\n            android:exported="true">' in manifest),
    ('projector page stays portrait until START', 'private void showProjectorPanel() {\n        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);' in main),\n    ('actual display rotation verification', 'getDefaultDisplay().getRotation()' in svc and 'verifyDisplayRotation(target, 0)' in svc),
    ('v2.3 version', "versionName '2.3.0'" in build),
]
failed=[name for name,ok in checks if not ok]
for name,ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
if failed:
    raise SystemExit('Validation failed: ' + ', '.join(failed))
