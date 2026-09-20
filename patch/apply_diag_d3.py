from pathlib import Path
import sys

root=Path(sys.argv[1])
build=root/"app/build.gradle"
main=root/"app/src/main/java/se/projektorlage/app/MainActivity.java"
mirror=root/"app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
manifest=root/"app/src/main/AndroidManifest.xml"

# --- Unique D3 install identity ---
b=build.read_text()
for old in [
    'applicationId "se.projektorlage.diagnostic2"',
    "applicationId 'se.projektorlage.diagnostic2'"
]:
    if old in b:
        q='"' if '"' in old else "'"
        b=b.replace(old, f'applicationId {q}se.projektorlage.diagnostic3{q}',1)
        break
else:
    raise SystemExit("D3 applicationId source not found")
b=b.replace("versionName 'D2-1.0'","versionName 'D3-1.0'",1)
build.write_text(b)

mf=manifest.read_text()
mf=mf.replace('android:label="Projektorläge Diagnostik D2"',
              'android:label="Projektorläge Diagnostik D3"')
manifest.write_text(mf)

# --- Mirror service: one-frame pre-TextureView luminance sampler ---
s=mirror.read_text()

# Public diagnostic action.
s=s.replace(
'''    public static final String ACTION_PROFILE = "se.projektorlage.app.MIRROR_PROFILE";''',
'''    public static final String ACTION_PROFILE = "se.projektorlage.app.MIRROR_PROFILE";
    public static final String ACTION_SAMPLE_LUMINANCE =
            "se.projektorlage.app.MIRROR_SAMPLE_LUMINANCE";''',
1)

# Sampling fields.
s=s.replace(
'''    private int diagnosticVisibilityCount;
''',
'''    private int diagnosticVisibilityCount;
    private boolean luminanceSampleInProgress;
    private ImageReader luminanceReader;
''',
1)

# Handle action before ACTION_START guard.
needle='''        if (ACTION_PROFILE.equals(action)) {
            String profile = intent.getStringExtra(EXTRA_PROFILE);
            applyPictureProfile(profile);
            return START_NOT_STICKY;
        }

        if (!ACTION_START.equals(action)) return START_NOT_STICKY;'''
repl='''        if (ACTION_PROFILE.equals(action)) {
            String profile = intent.getStringExtra(EXTRA_PROFILE);
            applyPictureProfile(profile);
            return START_NOT_STICKY;
        }

        if (ACTION_SAMPLE_LUMINANCE.equals(action)) {
            sampleCapturedLuminance();
            return START_NOT_STICKY;
        }

        if (!ACTION_START.equals(action)) return START_NOT_STICKY;'''
if needle not in s:
    raise SystemExit("D3 action insertion point not found")
s=s.replace(needle,repl,1)

# Insert sampler before diagnostic display snapshot helper.
anchor='''    private String getDisplaySnapshot() {'''
if anchor not in s:
    raise SystemExit("D3 diagnostic helper anchor not found")

sampler=r'''    private void sampleCapturedLuminance() {
        if (luminanceSampleInProgress) {
            recordDiagnosticEvent("luminance_sample_skipped", "already_running");
            return;
        }
        if (virtualDisplay == null || textureView == null || !appCaptureVerified) {
            recordDiagnosticEvent("luminance_sample_failed", "mirror_not_ready");
            return;
        }

        SurfaceTexture st = textureView.getSurfaceTexture();
        if (st == null) {
            recordDiagnosticEvent("luminance_sample_failed", "texture_missing");
            return;
        }

        luminanceSampleInProgress = true;
        recordDiagnosticEvent("luminance_sample_begin", getDisplaySnapshot());

        try {
            luminanceReader = ImageReader.newInstance(
                    captureWidth,
                    captureHeight,
                    PixelFormat.RGBA_8888,
                    2);

            luminanceReader.setOnImageAvailableListener(reader -> {
                Image image = null;
                try {
                    image = reader.acquireLatestImage();
                    if (image == null) return;

                    String result = calculateLuminanceStats(image);
                    recordDiagnosticEvent("luminance_pre_texture", result);
                } catch (Throwable t) {
                    recordDiagnosticEvent(
                            "luminance_sample_failed",
                            t.getClass().getSimpleName());
                } finally {
                    if (image != null) {
                        try { image.close(); } catch (Throwable ignored) {}
                    }
                    mainHandler.post(this::restoreMirrorAfterLuminanceSample);
                }
            }, mainHandler);

            // Same MediaProjection and same VirtualDisplay: only redirect the
            // output briefly to ImageReader. This measures captured pixels before
            // TextureView without creating a second projection session.
            virtualDisplay.setSurface(null);
            virtualDisplay.setSurface(luminanceReader.getSurface());

            // Safety: never leave the display detached if the source does not
            // deliver a frame (for example protected/secure video behavior).
            mainHandler.postDelayed(() -> {
                if (luminanceSampleInProgress) {
                    recordDiagnosticEvent(
                            "luminance_sample_timeout",
                            "no_frame_within_1500ms");
                    restoreMirrorAfterLuminanceSample();
                }
            }, 1500L);
        } catch (Throwable t) {
            recordDiagnosticEvent(
                    "luminance_sample_failed",
                    t.getClass().getSimpleName());
            restoreMirrorAfterLuminanceSample();
        }
    }

    private String calculateLuminanceStats(Image image) {
        Image.Plane[] planes = image.getPlanes();
        if (planes == null || planes.length == 0) return "no_planes";

        Image.Plane plane = planes[0];
        ByteBuffer buffer = plane.getBuffer();
        int pixelStride = plane.getPixelStride();
        int rowStride = plane.getRowStride();
        int width = image.getWidth();
        int height = image.getHeight();

        if (buffer == null || pixelStride < 4 || rowStride <= 0) {
            return "invalid_plane";
        }

        long samples = 0L;
        double sum = 0.0;
        double sumSq = 0.0;
        int min = 255;
        int max = 0;
        long nearBlack = 0L;
        long dark = 0L;
        long mid = 0L;
        long bright = 0L;

        // Sample a regular grid across the complete captured frame. Around
        // 20k samples is enough for diagnostics without stressing the phone.
        int stepX = Math.max(1, width / 160);
        int stepY = Math.max(1, height / 90);

        for (int y = 0; y < height; y += stepY) {
            int row = y * rowStride;
            for (int x = 0; x < width; x += stepX) {
                int pos = row + x * pixelStride;
                if (pos < 0 || pos + 2 >= buffer.limit()) continue;

                int r = buffer.get(pos) & 0xff;
                int g = buffer.get(pos + 1) & 0xff;
                int b = buffer.get(pos + 2) & 0xff;

                // Rec.709 luma, rounded to 8-bit diagnostic value.
                int y8 = (int) Math.round(
                        0.2126 * r + 0.7152 * g + 0.0722 * b);
                y8 = Math.max(0, Math.min(255, y8));

                samples++;
                sum += y8;
                sumSq += (double) y8 * (double) y8;
                if (y8 < min) min = y8;
                if (y8 > max) max = y8;

                if (y8 <= 8) nearBlack++;
                if (y8 < 32) dark++;
                else if (y8 < 160) mid++;
                else bright++;
            }
        }

        if (samples == 0L) return "samples=0";

        double mean = sum / samples;
        double variance = Math.max(0.0, (sumSq / samples) - mean * mean);
        double std = Math.sqrt(variance);

        return "size=" + width + "x" + height
                + ",samples=" + samples
                + ",mean=" + String.format(java.util.Locale.US, "%.2f", mean)
                + ",std=" + String.format(java.util.Locale.US, "%.2f", std)
                + ",min=" + min
                + ",max=" + max
                + ",nearBlackPct=" + String.format(
                        java.util.Locale.US, "%.2f", 100.0 * nearBlack / samples)
                + ",darkPct=" + String.format(
                        java.util.Locale.US, "%.2f", 100.0 * dark / samples)
                + ",midPct=" + String.format(
                        java.util.Locale.US, "%.2f", 100.0 * mid / samples)
                + ",brightPct=" + String.format(
                        java.util.Locale.US, "%.2f", 100.0 * bright / samples);
    }

    private void restoreMirrorAfterLuminanceSample() {
        if (!luminanceSampleInProgress) return;
        luminanceSampleInProgress = false;

        try {
            SurfaceTexture st = textureView == null
                    ? null : textureView.getSurfaceTexture();

            if (virtualDisplay != null && st != null) {
                st.setDefaultBufferSize(captureWidth, captureHeight);

                if (mirrorSurface == null || !mirrorSurface.isValid()) {
                    if (mirrorSurface != null) {
                        try { mirrorSurface.release(); } catch (Throwable ignored) {}
                    }
                    mirrorSurface = new Surface(st);
                }

                virtualDisplay.setSurface(null);
                virtualDisplay.setSurface(mirrorSurface);
                recordDiagnosticEvent(
                        "luminance_sample_restored",
                        getDisplaySnapshot());
            } else {
                recordDiagnosticEvent(
                        "luminance_sample_restore_failed",
                        "surface_missing");
            }
        } catch (Throwable t) {
            recordDiagnosticEvent(
                    "luminance_sample_restore_failed",
                    t.getClass().getSimpleName());
        }

        if (luminanceReader != null) {
            try { luminanceReader.close(); } catch (Throwable ignored) {}
            luminanceReader = null;
        }
    }

'''
s=s.replace(anchor,sampler+anchor,1)

# Cleanup reader if service stops during a sample.
cleanup='''        if (probeReader != null) {
            try { probeReader.close(); } catch (Throwable ignored) {}
            probeReader = null;
        }
'''
cleanup_repl=cleanup+'''
        if (luminanceReader != null) {
            try { luminanceReader.close(); } catch (Throwable ignored) {}
            luminanceReader = null;
        }
        luminanceSampleInProgress = false;
'''
# Replace last/first release block only once; releaseCaptureResources has this exact code.
if cleanup not in s:
    raise SystemExit("D3 cleanup insertion point not found")
s=s.replace(cleanup,cleanup_repl,1)

mirror.write_text(s)

# --- Main UI: visible D3 label and measurement button ---
m=main.read_text()
m=m.replace("DIAGNOSTIK D2 • loggning aktiv",
            "DIAGNOSTIK D3 • mätning före TextureView",1)

needle='''        Button copyDiagnostics = makeButton("KOPIERA DIAGNOSTIK / LOGG");
        copyDiagnostics.setOnClickListener(v -> copyDiagnosticReport());
        panel.addView(copyDiagnostics, full(0, dp(16)));

        Button advancedToggle = makeButton("Avancerat");'''
repl='''        Button sampleLuminance = makeButton("MÄT BILDSTRÖM NU");
        sampleLuminance.setOnClickListener(v -> {
            Intent sampleIntent = new Intent(this, MirrorOverlayService.class);
            sampleIntent.setAction(MirrorOverlayService.ACTION_SAMPLE_LUMINANCE);
            try {
                startService(sampleIntent);
                android.widget.Toast.makeText(
                        this,
                        "Mäter fångad bild före TextureView…",
                        android.widget.Toast.LENGTH_SHORT).show();
            } catch (Exception e) {
                android.widget.Toast.makeText(
                        this,
                        "Kunde inte starta mätningen.",
                        android.widget.Toast.LENGTH_LONG).show();
            }
        });
        panel.addView(sampleLuminance, full(0, dp(10)));

        Button copyDiagnostics = makeButton("KOPIERA DIAGNOSTIK / LOGG");
        copyDiagnostics.setOnClickListener(v -> copyDiagnosticReport());
        panel.addView(copyDiagnostics, full(0, dp(16)));

        Button advancedToggle = makeButton("Avancerat");'''
if needle not in m:
    raise SystemExit("D3 measurement button insertion point not found")
m=m.replace(needle,repl,1)
main.write_text(m)

print("diagnostic D3 pre-TextureView luminance sampler applied")
