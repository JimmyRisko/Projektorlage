from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
activity = root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java"
service = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

# Rename the button so the flow is explicit: Android chooses the single app.
s = main.read_text()
s = s.replace('TESTA SPEGELVÄND NETFLIX', 'SPEGELVÄND VALD APP', 1)
main.write_text(s)

# Do NOT launch Netflix after capture approval. On Android 14 QPR2+ the system's
# single-app sharing picker launches the app the user selected.
s = activity.read_text()
old = '''        Intent service = new Intent(this, MirrorOverlayService.class);
        service.setAction(MirrorOverlayService.ACTION_START);
        service.putExtra(MirrorOverlayService.EXTRA_RESULT_CODE, resultCode);
        service.putExtra(MirrorOverlayService.EXTRA_RESULT_DATA, data);
        startForegroundService(service);

        Intent netflix = getPackageManager().getLaunchIntentForPackage("com.netflix.mediaclient");
        if (netflix != null) {
            netflix.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(netflix);
        } else {
            Toast.makeText(this, "Netflix hittades inte.", Toast.LENGTH_LONG).show();
        }
        finish();'''
new = '''        Intent service = new Intent(this, MirrorOverlayService.class);
        service.setAction(MirrorOverlayService.ACTION_START);
        service.putExtra(MirrorOverlayService.EXTRA_RESULT_CODE, resultCode);
        service.putExtra(MirrorOverlayService.EXTRA_RESULT_DATA, data);
        startForegroundService(service);

        Toast.makeText(this,
                "Spegeltest startat. Om du valde 'Dela en app' speglas bara den valda appen.",
                Toast.LENGTH_LONG).show();
        finish();'''
s = replace_once(s, old, new, "remove forced Netflix launch")
activity.write_text(s)

s = service.read_text()

# Replace callback with resize-aware callback.
old = '''    private final MediaProjection.Callback projectionCallback = new MediaProjection.Callback() {
        @Override
        public void onStop() {
            stopSelf();
        }
    };'''
new = '''    private final MediaProjection.Callback projectionCallback = new MediaProjection.Callback() {
        @Override
        public void onStop() {
            stopSelf();
        }

        @Override
        public void onCapturedContentResize(int width, int height) {
            if (virtualDisplay == null || textureView == null || textureView.getSurfaceTexture() == null) return;
            try {
                int w = Math.max(1, width);
                int h = Math.max(1, height);
                int density = Math.max(1, getResources().getDisplayMetrics().densityDpi);
                SurfaceTexture st = textureView.getSurfaceTexture();
                st.setDefaultBufferSize(w, h);
                Surface newSurface = new Surface(st);
                virtualDisplay.resize(w, h, density);
                virtualDisplay.setSurface(newSurface);
                if (captureSurface != null && captureSurface != newSurface) {
                    try { captureSurface.release(); } catch (Exception ignored) {}
                }
                captureSurface = newSurface;
            } catch (Exception ignored) {
            }
        }
    };'''
s = replace_once(s, old, new, "projection resize callback")

# Do not recreate/resize based on overlay TextureView changes; captured-content callback owns that.
old = '''            @Override
            public void onSurfaceTextureSizeChanged(SurfaceTexture surfaceTexture, int width, int height) {
                resizeVirtualDisplay(surfaceTexture);
            }'''
new = '''            @Override
            public void onSurfaceTextureSizeChanged(SurfaceTexture surfaceTexture, int width, int height) {
                // Android 14+ reports the selected app's size through onCapturedContentResize().
            }'''
s = replace_once(s, old, new, "surface size callback")

# Remove FLAG_SECURE from our own output overlay. With single-app capture the overlay is
# outside the selected task and should not be part of the source capture.
old = '''        int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_SECURE;'''
new = '''        int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS;'''
s = replace_once(s, old, new, "overlay flags")

# Update notification text.
s = s.replace(
    'Skärmen visas horisontellt spegelvänd. Tryck för att stoppa.',
    'Den valda appen visas horisontellt spegelvänd. Tryck för att stoppa.',
    1
)

service.write_text(s)

s = build.read_text()
s = s.replace("versionCode 8", "versionCode 9", 1)
s = s.replace("versionName '0.8.0'", "versionName '0.9.0'", 1)
build.write_text(s)

print("v0.9 patch applied")
