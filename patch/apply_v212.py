from pathlib import Path
import sys

root = Path(sys.argv[1])
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

s = mirror.read_text()

# Imports: replace TextureView/SurfaceTexture output with SurfaceView.
s = s.replace("import android.graphics.SurfaceTexture;\n", "")
s = s.replace(
    "import android.view.TextureView;\n",
    "import android.view.SurfaceHolder;\nimport android.view.SurfaceView;\n",
    1
)

# Fields.
s = s.replace(
    "    private TextureView textureView;\n",
    "    private SurfaceView surfaceView;\n",
    1
)
s = s.replace(
    "    private Surface mirrorSurface;\n",
    "",
    1
)

# Resize callback: SurfaceView buffer tracks capture size.
old_resize = '''            mainHandler.post(() -> {
                try {
                    SurfaceTexture st = textureView == null ? null : textureView.getSurfaceTexture();
                    if (st != null) st.setDefaultBufferSize(captureWidth, captureHeight);
                    if (virtualDisplay != null) {
                        virtualDisplay.resize(captureWidth, captureHeight, densityDpi);
                    }
                } catch (Throwable ignored) {
                }
            });'''
new_resize = '''            mainHandler.post(() -> {
                try {
                    if (surfaceView != null) {
                        surfaceView.getHolder().setFixedSize(captureWidth, captureHeight);
                    }
                    if (virtualDisplay != null) {
                        virtualDisplay.resize(captureWidth, captureHeight, densityDpi);
                    }
                } catch (Throwable ignored) {
                }
            });'''
if old_resize not in s:
    raise SystemExit("v2.12: resize callback block not found")
s = s.replace(old_resize, new_resize, 1)

# Replace TextureView creation/listener with SurfaceView.
start = s.find("        textureView = new TextureView(this);")
end = s.find("        try {\n            windowManager.addView(overlay, lp);", start)
if start < 0 or end < 0:
    raise SystemExit("v2.12: TextureView creation block not found")

old_block = s[start:end]
new_block = r'''        surfaceView = new SurfaceView(this);

        // Keep the exact horizontal mirror that worked in v2.7, but move the
        // output onto SurfaceView so HDR video is not forced through TextureView's
        // HDR->SDR conversion path.
        surfaceView.setScaleX(-1f);

        if (android.os.Build.VERSION.SDK_INT >= 34) {
            surfaceView.setSurfaceLifecycle(
                    SurfaceView.SURFACE_LIFECYCLE_FOLLOWS_ATTACHMENT);
        }

        overlay.addView(surfaceView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        addProbeMarker();

        int type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
        int windowFlags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON;

        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                type,
                windowFlags,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE;
        lp.setTitle("Projektorläge HDR-spegel");

        surfaceView.getHolder().addCallback(new SurfaceHolder.Callback() {
            @Override
            public void surfaceCreated(SurfaceHolder holder) {
                try {
                    holder.setFixedSize(captureWidth, captureHeight);
                } catch (Throwable ignored) {
                }
                startCaptureProbe();
            }

            @Override
            public void surfaceChanged(
                    SurfaceHolder holder, int format, int width, int height) {
            }

            @Override
            public void surfaceDestroyed(SurfaceHolder holder) {
                releaseCaptureResources();
            }
        });

'''
s = s[:start] + new_block + s[end:]

# Replace probe starter signature/body prelude.
s = s.replace(
    "    private void startCaptureProbe(SurfaceTexture st) {\n"
    "        if (projection == null || st == null || virtualDisplay != null) return;\n\n"
    "        st.setDefaultBufferSize(captureWidth, captureHeight);\n\n",
    "    private void startCaptureProbe() {\n"
    "        if (projection == null || surfaceView == null || virtualDisplay != null) return;\n\n",
    1
)

# Replace TextureView output switch method.
method_start = s.find("    private void switchProbeToMirrorSurface() {")
method_end = s.find("    private void setMirrorError(", method_start)
if method_start < 0 or method_end < 0:
    raise SystemExit("v2.12: switchProbeToMirrorSurface block not found")

new_switch = r'''    private void switchProbeToMirrorSurface() {
        if (!appCaptureVerified || virtualDisplay == null || surfaceView == null) return;

        Surface output = surfaceView.getHolder().getSurface();
        if (output == null || !output.isValid()) {
            setMirrorError(
                    "Spegelytan försvann innan bilden startade.",
                    "OUTPUT_SURFACE_MISSING");
            stopSelf();
            return;
        }

        try {
            if (probeMarker != null && overlay != null) {
                overlay.removeView(probeMarker);
                probeMarker = null;
            }

            surfaceView.getHolder().setFixedSize(captureWidth, captureHeight);

            // Android 14+: keep the same VirtualDisplay/token and only retarget
            // its Surface. This preserves the working single-app capture path.
            virtualDisplay.setSurface(null);
            virtualDisplay.resize(captureWidth, captureHeight, densityDpi);
            virtualDisplay.setSurface(output);

            if (probeReader != null) {
                try { probeReader.close(); } catch (Throwable ignored) {}
                probeReader = null;
            }

            // The Surface is valid and the app-only probe has passed. We do not
            // inspect/transform the video pixels, which is exactly what lets HDR
            // stay on the platform SurfaceView path.
            mainHandler.postDelayed(() -> {
                if (surfaceView == null || virtualDisplay == null) return;
                getSharedPreferences("state", MODE_PRIVATE).edit()
                        .putBoolean("mirror_ready", true)
                        .putBoolean("app_capture_verified", true)
                        .remove("mirror_error")
                        .remove("mirror_error_code")
                        .apply();
            }, 250L);
        } catch (Throwable t) {
            setMirrorError(
                    "Kunde inte växla till HDR-spegelbilden.",
                    "SURFACE_SWITCH_FAILED");
            stopSelf();
        }
    }

'''
s = s[:method_start] + new_switch + s[method_end:]

# Remove mirrorSurface cleanup, already removed field but old cleanup may remain.
s = s.replace(
'''        if (mirrorSurface != null) {
            try { mirrorSurface.release(); } catch (Throwable ignored) {}
            mirrorSurface = null;
        }

''',
"",
1)

# Cleanup field name.
s = s.replace(
    "        textureView = null;\n",
    "        surfaceView = null;\n",
    1
)

# Sanity: old output APIs must be gone.
if "TextureView" in s or "SurfaceTexture" in s:
    raise SystemExit("v2.12: old TextureView/SurfaceTexture references remain")

mirror.write_text(s)

b = build.read_text()
b = b.replace("versionCode 31", "versionCode 32", 1)
b = b.replace("versionName '2.11.0'", "versionName '2.12.0'", 1)
build.write_text(b)

print("v2.12 SurfaceView HDR output applied")
