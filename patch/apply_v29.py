from pathlib import Path
import sys

root = Path(sys.argv[1])
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

mirror.write_text(r'''package se.projektorlage.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.SurfaceTexture;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.opengl.GLES11Ext;
import android.opengl.GLES20;
import android.opengl.GLSurfaceView;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.view.Gravity;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;

import javax.microedition.khronos.egl.EGLConfig;
import javax.microedition.khronos.opengles.GL10;

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
    private GLSurfaceView glView;
    private MirrorRenderer renderer;
    private FrameLayout probeMarker;

    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader probeReader;
    private Surface captureSurface;
    private SurfaceTexture sourceTexture;

    private boolean intentionalStop;
    private boolean probeFinished;
    private boolean appCaptureVerified;
    private boolean glSurfaceReady;
    private boolean sourceTextureReady;
    private int probeFrames;

    private int captureWidth;
    private int captureHeight;
    private int densityDpi;

    private String currentProfile = "PROJECTOR";

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

            mainHandler.post(() -> {
                try {
                    if (sourceTexture != null) {
                        sourceTexture.setDefaultBufferSize(captureWidth, captureHeight);
                    }

                    if (virtualDisplay != null && probeFinished) {
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
            String profile = intent.getStringExtra(EXTRA_PROFILE);
            applyPictureProfile(profile);
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

        currentProfile = getSharedPreferences("state", MODE_PRIVATE)
                .getString("picture_profile", "PROJECTOR");

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

        glView = new GLSurfaceView(this);
        glView.setEGLContextClientVersion(2);
        glView.setEGLConfigChooser(8, 8, 8, 8, 0, 0);
        glView.setPreserveEGLContextOnPause(true);
        glView.getHolder().setFormat(PixelFormat.OPAQUE);
        glView.setAlpha(0f);

        renderer = new MirrorRenderer();
        renderer.setProfile(currentProfile);
        renderer.setReadyListener(texture -> mainHandler.post(() -> {
            sourceTexture = texture;
            sourceTextureReady = true;
            maybeStartProbe();
        }));

        glView.getHolder().addCallback(new SurfaceHolder.Callback() {
            @Override
            public void surfaceCreated(SurfaceHolder holder) {
                glSurfaceReady = true;
                maybeStartProbe();
            }

            @Override
            public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
            }

            @Override
            public void surfaceDestroyed(SurfaceHolder holder) {
                glSurfaceReady = false;
                releaseCaptureResources();
            }
        });

        glView.setRenderer(renderer);
        glView.setRenderMode(GLSurfaceView.RENDERMODE_WHEN_DIRTY);

        overlay.addView(glView, new FrameLayout.LayoutParams(
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

        if (Build.VERSION.SDK_INT >= 35) {
            lp.setDesiredHdrHeadroom(1.0f);
        }

        lp.setColorMode(ActivityInfo.COLOR_MODE_DEFAULT);
        lp.setTitle("Projektorläge GPU-spegel");

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

    private void maybeStartProbe() {
        if (!glSurfaceReady
                || !sourceTextureReady
                || sourceTexture == null
                || projection == null
                || virtualDisplay != null) {
            return;
        }

        sourceTexture.setDefaultBufferSize(captureWidth, captureHeight);

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

                mainHandler.post(this::switchProbeToGpuSurface);
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

    private void switchProbeToGpuSurface() {
        if (!appCaptureVerified
                || virtualDisplay == null
                || sourceTexture == null
                || glView == null) {
            return;
        }

        try {
            if (probeMarker != null && overlay != null) {
                overlay.removeView(probeMarker);
                probeMarker = null;
            }

            sourceTexture.setDefaultBufferSize(captureWidth, captureHeight);
            captureSurface = new Surface(sourceTexture);

            virtualDisplay.setSurface(null);
            virtualDisplay.resize(captureWidth, captureHeight, densityDpi);
            virtualDisplay.setSurface(captureSurface);

            if (probeReader != null) {
                try { probeReader.close(); } catch (Throwable ignored) {}
                probeReader = null;
            }

            glView.setAlpha(1f);
            glView.requestRender();
        } catch (Throwable t) {
            setMirrorError("Kunde inte växla till GPU-spegeln.", "SURFACE_SWITCH_FAILED");
            stopSelf();
        }
    }

    private void applyPictureProfile(String profile) {
        if (profile == null) profile = "PROJECTOR";
        currentProfile = profile;

        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("picture_profile", currentProfile)
                .apply();

        MirrorRenderer r = renderer;
        if (r != null) {
            r.setProfile(currentProfile);
            GLSurfaceView view = glView;
            if (view != null) view.requestRender();
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
                .setContentText("Spegelvänd GPU-bild aktiv")
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

        if (captureSurface != null) {
            try { captureSurface.release(); } catch (Throwable ignored) {}
            captureSurface = null;
        }

        if (probeReader != null) {
            try { probeReader.close(); } catch (Throwable ignored) {}
            probeReader = null;
        }
    }

    private void removeOverlayOnly() {
        releaseCaptureResources();

        if (sourceTexture != null) {
            try { sourceTexture.release(); } catch (Throwable ignored) {}
            sourceTexture = null;
        }

        if (overlay != null && windowManager != null) {
            try { windowManager.removeView(overlay); } catch (Throwable ignored) {}
        }

        overlay = null;
        glView = null;
        renderer = null;
        probeMarker = null;

        probeFinished = false;
        appCaptureVerified = false;
        glSurfaceReady = false;
        sourceTextureReady = false;
        probeFrames = 0;
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

    private final class MirrorRenderer implements GLSurfaceView.Renderer {
        private final FloatBuffer vertexBuffer;
        private final FloatBuffer texBuffer;
        private final float[] textureMatrix = new float[16];

        private int program;
        private int oesTextureId;
        private int aPosition;
        private int aTexCoord;
        private int uTextureMatrix;
        private int uTexture;
        private int uGamma;
        private int uSaturation;
        private int uShadowFloor;

        private SurfaceTexture surfaceTexture;
        private ReadyListener readyListener;
        private int renderedFrames;

        private volatile float gamma = 0.67f;
        private volatile float saturation = 1.03f;
        private volatile float shadowFloor = 0.006f;

        private final float[] vertices = {
                -1f, -1f,
                 1f, -1f,
                -1f,  1f,
                 1f,  1f
        };

        private final float[] texCoords = {
                0f, 1f,
                1f, 1f,
                0f, 0f,
                1f, 0f
        };

        MirrorRenderer() {
            vertexBuffer = ByteBuffer.allocateDirect(vertices.length * 4)
                    .order(ByteOrder.nativeOrder())
                    .asFloatBuffer();
            vertexBuffer.put(vertices).position(0);

            texBuffer = ByteBuffer.allocateDirect(texCoords.length * 4)
                    .order(ByteOrder.nativeOrder())
                    .asFloatBuffer();
            texBuffer.put(texCoords).position(0);
        }

        void setReadyListener(ReadyListener listener) {
            readyListener = listener;
        }

        void setProfile(String profile) {
            if ("NATURAL".equals(profile)) {
                gamma = 1.0f;
                saturation = 1.0f;
                shadowFloor = 0.0f;
            } else if ("MAX".equals(profile)) {
                gamma = 0.56f;
                saturation = 1.05f;
                shadowFloor = 0.004f;
            } else {
                // PROJECTOR: calibrated to undo the visible luminance loss seen
                // when the selected app is enlarged into the mirror surface.
                gamma = 0.67f;
                saturation = 1.03f;
                shadowFloor = 0.006f;
            }
        }

        @Override
        public void onSurfaceCreated(GL10 gl, EGLConfig config) {
            program = createProgram(VERTEX_SHADER, FRAGMENT_SHADER);

            aPosition = GLES20.glGetAttribLocation(program, "aPosition");
            aTexCoord = GLES20.glGetAttribLocation(program, "aTexCoord");
            uTextureMatrix = GLES20.glGetUniformLocation(program, "uTextureMatrix");
            uTexture = GLES20.glGetUniformLocation(program, "uTexture");
            uGamma = GLES20.glGetUniformLocation(program, "uGamma");
            uSaturation = GLES20.glGetUniformLocation(program, "uSaturation");
            uShadowFloor = GLES20.glGetUniformLocation(program, "uShadowFloor");

            int[] textures = new int[1];
            GLES20.glGenTextures(1, textures, 0);
            oesTextureId = textures[0];

            GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, oesTextureId);
            GLES20.glTexParameteri(
                    GLES11Ext.GL_TEXTURE_EXTERNAL_OES,
                    GLES20.GL_TEXTURE_MIN_FILTER,
                    GLES20.GL_LINEAR);
            GLES20.glTexParameteri(
                    GLES11Ext.GL_TEXTURE_EXTERNAL_OES,
                    GLES20.GL_TEXTURE_MAG_FILTER,
                    GLES20.GL_LINEAR);
            GLES20.glTexParameteri(
                    GLES11Ext.GL_TEXTURE_EXTERNAL_OES,
                    GLES20.GL_TEXTURE_WRAP_S,
                    GLES20.GL_CLAMP_TO_EDGE);
            GLES20.glTexParameteri(
                    GLES11Ext.GL_TEXTURE_EXTERNAL_OES,
                    GLES20.GL_TEXTURE_WRAP_T,
                    GLES20.GL_CLAMP_TO_EDGE);

            surfaceTexture = new SurfaceTexture(oesTextureId);
            surfaceTexture.setOnFrameAvailableListener(
                    st -> {
                        GLSurfaceView view = glView;
                        if (view != null) view.requestRender();
                    },
                    mainHandler);

            ReadyListener listener = readyListener;
            if (listener != null) listener.onReady(surfaceTexture);
        }

        @Override
        public void onSurfaceChanged(GL10 gl, int width, int height) {
            GLES20.glViewport(0, 0, width, height);
        }

        @Override
        public void onDrawFrame(GL10 gl) {
            if (surfaceTexture == null || !appCaptureVerified) {
                GLES20.glClearColor(0f, 0f, 0f, 1f);
                GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT);
                return;
            }

            try {
                surfaceTexture.updateTexImage();
                surfaceTexture.getTransformMatrix(textureMatrix);
            } catch (Throwable ignored) {
                return;
            }

            GLES20.glDisable(GLES20.GL_BLEND);
            GLES20.glClearColor(0f, 0f, 0f, 1f);
            GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT);

            GLES20.glUseProgram(program);

            vertexBuffer.position(0);
            GLES20.glEnableVertexAttribArray(aPosition);
            GLES20.glVertexAttribPointer(
                    aPosition, 2, GLES20.GL_FLOAT, false, 0, vertexBuffer);

            texBuffer.position(0);
            GLES20.glEnableVertexAttribArray(aTexCoord);
            GLES20.glVertexAttribPointer(
                    aTexCoord, 2, GLES20.GL_FLOAT, false, 0, texBuffer);

            GLES20.glUniformMatrix4fv(uTextureMatrix, 1, false, textureMatrix, 0);
            GLES20.glUniform1f(uGamma, gamma);
            GLES20.glUniform1f(uSaturation, saturation);
            GLES20.glUniform1f(uShadowFloor, shadowFloor);

            GLES20.glActiveTexture(GLES20.GL_TEXTURE0);
            GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, oesTextureId);
            GLES20.glUniform1i(uTexture, 0);

            GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4);

            renderedFrames++;
            if (renderedFrames == 2) {
                mainHandler.post(() -> getSharedPreferences("state", MODE_PRIVATE).edit()
                        .putBoolean("mirror_ready", true)
                        .putBoolean("app_capture_verified", true)
                        .remove("mirror_error")
                        .remove("mirror_error_code")
                        .apply());
            }

            GLES20.glDisableVertexAttribArray(aPosition);
            GLES20.glDisableVertexAttribArray(aTexCoord);
        }

        private int createProgram(String vertexSource, String fragmentSource) {
            int vertexShader = compileShader(GLES20.GL_VERTEX_SHADER, vertexSource);
            int fragmentShader = compileShader(GLES20.GL_FRAGMENT_SHADER, fragmentSource);

            int result = GLES20.glCreateProgram();
            GLES20.glAttachShader(result, vertexShader);
            GLES20.glAttachShader(result, fragmentShader);
            GLES20.glLinkProgram(result);

            int[] linked = new int[1];
            GLES20.glGetProgramiv(result, GLES20.GL_LINK_STATUS, linked, 0);

            if (linked[0] == 0) {
                String log = GLES20.glGetProgramInfoLog(result);
                GLES20.glDeleteProgram(result);
                throw new RuntimeException("GL program link failed: " + log);
            }

            GLES20.glDeleteShader(vertexShader);
            GLES20.glDeleteShader(fragmentShader);
            return result;
        }

        private int compileShader(int type, String source) {
            int shader = GLES20.glCreateShader(type);
            GLES20.glShaderSource(shader, source);
            GLES20.glCompileShader(shader);

            int[] compiled = new int[1];
            GLES20.glGetShaderiv(shader, GLES20.GL_COMPILE_STATUS, compiled, 0);

            if (compiled[0] == 0) {
                String log = GLES20.glGetShaderInfoLog(shader);
                GLES20.glDeleteShader(shader);
                throw new RuntimeException("GL shader compile failed: " + log);
            }

            return shader;
        }

        private static final String VERTEX_SHADER =
                "attribute vec4 aPosition;\n" +
                "attribute vec2 aTexCoord;\n" +
                "uniform mat4 uTextureMatrix;\n" +
                "varying vec2 vTexCoord;\n" +
                "void main() {\n" +
                "  gl_Position = aPosition;\n" +
                "  vec4 tc = uTextureMatrix * vec4(aTexCoord, 0.0, 1.0);\n" +
                "  vTexCoord = vec2(1.0 - tc.x, tc.y);\n" +
                "}\n";

        private static final String FRAGMENT_SHADER =
                "#extension GL_OES_EGL_image_external : require\n" +
                "precision highp float;\n" +
                "uniform samplerExternalOES uTexture;\n" +
                "uniform float uGamma;\n" +
                "uniform float uSaturation;\n" +
                "uniform float uShadowFloor;\n" +
                "varying vec2 vTexCoord;\n" +
                "void main() {\n" +
                "  vec4 c = texture2D(uTexture, vTexCoord);\n" +
                "  vec3 rgb = clamp(c.rgb, 0.0, 1.0);\n" +
                "  float lum = dot(rgb, vec3(0.2126, 0.7152, 0.0722));\n" +
                "  if (lum <= uShadowFloor) {\n" +
                "    gl_FragColor = vec4(rgb, 1.0);\n" +
                "    return;\n" +
                "  }\n" +
                "  float target = pow(clamp(lum, 0.0, 1.0), uGamma);\n" +
                "  float scale = target / max(lum, 0.0001);\n" +
                "  vec3 lifted = clamp(rgb * scale, 0.0, 1.0);\n" +
                "  float l2 = dot(lifted, vec3(0.2126, 0.7152, 0.0722));\n" +
                "  vec3 graded = clamp(vec3(l2) + (lifted - vec3(l2)) * uSaturation, 0.0, 1.0);\n" +
                "  gl_FragColor = vec4(graded, 1.0);\n" +
                "}\n";
    }

    private interface ReadyListener {
        void onReady(SurfaceTexture texture);
    }
}
''')

b = build.read_text()
b = b.replace("versionCode 28", "versionCode 29", 1)
b = b.replace("versionName '2.8.0'", "versionName '2.9.0'", 1)
build.write_text(b)

print("v2.9 direct GPU luminance mirror applied")
