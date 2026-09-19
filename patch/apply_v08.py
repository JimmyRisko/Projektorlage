from pathlib import Path
import sys

root = Path(sys.argv[1])
service = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

s = service.read_text()

s = replace_once(s,
'''            @Override
            public void onSurfaceTextureSizeChanged(SurfaceTexture surfaceTexture, int width, int height) {
                restartVirtualDisplay(surfaceTexture);
            }''',
'''            @Override
            public void onSurfaceTextureSizeChanged(SurfaceTexture surfaceTexture, int width, int height) {
                resizeVirtualDisplay(surfaceTexture);
            }''',
"surface resize callback")

s = replace_once(s,
'''    private void restartVirtualDisplay(SurfaceTexture surfaceTexture) {
        startVirtualDisplay(surfaceTexture);
    }''',
'''    private void resizeVirtualDisplay(SurfaceTexture surfaceTexture) {
        if (virtualDisplay == null || surfaceTexture == null) return;

        try {
            int width = Math.max(1, getResources().getDisplayMetrics().widthPixels);
            int height = Math.max(1, getResources().getDisplayMetrics().heightPixels);
            int density = Math.max(1, getResources().getDisplayMetrics().densityDpi);

            surfaceTexture.setDefaultBufferSize(width, height);

            Surface newSurface = new Surface(surfaceTexture);
            virtualDisplay.resize(width, height, density);
            virtualDisplay.setSurface(newSurface);

            if (captureSurface != null && captureSurface != newSurface) {
                try { captureSurface.release(); } catch (Exception ignored) {}
            }
            captureSurface = newSurface;
        } catch (Exception ignored) {
        }
    }''',
"resize virtual display")

# Harden the initial create so a runtime projection failure does not crash-loop the service.
s = replace_once(s,
'''        virtualDisplay = projection.createVirtualDisplay(
                "ProjektorlageMirror",
                width,
                height,
                density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                captureSurface,
                null,
                null);''',
'''        try {
            virtualDisplay = projection.createVirtualDisplay(
                    "ProjektorlageMirror",
                    width,
                    height,
                    density,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    captureSurface,
                    null,
                    null);
        } catch (Exception e) {
            stopSelf();
        }''',
"guard createVirtualDisplay")

service.write_text(s)

s = build.read_text()
s = s.replace("versionCode 7", "versionCode 8", 1)
s = s.replace("versionName '0.7.0'", "versionName '0.8.0'", 1)
build.write_text(s)

print("v0.8 patch applied")
