from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
manifest = root / "app/src/main/AndroidManifest.xml"
build = root / "app/build.gradle"
activity = root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java"
service = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

s = main.read_text()

s = replace_once(s,
'''        Button netflix = makeButton("ÖPPNA NETFLIX");
        netflix.setOnClickListener(v -> openNetflix());
        panel.addView(netflix, full(0, dp(10)));

        Button localVideo = makeButton("LOKAL VIDEO – SPEGEL / 180°");''',
'''        Button netflix = makeButton("ÖPPNA NETFLIX");
        netflix.setOnClickListener(v -> openNetflix());
        panel.addView(netflix, full(0, dp(10)));

        Button mirrorNetflix = makeButton("TESTA SPEGELVÄND NETFLIX");
        mirrorNetflix.setOnClickListener(v -> startActivity(new Intent(this, MirrorPermissionActivity.class)));
        panel.addView(mirrorNetflix, full(0, dp(10)));

        Button localVideo = makeButton("LOKAL VIDEO – SPEGEL / 180°");''',
"mirror netflix test button")

main.write_text(s)

m = manifest.read_text()

if 'android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION' not in m:
    m = m.replace(
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION" />',
        1
    )

m = replace_once(m,
'''        <activity
            android:name=".VideoPlayerActivity"''',
'''        <service
            android:name=".MirrorOverlayService"
            android:exported="false"
            android:foregroundServiceType="mediaProjection" />

        <activity
            android:name=".MirrorPermissionActivity"
            android:exported="false" />

        <activity
            android:name=".VideoPlayerActivity"''',
"mirror components manifest")
manifest.write_text(m)

activity.write_text(r'''package se.projektorlage.app;

import android.app.Activity;
import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Toast;

public class MirrorPermissionActivity extends Activity {
    private static final int REQ_CAPTURE = 9021;
    private MediaProjectionManager projectionManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this,
                    "Tillåt 'Visa över andra appar' och öppna testet igen.",
                    Toast.LENGTH_LONG).show();
            Intent settings = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName()));
            startActivity(settings);
            finish();
            return;
        }

        projectionManager = (MediaProjectionManager)
                getSystemService(MEDIA_PROJECTION_SERVICE);
        startActivityForResult(projectionManager.createScreenCaptureIntent(), REQ_CAPTURE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_CAPTURE) return;

        if (resultCode != RESULT_OK || data == null) {
            Toast.makeText(this, "Skärmspegling avbröts.", Toast.LENGTH_SHORT).show();
            finish();
            return;
        }

        Intent service = new Intent(this, MirrorOverlayService.class);
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
        finish();
    }
}
''')

service.write_text(r'''package se.projektorlage.app;

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
import android.os.IBinder;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.view.WindowManager;
import android.widget.FrameLayout;

public class MirrorOverlayService extends Service {
    public static final String ACTION_START = "se.projektorlage.app.MIRROR_START";
    public static final String ACTION_STOP = "se.projektorlage.app.MIRROR_STOP";
    public static final String EXTRA_RESULT_CODE = "result_code";
    public static final String EXTRA_RESULT_DATA = "result_data";

    private static final int NOTIFICATION_ID = 707;
    private static final String CHANNEL_ID = "mirror_projection";

    private WindowManager windowManager;
    private FrameLayout overlay;
    private TextureView textureView;
    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private Surface captureSurface;

    private final MediaProjection.Callback projectionCallback = new MediaProjection.Callback() {
        @Override
        public void onStop() {
            stopSelf();
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

        if (ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }

        startForeground(NOTIFICATION_ID, buildNotification());

        int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
        Intent resultData = intent.getParcelableExtra(EXTRA_RESULT_DATA);
        if (resultCode == 0 || resultData == null) {
            stopSelf();
            return START_NOT_STICKY;
        }

        MediaProjectionManager manager = (MediaProjectionManager)
                getSystemService(MEDIA_PROJECTION_SERVICE);
        projection = manager.getMediaProjection(resultCode, resultData);
        if (projection == null) {
            stopSelf();
            return START_NOT_STICKY;
        }

        projection.registerCallback(projectionCallback, null);
        createMirrorOverlay();
        return START_NOT_STICKY;
    }

    private void createMirrorOverlay() {
        removeOverlay();

        overlay = new FrameLayout(this);
        textureView = new TextureView(this);
        textureView.setScaleX(-1f);

        overlay.addView(textureView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        int type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
        int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_SECURE;

        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                type,
                flags,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.setTitle("Projektorläge spegeltest");

        textureView.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
            @Override
            public void onSurfaceTextureAvailable(SurfaceTexture surfaceTexture, int width, int height) {
                startVirtualDisplay(surfaceTexture);
            }

            @Override
            public void onSurfaceTextureSizeChanged(SurfaceTexture surfaceTexture, int width, int height) {
                restartVirtualDisplay(surfaceTexture);
            }

            @Override
            public boolean onSurfaceTextureDestroyed(SurfaceTexture surfaceTexture) {
                releaseVirtualDisplay();
                return true;
            }

            @Override
            public void onSurfaceTextureUpdated(SurfaceTexture surfaceTexture) {
            }
        });

        windowManager.addView(overlay, lp);
    }

    private void startVirtualDisplay(SurfaceTexture surfaceTexture) {
        if (projection == null) return;
        releaseVirtualDisplay();

        int width = Math.max(1, getResources().getDisplayMetrics().widthPixels);
        int height = Math.max(1, getResources().getDisplayMetrics().heightPixels);
        int density = Math.max(1, getResources().getDisplayMetrics().densityDpi);

        surfaceTexture.setDefaultBufferSize(width, height);
        captureSurface = new Surface(surfaceTexture);

        virtualDisplay = projection.createVirtualDisplay(
                "ProjektorlageMirror",
                width,
                height,
                density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                captureSurface,
                null,
                null);
    }

    private void restartVirtualDisplay(SurfaceTexture surfaceTexture) {
        startVirtualDisplay(surfaceTexture);
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
                .setContentTitle("Projektorläge – spegeltest")
                .setContentText("Skärmen visas horisontellt spegelvänd. Tryck för att stoppa.")
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
                "Projektorläge spegeltest",
                NotificationManager.IMPORTANCE_LOW);
        nm.createNotificationChannel(channel);
    }

    private void releaseVirtualDisplay() {
        if (virtualDisplay != null) {
            virtualDisplay.release();
            virtualDisplay = null;
        }
        if (captureSurface != null) {
            captureSurface.release();
            captureSurface = null;
        }
    }

    private void removeOverlay() {
        if (overlay != null && windowManager != null) {
            try {
                windowManager.removeView(overlay);
            } catch (Exception ignored) {
            }
        }
        overlay = null;
        textureView = null;
    }

    @Override
    public void onDestroy() {
        releaseVirtualDisplay();
        removeOverlay();
        if (projection != null) {
            try {
                projection.unregisterCallback(projectionCallback);
                projection.stop();
            } catch (Exception ignored) {
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

s = build.read_text()
s = s.replace("versionCode 6", "versionCode 7", 1)
s = s.replace("versionName '0.6.0'", "versionName '0.7.0'", 1)
build.write_text(s)

print("v0.7 patch applied")
