from pathlib import Path
import sys
root=Path(sys.argv[1])
b=(root/"app/build.gradle").read_text()
m=(root/"app/src/main/java/se/projektorlage/app/MirrorOverlayService.java").read_text()
ui=(root/"app/src/main/java/se/projektorlage/app/MainActivity.java").read_text()
checks=[
 ("unique D3 app id","se.projektorlage.diagnostic3" in b),
 ("D3 version","versionName 'D3-1.0'" in b),
 ("v2.11 TextureView retained","new TextureView(this)" in m),
 ("mirror retained","textureView.setScaleX(-1f)" in m),
 ("single projection VirtualDisplay retained",m.count("createVirtualDisplay(")==1),
 ("sample action","ACTION_SAMPLE_LUMINANCE" in m),
 ("ImageReader pre-texture sample","luminanceReader = ImageReader.newInstance" in m),
 ("VirtualDisplay temporary redirect","virtualDisplay.setSurface(luminanceReader.getSurface())" in m),
 ("mirror restore","virtualDisplay.setSurface(mirrorSurface)" in m),
 ("luma stats","luminance_pre_texture" in m and "nearBlackPct" in m and "brightPct" in m),
 ("sample timeout safety","no_frame_within_1500ms" in m),
 ("visible sample button","MÄT BILDSTRÖM NU" in ui),
 ("visible export button","KOPIERA DIAGNOSTIK / LOGG" in ui),
 ("no SurfaceView experiment","new SurfaceView(this)" not in m),
 ("no OpenGL experiment","GLSurfaceView" not in m),
]
bad=[n for n,x in checks if not x]
for n,x in checks: print(("PASS " if x else "FAIL ")+n)
if bad: raise SystemExit("D3 validation failed: "+", ".join(bad))
