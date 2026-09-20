from pathlib import Path
import sys

root=Path(sys.argv[1])
mos=(root/'app/src/main/java/se/projektorlage/app/MirrorOverlayService.java').read_text()
perm=(root/'app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java').read_text()
build=(root/'app/build.gradle').read_text()

checks = [
    ('HiddenApiBypass dependency', "org.lsposed.hiddenapibypass:hiddenapibypass:6.1" in build),
    ('HiddenApiBypass used for setSkipScreenshot', 'HiddenApiBypass.getDeclaredMethod' in mos and '"setSkipScreenshot"' in mos),
    ('whole display capture retained', 'createConfigForDefaultDisplay()' in perm),
    ('single app capture absent', 'createConfigForUserChoice()' not in perm),
    ('real capture verification present', 'verifyOverlayExclusion()' in mos and 'isMostlyMagenta' in mos),
    ('verification uses same VirtualDisplay token', mos.count('createVirtualDisplay(') == 1 and 'virtualDisplay.setSurface(output)' in mos),
    ('overlay is not trusted before verification', 'putBoolean("overlay_excluded", true)' in mos and 'verificationFinished' in mos),
    ('mirror output waits for verification', 'setVerificationMode(false)' in mos),
    ('no FLAG_SECURE workaround', '| WindowManager.LayoutParams.FLAG_SECURE' not in mos),
    ('v2.5 version', "versionName '2.5.0'" in build),
]
failed=[name for name,ok in checks if not ok]
for name,ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
if failed:
    raise SystemExit('Validation failed: ' + ', '.join(failed))
