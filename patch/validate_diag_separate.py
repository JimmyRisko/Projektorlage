from pathlib import Path
import sys
root=Path(sys.argv[1])
b=(root/"app/build.gradle").read_text()
m=(root/"app/src/main/java/se/projektorlage/app/MirrorOverlayService.java").read_text()
checks=[
 ("separate app id",'applicationId "se.projektorlage.diagnostic"' in b or "applicationId 'se.projektorlage.diagnostic'" in b),
 ("diagnostic version","versionCode 1" in b and "versionName '1.0.0-diag'" in b),
 ("v2.11 TextureView retained","new TextureView(this)" in m),
 ("mirror retained","textureView.setScaleX(-1f)" in m),
 ("diagnostics retained","capture_resize_" in m and "capture_visibility_" in m and "ProjektorDiag" in m),
 ("no SurfaceView experiment","new SurfaceView(this)" not in m),
 ("no OpenGL experiment","GLSurfaceView" not in m),
]
bad=[n for n,x in checks if not x]
for n,x in checks: print(("PASS " if x else "FAIL ")+n)
if bad: raise SystemExit("Validation failed: "+", ".join(bad))
