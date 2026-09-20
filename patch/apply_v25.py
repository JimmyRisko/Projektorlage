from pathlib import Path
import sys

root = Path(sys.argv[1])
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
build = root / "app/build.gradle"

mirror.write_text(r'''package se.projektorlage.app;

import android.annotation.TargetApi;
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
import android.media.Image;
import android.media.ImageReader;
import android.hardware.display.VirtualDisplay;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.opengl.GLES11Ext;
import android.opengl.GLES20;
import android.opengl.GLSurfaceView;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.view.Gravity;
import android.view.Surface;
import android.view.SurfaceControl;
import android.view.SurfaceHolder;
import android.view.WindowManager;
import android.widget.FrameLayout;

import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;

import javax.microedition.khronos.egl.EGLConfig;
import javax.microedition.khronos.opengles.GL10;

import org.lsposed.hiddenapibypass.HiddenApiBypass;

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

    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private Surface captureSurface;
    private SurfaceTexture sourceTexture;
    private ImageReader verificationReader;
    private boolean verificationFinished;

    private boolean intentionalStop;
    private boolean skipScreenshotInstalled;
    private boolean glOutputSurfaceReady;
    private boolean sourceTextureReady;
    private boolean captureStarted;
    private int skipAttempts;

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
            if (width <= 0 || height <= 0) return;
            mainHandler.post(() -> {
                try {
                    if (sourceTexture != null) {
                        sourceTexture.setDefaultBufferSize(width, height);
                    }
                    if (virtualDisplay != null) {
                        int density = Math.max(1, getResources().getDisplayMetrics().densityDpi);
                        virtualDisplay.resize(width, height, density);
                    }
                } catch (Throwable ignored) {
                }
            });
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

        // Stability first: picture profiles are intentionally ignored here.
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
                .remove("mirror_error_code")
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
        overlay.setBackgroundColor(Color.TRANSPARENT);
        overlay.setClickable(true);
        overlay.setOnTouchListener((v, event) -> true);

        glView = new GLSurfaceView(this);
        glView.setEGLContextClientVersion(2);
        glView.setPreserveEGLContextOnPause(true);
        glView.getHolder().setFormat(PixelFormat.OPAQUE);
        glView.setZOrderOnTop(true);

        renderer = new MirrorRenderer();
        renderer.setReadyListener(texture -> mainHandler.post(() -> {
            sourceTexture = texture;
            sourceTextureReady = true;
            maybeStartCapture();
        }));

        glView.getHolder().addCallback(new SurfaceHolder.Callback() {
            @Override
            public void surfaceCreated(SurfaceHolder holder) {
                glOutputSurfaceReady = true;
                skipAttempts = 0;
                if (glView != null) glView.requestRender();
                attemptSkipScreenshot();
            }

            @Override
            public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
            }

            @Override
            public void surfaceDestroyed(SurfaceHolder holder) {
                glOutputSurfaceReady = false;
                skipScreenshotInstalled = false;
                releaseVirtualDisplay();
            }
        });

        glView.setRenderer(renderer);
        glView.setRenderMode(GLSurfaceView.RENDERMODE_WHEN_DIRTY);

        overlay.addView(glView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        int type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
        int windowFlags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON;

        // The root window is translucent. Only the GLSurfaceView's own compositor layer
        // is opaque, and that exact SurfaceControl is marked SKIP_SCREENSHOT.
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                type,
                windowFlags,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL;
        lp.setTitle("Projektorläge spegel");

        try {
            windowManager.addView(overlay, lp);
        } catch (Throwable t) {
            setMirrorError("kunde inte visa spegelytan");
            stopSelf();
        }
    }

    private void attemptSkipScreenshot() {
        if (!glOutputSurfaceReady || glView == null) return;

        if (installSkipScreenshotOnGlSurface()) {
            skipScreenshotInstalled = true;
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("overlay_excluded", false)
                    .remove("mirror_error_code")
                    .apply();
            maybeStartCapture();
            return;
        }

        skipAttempts++;
        if (skipAttempts <= 20) {
            mainHandler.postDelayed(this::attemptSkipScreenshot,
                    skipAttempts < 6 ? 50L : 100L);
            return;
        }

        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("mirror_error_code", "SKIP_SCREENSHOT_BLOCKED")
                .apply();
        setMirrorError("Samsung/Android blockerade att spegelytan undantas från skärmdelningen");
        stopSelf();
    }

    /**
     * The important v2.5 change:
     * GLSurfaceView inherits SurfaceView, whose getSurfaceControl() is a public API on
     * Android 10+. We therefore no longer reflect through ViewRootImpl/BLAST just to find
     * the output layer. The only hidden call left is setSkipScreenshot itself.
     */
    @TargetApi(29)
    private boolean installSkipScreenshotOnGlSurface() {
        if (android.os.Build.VERSION.SDK_INT < 29 || glView == null) return false;

        try {
            SurfaceControl sc = glView.getSurfaceControl();
            if (sc == null || !sc.isValid()) return false;

            SurfaceControl.Transaction transaction = new SurfaceControl.Transaction();
            try {
                Method method = HiddenApiBypass.getDeclaredMethod(
                        SurfaceControl.Transaction.class,
                        "setSkipScreenshot",
                        SurfaceControl.class,
                        boolean.class);
                method.invoke(transaction, sc, true);
                transaction.apply();
                return true;
            } finally {
                try { transaction.close(); } catch (Throwable ignored) {}
            }
        } catch (Throwable ignored) {
            return false;
        }
    }

    private void maybeStartCapture() {
        if (captureStarted
                || !skipScreenshotInstalled
                || !glOutputSurfaceReady
                || !sourceTextureReady
                || sourceTexture == null
                || projection == null) {
            return;
        }

        captureStarted = true;
        verifyOverlayExclusion();
    }

    /**
     * A successful reflection call is not enough on OEM builds. We verify the
     * real compositor result with one MediaProjection frame.
     *
     * The GLSurfaceView is solid magenta while verificationMode=true. If that
     * magenta surface appears in MediaProjection, SKIP_SCREENSHOT did not
     * actually take effect. Android 14+ allows one VirtualDisplay per token,
     * so this same VirtualDisplay is retargeted to the source SurfaceTexture.
     */
    private void verifyOverlayExclusion() {
        if (projection == null || sourceTexture == null || verificationFinished) return;

        int width = Math.max(1, getResources().getDisplayMetrics().widthPixels);
        int height = Math.max(1, getResources().getDisplayMetrics().heightPixels);
        int density = Math.max(1, getResources().getDisplayMetrics().densityDpi);

        try {
            verificationReader = ImageReader.newInstance(
                    width, height, PixelFormat.RGBA_8888, 2);

            verificationReader.setOnImageAvailableListener(reader -> {
                Image image = null;
                try {
                    image = reader.acquireLatestImage();
                    if (image == null || verificationFinished) return;

                    if (isMostlyMagenta(image)) {
                        verificationFinished = true;
                        getSharedPreferences("state", MODE_PRIVATE).edit()
                                .putString("mirror_error_code", "OVERLAY_STILL_CAPTURED")
                                .apply();
                        setMirrorError("Android fångar fortfarande spegelytan");
                        mainHandler.post(this::stopSelf);
                        return;
                    }

                    verificationFinished = true;
                    mainHandler.post(() -> activateMirrorOutput(width, height));
                } catch (Throwable t) {
                    verificationFinished = true;
                    setMirrorError("kunde inte verifiera overlay-undantaget");
                    mainHandler.post(this::stopSelf);
                } finally {
                    if (image != null) {
                        try { image.close(); } catch (Throwable ignored) {}
                    }
                }
            }, mainHandler);

            virtualDisplay = projection.createVirtualDisplay(
                    "ProjektorlageVerify",
                    width,
                    height,
                    density,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    verificationReader.getSurface(),
                    null,
                    mainHandler);
        } catch (Throwable t) {
            captureStarted = false;
            setMirrorError("kunde inte verifiera overlay-undantaget");
            stopSelf();
        }
    }

    private void activateMirrorOutput(int width, int height) {
        try {
            if (renderer != null) renderer.setVerificationMode(false);
            if (glView != null) glView.requestRender();

            sourceTexture.setDefaultBufferSize(width, height);
            Surface output = new Surface(sourceTexture);

            if (virtualDisplay == null) {
                setMirrorError("verifieringsdisplay saknas");
                stopSelf();
                return;
            }

            virtualDisplay.setSurface(output);

            if (captureSurface != null) {
                try { captureSurface.release(); } catch (Throwable ignored) {}
            }
            captureSurface = output;

            if (verificationReader != null) {
                try { verificationReader.close(); } catch (Throwable ignored) {}
                verificationReader = null;
            }

            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("overlay_excluded", true)
                    .remove("mirror_error")
                    .remove("mirror_error_code")
                    .apply();
        } catch (Throwable t) {
            setMirrorError("kunde inte växla till spegelbilden");
            stopSelf();
        }
    }

    private boolean isMostlyMagenta(Image image) {
        Image.Plane[] planes = image.getPlanes();
        if (planes == null || planes.length == 0) return true;

        Image.Plane plane = planes[0];
        ByteBuffer buffer = plane.getBuffer();
        int pixelStride = plane.getPixelStride();
        int rowStride = plane.getRowStride();
        if (buffer == null || pixelStride < 4 || rowStride <= 0) return true;

        int width = image.getWidth();
        int height = image.getHeight();
        int[][] points = new int[][] {
                {width / 2, height / 2},
                {width / 4, height / 4},
                {3 * width / 4, height / 4},
                {width / 4, 3 * height / 4},
                {3 * width / 4, 3 * height / 4}
        };

        int magenta = 0;
        for (int[] point : points) {
            int x = Math.max(0, Math.min(width - 1, point[0]));
            int y = Math.max(0, Math.min(height - 1, point[1]));
            int offset = y * rowStride + x * pixelStride;
            if (offset < 0 || offset + 2 >= buffer.limit()) continue;

            int r = buffer.get(offset) & 0xff;
            int g = buffer.get(offset + 1) & 0xff;
            int b = buffer.get(offset + 2) & 0xff;
            if (r > 210 && g < 80 && b > 210) magenta++;
        }

        return magenta >= 3;
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
                .setContentText("Spegelvänd helskärmsbild aktiv")
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

        if (glView != null) {
            try { glView.onPause(); } catch (Throwable ignored) {}
        }

        overlay = null;
        glView = null;
        renderer = null;
        sourceTexture = null;

        glOutputSurfaceReady = false;
        sourceTextureReady = false;
        skipScreenshotInstalled = false;
        captureStarted = false;
        verificationFinished = false;

        if (verificationReader != null) {
            try { verificationReader.close(); } catch (Throwable ignored) {}
            verificationReader = null;
        }

        skipAttempts = 0;
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

        private SurfaceTexture surfaceTexture;
        private ReadyListener readyListener;
        private int renderedFrames;
        private volatile boolean verificationMode = true;

        private final float[] vertices = {
                -1f, -1f,
                 1f, -1f,
                -1f,  1f,
                 1f,  1f
        };

        // Keep canonical texture coordinates. The horizontal flip happens AFTER
        // SurfaceTexture's own rotation/crop transform in the vertex shader.
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

        void setVerificationMode(boolean enabled) {
            verificationMode = enabled;
        }

        @Override
        public void onSurfaceCreated(GL10 gl, EGLConfig config) {
            program = createProgram(VERTEX_SHADER, FRAGMENT_SHADER);

            aPosition = GLES20.glGetAttribLocation(program, "aPosition");
            aTexCoord = GLES20.glGetAttribLocation(program, "aTexCoord");
            uTextureMatrix = GLES20.glGetUniformLocation(program, "uTextureMatrix");
            uTexture = GLES20.glGetUniformLocation(program, "uTexture");

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
            if (verificationMode) {
                GLES20.glClearColor(1f, 0f, 1f, 1f);
                GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT);
                return;
            }

            if (surfaceTexture == null) return;

            try {
                surfaceTexture.updateTexImage();
                surfaceTexture.getTransformMatrix(textureMatrix);
            } catch (Throwable ignored) {
                return;
            }

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

            GLES20.glActiveTexture(GLES20.GL_TEXTURE0);
            GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, oesTextureId);
            GLES20.glUniform1i(uTexture, 0);

            GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4);

            renderedFrames++;
            if (renderedFrames == 2 && skipScreenshotInstalled) {
                mainHandler.post(() -> getSharedPreferences("state", MODE_PRIVATE).edit()
                        .putBoolean("mirror_ready", true)
                        .remove("mirror_error")
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
                "precision mediump float;\n" +
                "uniform samplerExternalOES uTexture;\n" +
                "varying vec2 vTexCoord;\n" +
                "void main() {\n" +
                "  gl_FragColor = texture2D(uTexture, vTexCoord);\n" +
                "}\n";
    }

    private interface ReadyListener {
        void onReady(SurfaceTexture texture);
    }
}
''')

b = build.read_text()
if "org.lsposed.hiddenapibypass:hiddenapibypass:6.1" not in b:
    if "dependencies {" in b:
        b = b.replace(
            "dependencies {",
            "dependencies {\n    implementation 'org.lsposed.hiddenapibypass:hiddenapibypass:6.1'",
            1)
    else:
        b += "\n\ndependencies {\n    implementation 'org.lsposed.hiddenapibypass:hiddenapibypass:6.1'\n}\n"
b = b.replace("versionCode 24", "versionCode 25", 1)
b = b.replace("versionName '2.4.0'", "versionName '2.5.0'", 1)
build.write_text(b)

print("v2.5 public SurfaceView SurfaceControl mirror path applied")
