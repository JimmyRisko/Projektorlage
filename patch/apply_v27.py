from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
perm = root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java"
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

# v2.7: stop trying to mirror the whole display back onto itself.
# Android 14+ can capture one selected app. The projector overlay then sits
# outside the captured task, so there is no feedback loop and no hidden API.
# A short two-colour probe detects accidental "whole screen" selection before
# any captured frame is shown.

perm.write_text(r'''package se.projektorlage.app;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.projection.MediaProjectionConfig;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.widget.Toast;

public class MirrorPermissionActivity extends Activity {
    private static final int REQ_CAPTURE = 9021;
    private static final String NETFLIX_PACKAGE = "com.netflix.mediaclient";

    private final Handler handler = new Handler(Looper.getMainLooper());
    private MediaProjectionManager projectionManager;
    private boolean captureRequested;
    private boolean overlaySettingsOpened;
    private boolean writeSettingsOpened;
    private int captureResultCode;
    private Intent captureResultData;
    private long setupDeadline;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        projectionManager = (MediaProjectionManager)
                getSystemService(MEDIA_PROJECTION_SERVICE);
        continueSetup();
    }

    @Override
    protected void onResume() {
        super.onResume();

        if (overlaySettingsOpened) {
            overlaySettingsOpened = false;
            if (!Settings.canDrawOverlays(this)) {
                fail("ERR_BASE_SETUP",
                        "Tillåt 'Visa över andra appar' för att använda projektorläget.");
                return;
            }
            continueSetup();
            return;
        }

        if (writeSettingsOpened) {
            writeSettingsOpened = false;
            if (!Settings.System.canWrite(this)) {
                fail("ERR_BASE_SETUP",
                        "Tillåt 'Ändra systeminställningar' för bildriktning och ljusstyrka.");
                return;
            }
            continueSetup();
        }
    }

    private void continueSetup() {
        if (!Settings.canDrawOverlays(this)) {
            overlaySettingsOpened = true;
            startActivity(new Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName())));
            return;
        }

        if (!Settings.System.canWrite(this)) {
            writeSettingsOpened = true;
            startActivity(new Intent(
                    Settings.ACTION_MANAGE_WRITE_SETTINGS,
                    Uri.parse("package:" + getPackageName())));
            return;
        }

        if (captureRequested) return;

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            fail("ERR_CAPTURE_UNSUPPORTED",
                    "Den här speglingen kräver Android 14 eller senare.");
            return;
        }

        captureRequested = true;
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("startup_state", "WAITING_FOR_CAPTURE")
                .putBoolean("mirror_ready", false)
                .putBoolean("app_capture_verified", false)
                .remove("mirror_error")
                .remove("mirror_error_code")
                .apply();

        Toast.makeText(this,
                "Välj EN APP i Android-rutan och välj sedan Netflix. Välj inte 'Hela skärmen'.",
                Toast.LENGTH_LONG).show();

        startActivityForResult(
                projectionManager.createScreenCaptureIntent(
                        MediaProjectionConfig.createConfigForUserChoice()),
                REQ_CAPTURE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_CAPTURE) return;

        if (resultCode != RESULT_OK || data == null) {
            fail("ERR_CAPTURE_CANCELLED", "Projektorstarten avbröts.");
            return;
        }

        captureResultCode = resultCode;
        captureResultData = data;

        SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);
        prefs.edit()
                .putString("rotation_mode", "REVERSE")
                .putInt("light_boost_percent", 0)
                .putString("picture_profile", "NATURAL")
                .putBoolean("auto_launch_netflix", false)
                .putBoolean("rotation_verified", false)
                .putBoolean("brightness_verified", false)
                .putBoolean("mirror_ready", false)
                .putBoolean("app_capture_verified", false)
                .remove("mirror_error")
                .remove("mirror_error_code")
                .putString("startup_state", "CONFIGURING_PHONE")
                .apply();

        Intent projector = new Intent(this, RotationService.class);
        projector.setAction(RotationService.ACTION_ENABLE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(projector);
        } else {
            startService(projector);
        }

        setupDeadline = System.currentTimeMillis() + 4500L;
        handler.post(this::waitForBaseSetup);
    }

    private void waitForBaseSetup() {
        SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);
        boolean enabled = prefs.getBoolean("enabled", false);
        boolean rotationOk = prefs.getBoolean("rotation_verified", false);
        boolean brightnessOk = prefs.getBoolean("brightness_verified", false);

        if (enabled && rotationOk && brightnessOk) {
            startMirrorAndNetflix();
            return;
        }

        if (System.currentTimeMillis() >= setupDeadline) {
            failAndRestore("ERR_BASE_SETUP",
                    "Projektorläge kunde inte verifiera bildriktning och maxljus.");
            return;
        }

        handler.postDelayed(this::waitForBaseSetup, 150L);
    }

    private void startMirrorAndNetflix() {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("startup_state", "STARTING_MIRROR")
                .apply();

        Intent mirrorIntent = new Intent(this, MirrorOverlayService.class);
        mirrorIntent.setAction(MirrorOverlayService.ACTION_START);
        mirrorIntent.putExtra(MirrorOverlayService.EXTRA_RESULT_CODE, captureResultCode);
        mirrorIntent.putExtra(MirrorOverlayService.EXTRA_RESULT_DATA, captureResultData);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(mirrorIntent);
        } else {
            startService(mirrorIntent);
        }

        Intent netflix = getPackageManager().getLaunchIntentForPackage(NETFLIX_PACKAGE);
        if (netflix == null) {
            failAndRestore("ERR_MIRROR", "Netflix-appen hittades inte på mobilen.");
            return;
        }

        netflix.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        startActivity(netflix);

        setupDeadline = System.currentTimeMillis() + 8000L;
        handler.postDelayed(this::waitForMirror, 200L);
    }

    private void waitForMirror() {
        SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);

        if (prefs.getBoolean("mirror_ready", false)
                && prefs.getBoolean("app_capture_verified", false)) {
            prefs.edit().putString("startup_state", "READY").apply();
            finish();
            return;
        }

        String mirrorError = prefs.getString("mirror_error", "");
        if (!mirrorError.isEmpty()) {
            failAndRestore("ERR_MIRROR", mirrorError);
            return;
        }

        if (System.currentTimeMillis() >= setupDeadline) {
            failAndRestore("ERR_MIRROR",
                    "Ingen bild kom fram. Starta igen och välj EN APP → Netflix i Android-rutan.");
            return;
        }

        handler.postDelayed(this::waitForMirror, 200L);
    }

    private void fail(String state, String message) {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("startup_state", state)
                .apply();
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
        finish();
    }

    private void failAndRestore(String state, String message) {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("startup_state", state)
                .apply();

        Toast.makeText(this, message, Toast.LENGTH_LONG).show();

        Intent stopMirror = new Intent(this, MirrorOverlayService.class);
        stopMirror.setAction(MirrorOverlayService.ACTION_STOP);
        try { startService(stopMirror); } catch (Exception ignored) {}

        Intent stopProjector = new Intent(this, RotationService.class);
        stopProjector.setAction(RotationService.ACTION_DISABLE);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(stopProjector);
            } else {
                startService(stopProjector);
            }
        } catch (Exception ignored) {}

        finish();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
}
''')

mirror.write_text(r'''package se.projektorlage.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.SurfaceTexture;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;

import java.nio.ByteBuffer;

public class MirrorOverlayService extends Service {
    public static final String ACTION_START = "se.projektorlage.app.MIRROR_START";
    public static final String ACTION_STOP = "se.projektorlage.app.MIRROR_STOP";
    public static final String ACTION_PROFILE = "se.projektorlage.app.MIRROR_PROFILE";
    public static final String EXTRA_PROFILE = "picture_profile";
    public static final String EXTRA_RESULT_CODE = "result_code";
    public static final String EXTRA_RESULT_DATA = "result_data";

    private static final int NOTIFICATION_ID = 707;
    private static final String CHANNEL_ID = "mirror_projection";

    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private WindowManager windowManager;
    private FrameLayout overlay;
    private TextureView textureView;
    private FrameLayout probeMarker;

    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader probeReader;
    private Surface mirrorSurface;

    private boolean intentionalStop;
    private boolean probeFinished;
    private boolean appCaptureVerified;
    private int probeFrames;
    private int updatedFrames;

    private int captureWidth;
    private int captureHeight;
    private int densityDpi;

    private final MediaProjection.Callback projectionCallback = new MediaProjection.Callback() {
        @Override
        public void onStop() {
            if (!intentionalStop) {
                setMirrorError("Skärmdelningen stoppades.", "PROJECTION_STOPPED");
            }
            stopSelf();
        }

        @Override
        public void onCapturedContentResize(int width, int height) {
            if (width <= 0 || height <= 0) return;
            captureWidth = width;
            captureHeight = height;

            if (!probeFinished) return;

            mainHandler.post(() -> {
                try {
                    SurfaceTexture st = textureView == null ? null : textureView.getSurfaceTexture();
                    if (st != null) st.setDefaultBufferSize(captureWidth, captureHeight);
                    if (virtualDisplay != null) {
                        virtualDisplay.resize(captureWidth, captureHeight, densityDpi);
                    }
                } catch (Throwable ignored) {
                }
            });
        }

        @Override
        public void onCapturedContentVisibilityChanged(boolean isVisible) {
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("captured_content_visible", isVisible)
                    .apply();
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_NOT_STICKY;

        String action = intent.getAction();

        if (ACTION_STOP.equals(action)) {
            intentionalStop = true;
            stopSelf();
            return START_NOT_STICKY;
        }

        if (ACTION_PROFILE.equals(action)) {
            return START_NOT_STICKY;
        }

        if (!ACTION_START.equals(action)) return START_NOT_STICKY;

        startForeground(NOTIFICATION_ID, buildNotification());

        int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
        Intent resultData = intent.getParcelableExtra(EXTRA_RESULT_DATA);

        if (resultCode == 0 || resultData == null) {
            setMirrorError("Saknar skärmdelningsbehörighet.", "NO_CAPTURE_PERMISSION");
            stopSelf();
            return START_NOT_STICKY;
        }

        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putBoolean("mirror_ready", false)
                .putBoolean("app_capture_verified", false)
                .remove("mirror_error")
                .remove("mirror_error_code")
                .apply();

        MediaProjectionManager manager = (MediaProjectionManager)
                getSystemService(MEDIA_PROJECTION_SERVICE);
        projection = manager.getMediaProjection(resultCode, resultData);

        if (projection == null) {
            setMirrorError("Kunde inte starta skärmdelningen.", "PROJECTION_NULL");
            stopSelf();
            return START_NOT_STICKY;
        }

        projection.registerCallback(projectionCallback, mainHandler);
        createMirrorOverlay();
        return START_NOT_STICKY;
    }

    private void createMirrorOverlay() {
        removeOverlayOnly();

        captureWidth = Math.max(1, getResources().getDisplayMetrics().widthPixels);
        captureHeight = Math.max(1, getResources().getDisplayMetrics().heightPixels);
        densityDpi = Math.max(1, getResources().getDisplayMetrics().densityDpi);

        overlay = new FrameLayout(this);
        overlay.setBackgroundColor(Color.TRANSPARENT);

        textureView = new TextureView(this);
        textureView.setOpaque(true);
        textureView.setScaleX(-1f);
        textureView.setAlpha(0f);

        overlay.addView(textureView, new FrameLayout.LayoutParams(
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
        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL;
        lp.setTitle("Projektorläge spegel");

        textureView.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
            @Override
            public void onSurfaceTextureAvailable(SurfaceTexture st, int width, int height) {
                startCaptureProbe(st);
            }

            @Override
            public void onSurfaceTextureSizeChanged(SurfaceTexture st, int width, int height) {
                if (!probeFinished) return;
                try {
                    st.setDefaultBufferSize(captureWidth, captureHeight);
                } catch (Throwable ignored) {
                }
            }

            @Override
            public boolean onSurfaceTextureDestroyed(SurfaceTexture st) {
                releaseCaptureResources();
                return true;
            }

            @Override
            public void onSurfaceTextureUpdated(SurfaceTexture st) {
                if (!appCaptureVerified) return;

                updatedFrames++;
                if (updatedFrames == 1) {
                    textureView.setAlpha(1f);
                }

                if (updatedFrames == 2) {
                    getSharedPreferences("state", MODE_PRIVATE).edit()
                            .putBoolean("mirror_ready", true)
                            .putBoolean("app_capture_verified", true)
                            .remove("mirror_error")
                            .remove("mirror_error_code")
                            .apply();
                }
            }
        });

        try {
            windowManager.addView(overlay, lp);
        } catch (Throwable t) {
            setMirrorError("Kunde inte visa spegelytan.", "OVERLAY_FAILED");
            stopSelf();
        }
    }

    private void addProbeMarker() {
        probeMarker = new FrameLayout(this);

        int square = dp(14);
        FrameLayout.LayoutParams markerLp = new FrameLayout.LayoutParams(
                square * 2, square, Gravity.CENTER);
        overlay.addView(probeMarker, markerLp);

        View magenta = new View(this);
        magenta.setBackgroundColor(Color.rgb(255, 0, 255));
        probeMarker.addView(magenta, new FrameLayout.LayoutParams(square, square));

        View cyan = new View(this);
        cyan.setBackgroundColor(Color.rgb(0, 255, 255));
        FrameLayout.LayoutParams cyanLp = new FrameLayout.LayoutParams(square, square);
        cyanLp.leftMargin = square;
        probeMarker.addView(cyan, cyanLp);
    }

    private void startCaptureProbe(SurfaceTexture st) {
        if (projection == null || st == null || virtualDisplay != null) return;

        st.setDefaultBufferSize(captureWidth, captureHeight);

        try {
            probeReader = ImageReader.newInstance(
                    captureWidth,
                    captureHeight,
                    PixelFormat.RGBA_8888,
                    2);

            probeReader.setOnImageAvailableListener(this::inspectProbeFrame, mainHandler);

            virtualDisplay = projection.createVirtualDisplay(
                    "ProjektorlageMirror",
                    captureWidth,
                    captureHeight,
                    densityDpi,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    probeReader.getSurface(),
                    null,
                    mainHandler);
        } catch (Throwable t) {
            setMirrorError("Kunde inte skapa spegelströmmen.", "VIRTUAL_DISPLAY_FAILED");
            stopSelf();
        }
    }

    private void inspectProbeFrame(ImageReader reader) {
        if (probeFinished) return;

        Image image = null;
        try {
            image = reader.acquireLatestImage();
            if (image == null) return;

            probeFrames++;

            if (containsProbeMarker(image)) {
                probeFinished = true;
                setMirrorError(
                        "Välj EN APP i Android-rutan – inte 'Hela skärmen'.",
                        "WHOLE_DISPLAY_SELECTED");
                stopSelf();
                return;
            }

            if (probeFrames >= 5) {
                probeFinished = true;
                appCaptureVerified = true;

                getSharedPreferences("state", MODE_PRIVATE).edit()
                        .putBoolean("app_capture_verified", true)
                        .apply();

                mainHandler.post(this::switchProbeToMirrorSurface);
            }
        } catch (Throwable t) {
            setMirrorError("Kunde inte verifiera vald skärmdelning.", "PROBE_FAILED");
            stopSelf();
        } finally {
            if (image != null) {
                try { image.close(); } catch (Throwable ignored) {}
            }
        }
    }

    private boolean containsProbeMarker(Image image) {
        Image.Plane[] planes = image.getPlanes();
        if (planes == null || planes.length == 0) return false;

        Image.Plane plane = planes[0];
        ByteBuffer buffer = plane.getBuffer();
        int pixelStride = plane.getPixelStride();
        int rowStride = plane.getRowStride();
        int width = image.getWidth();
        int height = image.getHeight();

        if (buffer == null || pixelStride < 4 || rowStride <= 0) return false;

        int x0 = Math.max(0, width * 35 / 100);
        int x1 = Math.min(width, width * 65 / 100);
        int y0 = Math.max(0, height * 35 / 100);
        int y1 = Math.min(height, height * 65 / 100);

        int magentaHits = 0;
        int cyanHits = 0;
        int step = Math.max(2, Math.min(width, height) / 360);

        for (int y = y0; y < y1; y += step) {
            int row = y * rowStride;
            for (int x = x0; x < x1; x += step) {
                int pos = row + x * pixelStride;
                if (pos < 0 || pos + 2 >= buffer.limit()) continue;

                int r = buffer.get(pos) & 0xff;
                int g = buffer.get(pos + 1) & 0xff;
                int b = buffer.get(pos + 2) & 0xff;

                if (r > 235 && g < 30 && b > 235) {
                    magentaHits++;
                } else if (r < 30 && g > 235 && b > 235) {
                    cyanHits++;
                }

                if (magentaHits >= 8 && cyanHits >= 8) {
                    return true;
                }
            }
        }

        return false;
    }

    private void switchProbeToMirrorSurface() {
        if (!appCaptureVerified || virtualDisplay == null || textureView == null) return;

        SurfaceTexture st = textureView.getSurfaceTexture();
        if (st == null) {
            setMirrorError("Spegelytan försvann innan bilden startade.", "OUTPUT_SURFACE_MISSING");
            stopSelf();
            return;
        }

        try {
            if (probeMarker != null && overlay != null) {
                overlay.removeView(probeMarker);
                probeMarker = null;
            }

            st.setDefaultBufferSize(captureWidth, captureHeight);
            mirrorSurface = new Surface(st);

            virtualDisplay.setSurface(null);
            virtualDisplay.resize(captureWidth, captureHeight, densityDpi);
            virtualDisplay.setSurface(mirrorSurface);

            if (probeReader != null) {
                try { probeReader.close(); } catch (Throwable ignored) {}
                probeReader = null;
            }
        } catch (Throwable t) {
            setMirrorError("Kunde inte växla till spegelbilden.", "SURFACE_SWITCH_FAILED");
            stopSelf();
        }
    }

    private void setMirrorError(String message, String code) {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putBoolean("mirror_ready", false)
                .putBoolean("app_capture_verified", false)
                .putString("mirror_error", message)
                .putString("mirror_error_code", code)
                .apply();
    }

    private Notification buildNotification() {
        Intent stopIntent = new Intent(this, MirrorOverlayService.class);
        stopIntent.setAction(ACTION_STOP);

        PendingIntent stopPending = PendingIntent.getService(
                this,
                12,
                stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        return new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Projektorläge")
                .setContentText("Spegelvänd appbild aktiv")
                .setSmallIcon(android.R.drawable.ic_menu_view)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(
                        android.R.drawable.ic_menu_close_clear_cancel,
                        "STOPPA",
                        stopPending).build())
                .build();
    }

    private void createChannel() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm == null) return;

        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Projektorläge",
                NotificationManager.IMPORTANCE_LOW);
        nm.createNotificationChannel(channel);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void releaseCaptureResources() {
        if (virtualDisplay != null) {
            try { virtualDisplay.release(); } catch (Throwable ignored) {}
            virtualDisplay = null;
        }

        if (mirrorSurface != null) {
            try { mirrorSurface.release(); } catch (Throwable ignored) {}
            mirrorSurface = null;
        }

        if (probeReader != null) {
            try { probeReader.close(); } catch (Throwable ignored) {}
            probeReader = null;
        }
    }

    private void removeOverlayOnly() {
        releaseCaptureResources();

        if (overlay != null && windowManager != null) {
            try { windowManager.removeView(overlay); } catch (Throwable ignored) {}
        }

        overlay = null;
        textureView = null;
        probeMarker = null;
        probeFinished = false;
        appCaptureVerified = false;
        probeFrames = 0;
        updatedFrames = 0;
    }

    @Override
    public void onDestroy() {
        intentionalStop = true;

        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putBoolean("mirror_ready", false)
                .putBoolean("app_capture_verified", false)
                .apply();

        removeOverlayOnly();

        if (projection != null) {
            try {
                projection.unregisterCallback(projectionCallback);
                projection.stop();
            } catch (Throwable ignored) {
            }
            projection = null;
        }

        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
''')

s = main.read_text()
s = s.replace(
    "Tryck Starta. Android ber dig välja Netflix i en säkerhetsruta; sedan sköter appen resten.",
    "Tryck Starta. I Android-rutan väljer du En app och sedan Netflix – inte Hela skärmen.",
    1)
s = s.replace(
    "Tryck Starta. Välj Netflix i Android-rutan. Bildriktning, spegling, maxljus och fjärr ställs sedan in automatiskt.",
    "Tryck Starta. Välj En app → Netflix i Android-rutan. Välj inte Hela skärmen.",
    1)
main.write_text(s)

b = build.read_text()
b = b.replace("    implementation 'org.lsposed.hiddenapibypass:hiddenapibypass:6.1'\n", "")
b = b.replace("versionCode 26", "versionCode 27", 1)
b = b.replace("versionName '2.6.0'", "versionName '2.7.0'", 1)
build.write_text(b)

print("v2.7 app-only mirror + whole-display guard applied")
