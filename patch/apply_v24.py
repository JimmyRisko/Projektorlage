from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
perm = root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java"
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

# ---- MainActivity copy: full-screen source again, because that is the path that actually showed Netflix on this device.
s = main.read_text()
s = s.replace(
    "Tryck Starta. Android ber dig välja Netflix i en säkerhetsruta; sedan sköter appen resten.",
    "Tryck Starta och godkänn Androids skärmdelning. Sedan verifierar appen spegling, bildriktning och maxljus innan Netflix öppnas.",
    1
)
s = s.replace(
    "Tryck Starta. Välj Netflix i Android-rutan. Bildriktning, spegling, maxljus och fjärr ställs sedan in automatiskt.",
    "Tryck Starta och godkänn skärmdelning. Appen använder hela skärmen som källa men utesluter sin egen spegelbild för att undvika återkopplingsloopen.",
    1
)
main.write_text(s)

# ---- Capture permission: force default display (whole screen), not single-app capture.
s = perm.read_text()
s = s.replace(
'''        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            Toast.makeText(this,
                    "Välj Netflix i Android-rutan. Det krävs en gång per projektorsession.",
                    Toast.LENGTH_LONG).show();
            startActivityForResult(
                    projectionManager.createScreenCaptureIntent(
                            MediaProjectionConfig.createConfigForUserChoice()),
                    REQ_CAPTURE);
        } else {
            Toast.makeText(this,
                    "Godkänn skärmdelning för projektorläget.",
                    Toast.LENGTH_LONG).show();
            startActivityForResult(projectionManager.createScreenCaptureIntent(), REQ_CAPTURE);
        }''',
'''        Toast.makeText(this,
                "Godkänn skärmdelning. Du behöver inte välja Netflix eller ändra bildriktning.",
                Toast.LENGTH_LONG).show();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startActivityForResult(
                    projectionManager.createScreenCaptureIntent(
                            MediaProjectionConfig.createConfigForDefaultDisplay()),
                    REQ_CAPTURE);
        } else {
            startActivityForResult(projectionManager.createScreenCaptureIntent(), REQ_CAPTURE);
        }''',
1
)
perm.write_text(s)

# ---- Product-safe startup sequencing: do not open Netflix until the mirror
# overlay has been excluded from capture and real frames are flowing.
s = perm.read_text()
old_startup = '''    private void startMirrorAndNetflix() {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("startup_state", "STARTING_MIRROR")
                .apply();

        Intent mirror = new Intent(this, MirrorOverlayService.class);
        mirror.setAction(MirrorOverlayService.ACTION_START);
        mirror.putExtra(MirrorOverlayService.EXTRA_RESULT_CODE, captureResultCode);
        mirror.putExtra(MirrorOverlayService.EXTRA_RESULT_DATA, captureResultData);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(mirror);
        } else {
            startService(mirror);
        }

        Intent netflix = getPackageManager().getLaunchIntentForPackage(NETFLIX_PACKAGE);
        if (netflix == null) {
            failAndRestore("ERR_MIRROR", "Netflix-appen hittades inte på mobilen.");
            return;
        }

        netflix.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        startActivity(netflix);

        setupDeadline = System.currentTimeMillis() + 6000;
        handler.postDelayed(this::waitForMirror, 200);
    }

    private void waitForMirror() {
        SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);
        if (prefs.getBoolean("mirror_ready", false)) {
            prefs.edit().putString("startup_state", "READY").apply();
            finish();
            return;
        }

        String mirrorError = prefs.getString("mirror_error", "");
        if (!mirrorError.isEmpty()) {
            failAndRestore("ERR_MIRROR", "Speglingen kunde inte starta: " + mirrorError);
            return;
        }

        if (System.currentTimeMillis() >= setupDeadline) {
            failAndRestore("ERR_MIRROR", "Speglingen gav ingen bild. Starta om projektorläget och välj Netflix i Android-rutan.");
            return;
        }

        handler.postDelayed(this::waitForMirror, 200);
    }'''

new_startup = '''    private void startMirrorAndNetflix() {
        Intent netflix = getPackageManager().getLaunchIntentForPackage(NETFLIX_PACKAGE);
        if (netflix == null) {
            failAndRestore("ERR_MIRROR", "Netflix-appen hittades inte på mobilen.");
            return;
        }

        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("startup_state", "STARTING_MIRROR")
                .apply();

        Intent mirror = new Intent(this, MirrorOverlayService.class);
        mirror.setAction(MirrorOverlayService.ACTION_START);
        mirror.putExtra(MirrorOverlayService.EXTRA_RESULT_CODE, captureResultCode);
        mirror.putExtra(MirrorOverlayService.EXTRA_RESULT_DATA, captureResultData);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(mirror);
        } else {
            startService(mirror);
        }

        // Do not open Netflix until the overlay is definitely excluded from
        // MediaProjection and actual frames have reached the mirrored TextureView.
        setupDeadline = System.currentTimeMillis() + 7000;
        handler.postDelayed(this::waitForMirrorThenLaunchNetflix, 150);
    }

    private void waitForMirrorThenLaunchNetflix() {
        SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);

        String mirrorError = prefs.getString("mirror_error", "");
        if (!mirrorError.isEmpty()) {
            failAndRestore("ERR_MIRROR", "Speglingen kunde inte starta: " + mirrorError);
            return;
        }

        if (prefs.getBoolean("mirror_ready", false)
                && prefs.getBoolean("overlay_excluded", false)) {
            Intent netflix = getPackageManager().getLaunchIntentForPackage(NETFLIX_PACKAGE);
            if (netflix == null) {
                failAndRestore("ERR_MIRROR", "Netflix-appen hittades inte på mobilen.");
                return;
            }

            netflix.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            startActivity(netflix);

            prefs.edit().putString("startup_state", "READY").apply();
            finish();
            return;
        }

        if (System.currentTimeMillis() >= setupDeadline) {
            failAndRestore("ERR_MIRROR",
                    "Speglingen kunde inte verifieras. Projektorläget har återställts utan att öppna Netflix.");
            return;
        }

        handler.postDelayed(this::waitForMirrorThenLaunchNetflix, 150);
    }'''

if old_startup not in s:
    raise SystemExit("v2.4 startup sequencing patch did not match")
s = s.replace(old_startup, new_startup, 1)
perm.write_text(s)

# ---- Replace the mirror service with the known-working TextureView path plus
# SurfaceFlinger eSkipScreenshot, the technique used by LSFG Android to stop
# the overlay from feeding back into MediaProjection.
mirror.write_text(r'''package se.projektorlage.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.graphics.SurfaceTexture;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.view.Gravity;
import android.view.Surface;
import android.view.SurfaceControl;
import android.view.TextureView;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;

import java.lang.reflect.Field;
import java.lang.reflect.Method;

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
    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private Surface captureSurface;

    private boolean intentionalStop;
    private boolean skipScreenshotInstalled;
    private int updatedFrames;

    private final MediaProjection.Callback projectionCallback = new MediaProjection.Callback() {
        @Override
        public void onStop() {
            if (!intentionalStop) {
                setMirrorError("skärmdelningen stoppades");
            }
            stopSelf();
        }

        @Override
        public void onCapturedContentResize(int width, int height) {
            if (virtualDisplay == null || textureView == null
                    || textureView.getSurfaceTexture() == null) return;
            try {
                int w = Math.max(1, width);
                int h = Math.max(1, height);
                int density = Math.max(1, getResources().getDisplayMetrics().densityDpi);
                SurfaceTexture st = textureView.getSurfaceTexture();
                st.setDefaultBufferSize(w, h);
                virtualDisplay.resize(w, h, density);
            } catch (Throwable ignored) {
            }
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

        // Picture profiles are intentionally ignored in this stability build.
        // No white overlay, no tone transform: first make mirroring reliable.
        if (ACTION_PROFILE.equals(action)) {
            return START_NOT_STICKY;
        }

        if (!ACTION_START.equals(action)) return START_NOT_STICKY;

        startForeground(NOTIFICATION_ID, buildNotification());

        int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
        Intent resultData = intent.getParcelableExtra(EXTRA_RESULT_DATA);
        if (resultCode == 0 || resultData == null) {
            setMirrorError("saknar skärmdelningsbehörighet");
            stopSelf();
            return START_NOT_STICKY;
        }

        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putBoolean("mirror_ready", false)
                .putBoolean("overlay_excluded", false)
                .remove("mirror_error")
                .apply();

        MediaProjectionManager manager = (MediaProjectionManager)
                getSystemService(MEDIA_PROJECTION_SERVICE);
        projection = manager.getMediaProjection(resultCode, resultData);
        if (projection == null) {
            setMirrorError("kunde inte starta skärmdelningen");
            stopSelf();
            return START_NOT_STICKY;
        }

        projection.registerCallback(projectionCallback, mainHandler);
        createMirrorOverlay();
        return START_NOT_STICKY;
    }

    private void createMirrorOverlay() {
        removeOverlayOnly();

        overlay = new FrameLayout(this);
        overlay.setClickable(true);
        overlay.setOnTouchListener((v, event) -> true);

        textureView = new TextureView(this);
        textureView.setOpaque(true);

        // This is the same simple horizontal flip that worked in the earlier
        // morning build. Keep it separate from the capture pipeline.
        textureView.setScaleX(-1f);

        overlay.addView(textureView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        int type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
        int windowFlags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON;

        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                type,
                windowFlags,
                PixelFormat.OPAQUE);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL;
        lp.setTitle("Projektorläge spegel");

        textureView.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
            @Override
            public void onSurfaceTextureAvailable(SurfaceTexture st, int width, int height) {
                // Important order:
                // 1) The overlay must be attached and have a real SurfaceControl.
                // 2) Mark that layer eSkipScreenshot.
                // 3) Only then start MediaProjection capture.
                mainHandler.post(() -> attemptInstallSkipScreenshot(st, 0));
            }

            @Override
            public void onSurfaceTextureSizeChanged(SurfaceTexture st, int width, int height) {
                if (virtualDisplay != null) {
                    try {
                        int density = Math.max(1, getResources().getDisplayMetrics().densityDpi);
                        st.setDefaultBufferSize(Math.max(1, width), Math.max(1, height));
                        virtualDisplay.resize(Math.max(1, width), Math.max(1, height), density);
                    } catch (Throwable ignored) {
                    }
                }
            }

            @Override
            public boolean onSurfaceTextureDestroyed(SurfaceTexture st) {
                releaseVirtualDisplay();
                return true;
            }

            @Override
            public void onSurfaceTextureUpdated(SurfaceTexture st) {
                updatedFrames++;
                if (updatedFrames == 2 && skipScreenshotInstalled) {
                    getSharedPreferences("state", MODE_PRIVATE).edit()
                            .putBoolean("mirror_ready", true)
                            .remove("mirror_error")
                            .apply();
                }
            }
        });

        try {
            windowManager.addView(overlay, lp);
        } catch (Throwable t) {
            setMirrorError("kunde inte visa spegelytan");
            stopSelf();
        }
    }

    private void attemptInstallSkipScreenshot(SurfaceTexture st, int attempt) {
        if (overlay == null || st == null) return;

        if (installSkipScreenshot(overlay)) {
            skipScreenshotInstalled = true;
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("overlay_excluded", true)
                    .apply();
            startVirtualDisplay(st);
            return;
        }

        // SurfaceControl/BLAST can lag a few frames behind View attachment on Samsung.
        // Retry briefly instead of failing on the first frame.
        if (attempt < 15) {
            mainHandler.postDelayed(
                    () -> attemptInstallSkipScreenshot(st, attempt + 1),
                    attempt < 4 ? 50L : 90L);
            return;
        }

        setMirrorError("Samsung/Android blockerade overlay-undantaget");
        stopSelf();
    }

    /**
     * SurfaceFlinger eSkipScreenshot:
     * the overlay is visible on the physical phone display but omitted from
     * MediaProjection/VirtualDisplay composition. This is the missing piece
     * that prevents the hall-of-mirrors feedback loop without FLAG_SECURE.
     */
    @android.annotation.TargetApi(29)
    private boolean installSkipScreenshot(View host) {
        if (android.os.Build.VERSION.SDK_INT < 29) return false;

        try {
            Object viewRootImpl = null;

            // Same primary path used by LSFG Android.
            try {
                Method getVri = host.getClass().getMethod("getViewRootImpl");
                getVri.setAccessible(true);
                viewRootImpl = getVri.invoke(host);
            } catch (Throwable ignored) {
            }

            // OEM fallback.
            if (viewRootImpl == null) {
                try {
                    Method getVri = View.class.getDeclaredMethod("getViewRootImpl");
                    getVri.setAccessible(true);
                    viewRootImpl = getVri.invoke(host);
                } catch (Throwable ignored) {
                }
            }

            if (viewRootImpl == null) return false;

            SurfaceControl sc = null;

            // AOSP path: ViewRootImpl.getSurfaceControl().
            try {
                Method getter = viewRootImpl.getClass().getMethod("getSurfaceControl");
                Object value = getter.invoke(viewRootImpl);
                if (value instanceof SurfaceControl) sc = (SurfaceControl) value;
            } catch (Throwable ignored) {
            }

            // Samsung/OEM fallback: conventional mSurfaceControl field.
            if (sc == null) {
                Class<?> cls = viewRootImpl.getClass();
                while (cls != null && sc == null) {
                    try {
                        Field field = cls.getDeclaredField("mSurfaceControl");
                        field.setAccessible(true);
                        Object value = field.get(viewRootImpl);
                        if (value instanceof SurfaceControl) sc = (SurfaceControl) value;
                    } catch (Throwable ignored) {
                    }
                    cls = cls.getSuperclass();
                }
            }

            // OEM rename fallback: find any SurfaceControl-typed field.
            if (sc == null) {
                Class<?> cls = viewRootImpl.getClass();
                while (cls != null && sc == null) {
                    for (Field field : cls.getDeclaredFields()) {
                        if (SurfaceControl.class.isAssignableFrom(field.getType())) {
                            try {
                                field.setAccessible(true);
                                Object value = field.get(viewRootImpl);
                                if (value instanceof SurfaceControl) {
                                    sc = (SurfaceControl) value;
                                    break;
                                }
                            } catch (Throwable ignored) {
                            }
                        }
                    }
                    cls = cls.getSuperclass();
                }
            }

            // Android 12+ BLAST fallback used by LSFG for OEMs that hide SC fields.
            if (sc == null) {
                try {
                    Class<?> blastClass = Class.forName("android.graphics.BLASTBufferQueue");
                    Class<?> cls = viewRootImpl.getClass();

                    while (cls != null && sc == null) {
                        for (Field field : cls.getDeclaredFields()) {
                            if (!blastClass.isAssignableFrom(field.getType())) continue;

                            try {
                                field.setAccessible(true);
                                Object blast = field.get(viewRootImpl);
                                if (blast == null) continue;

                                for (String methodName :
                                        new String[]{"getSyncedSurfaceControl", "getSurfaceControl"}) {
                                    try {
                                        Method method = blast.getClass().getMethod(methodName);
                                        Object value = method.invoke(blast);
                                        if (value instanceof SurfaceControl) {
                                            sc = (SurfaceControl) value;
                                            break;
                                        }
                                    } catch (Throwable ignored) {
                                    }
                                }
                            } catch (Throwable ignored) {
                            }

                            if (sc != null) break;
                        }
                        cls = cls.getSuperclass();
                    }
                } catch (Throwable ignored) {
                }
            }

            if (sc == null || !sc.isValid()) return false;

            SurfaceControl.Transaction transaction = new SurfaceControl.Transaction();
            Method skip = null;

            try {
                skip = transaction.getClass().getMethod(
                        "setSkipScreenshot",
                        SurfaceControl.class,
                        boolean.class);
            } catch (Throwable ignored) {
            }

            if (skip == null) {
                for (Method method : transaction.getClass().getDeclaredMethods()) {
                    if ("setSkipScreenshot".equals(method.getName())
                            && method.getParameterTypes().length == 2) {
                        try {
                            method.setAccessible(true);
                            skip = method;
                            break;
                        } catch (Throwable ignored) {
                        }
                    }
                }
            }

            if (skip == null) return false;

            skip.invoke(transaction, sc, true);
            transaction.apply();
            return true;
        } catch (Throwable t) {
            return false;
        }
    }

    private void startVirtualDisplay(SurfaceTexture st) {
        if (projection == null || st == null || !skipScreenshotInstalled) return;

        releaseVirtualDisplay();

        int width = Math.max(1, getResources().getDisplayMetrics().widthPixels);
        int height = Math.max(1, getResources().getDisplayMetrics().heightPixels);
        int density = Math.max(1, getResources().getDisplayMetrics().densityDpi);

        try {
            st.setDefaultBufferSize(width, height);
            captureSurface = new Surface(st);

            virtualDisplay = projection.createVirtualDisplay(
                    "ProjektorlageMirror",
                    width,
                    height,
                    density,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    captureSurface,
                    null,
                    mainHandler);
        } catch (Throwable t) {
            setMirrorError("kunde inte skapa spegelströmmen");
            stopSelf();
        }
    }

    private void setMirrorError(String message) {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putBoolean("mirror_ready", false)
                .putString("mirror_error", message)
                .apply();
    }

    private Notification buildNotification() {
        Intent stopIntent = new Intent(this, MirrorOverlayService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPending = PendingIntent.getService(
                this, 12, stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        return new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Projektorläge")
                .setContentText("Spegling aktiv – egen overlay är utesluten från skärmdelningen")
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
                CHANNEL_ID, "Projektorläge", NotificationManager.IMPORTANCE_LOW);
        nm.createNotificationChannel(channel);
    }

    private void releaseVirtualDisplay() {
        if (virtualDisplay != null) {
            try { virtualDisplay.release(); } catch (Throwable ignored) {}
            virtualDisplay = null;
        }
        if (captureSurface != null) {
            try { captureSurface.release(); } catch (Throwable ignored) {}
            captureSurface = null;
        }
    }

    private void removeOverlayOnly() {
        releaseVirtualDisplay();
        if (overlay != null && windowManager != null) {
            try { windowManager.removeView(overlay); } catch (Throwable ignored) {}
        }
        overlay = null;
        textureView = null;
        updatedFrames = 0;
        skipScreenshotInstalled = false;
    }

    @Override
    public void onDestroy() {
        intentionalStop = true;
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putBoolean("mirror_ready", false)
                .putBoolean("overlay_excluded", false)
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

b = build.read_text()
b = b.replace("minSdk 26", "minSdk 29", 1)
b = b.replace("versionCode 23", "versionCode 24", 1)
b = b.replace("versionName '2.3.0'", "versionName '2.4.0'", 1)
build.write_text(b)

print("v2.4 whole-display + skip-screenshot mirror architecture applied")
