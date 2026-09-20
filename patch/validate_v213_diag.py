from pathlib import Path
import sys

root=Path(sys.argv[1])
mos=(root/"app/src/main/java/se/projektorlage/app/MirrorOverlayService.java").read_text()
build=(root/"app/build.gradle").read_text()

checks=[
 ("v2.11 TextureView retained","new TextureView(this)" in mos),
 ("v2.11 mirror retained","textureView.setScaleX(-1f)" in mos),
 ("single VirtualDisplay retained",mos.count("createVirtualDisplay(")==1),
 ("diagnostic resize callback","capture_resize_" in mos),
 ("diagnostic visibility callback","capture_visibility_" in mos),
 ("diagnostic display snapshot","getDisplaySnapshot()" in mos),
 ("diagnostic event log","ProjektorDiag" in mos),
 ("no SurfaceView experiment","new SurfaceView(this)" not in mos),
 ("no GLSurfaceView experiment","GLSurfaceView" not in mos),
 ("v2.13 diagnostic version","versionCode 33" in build and "versionName '2.13.0-diag'" in build),
]
failed=[n for n,ok in checks if not ok]
for n,ok in checks: print(("PASS " if ok else "FAIL ")+n)
if failed: raise SystemExit("Validation failed: "+", ".join(failed))
