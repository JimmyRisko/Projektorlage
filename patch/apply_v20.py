from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

# ---------- MainActivity: replace old white-overlay boost controls with picture profiles ----------
s = main.read_text()

old = '''        LinearLayout boostRow = new LinearLayout(this);
        boostRow.setOrientation(LinearLayout.HORIZONTAL);
        boostRow.setWeightSum(3f);
        Button boostOff = makeButton("BOOST AV");
        Button boost12 = makeButton("+12%");
        Button boost25 = makeButton("+25%");
        boostOff.setOnClickListener(v -> sendRemote("BOOST_0"));
        boost12.setOnClickListener(v -> sendRemote("BOOST_12"));
        boost25.setOnClickListener(v -> sendRemote("BOOST_25"));
        boostRow.addView(boostOff, weighted(dp(4)));
        boostRow.addView(boost12, weighted(dp(4)));
        boostRow.addView(boost25, weighted(0));
        remoteAdvanced.addView(boostRow, full(0, dp(10)));'''
new = '''        remoteAdvanced.addView(text("Projektorbild", 14, muted(), true), full(dp(6), dp(6)));
        LinearLayout pictureRow = new LinearLayout(this);
        pictureRow.setOrientation(LinearLayout.HORIZONTAL);
        pictureRow.setWeightSum(3f);
        Button pictureNatural = makeButton("NATURLIG");
        Button pictureProjector = makeButton("PROJEKTOR");
        Button pictureMax = makeButton("MAX");
        pictureNatural.setOnClickListener(v -> sendRemote("PICTURE_NATURAL"));
        pictureProjector.setOnClickListener(v -> sendRemote("PICTURE_PROJECTOR"));
        pictureMax.setOnClickListener(v -> sendRemote("PICTURE_MAX"));
        pictureRow.addView(pictureNatural, weighted(dp(4)));
        pictureRow.addView(pictureProjector, weighted(dp(4)));
        pictureRow.addView(pictureMax, weighted(0));
        remoteAdvanced.addView(pictureRow, full(0, dp(10)));'''
if old not in s:
    raise SystemExit("Patch misslyckades: remote boost row")
s = s.replace(old, new, 1)

# Friendly response labels if present.
s = s.replace(
'''            case "BOOST_0": return "projektorboost av";
            case "BOOST_12": return "projektorboost +12%";
            case "BOOST_25": return "projektorboost +25%";''',
'''            case "PICTURE_NATURAL": return "naturlig bild";
            case "PICTURE_PROJECTOR": return "projektorbild";
            case "PICTURE_MAX": return "projektorbild max";''',
1)

# Set projector profile as the automatic default.
s = s.replace(
'''.putInt("light_boost_percent", 0)
                .putBoolean("auto_launch_netflix", false)''',
'''.putInt("light_boost_percent", 0)
                .putString("picture_profile", "PROJECTOR")
                .putBoolean("auto_launch_netflix", false)''',
1)

main.write_text(s)

# ---------- MirrorOverlayService: GPU tone curve, no gray overlay ----------
s = mirror.read_text()

# Imports
if "import android.graphics.RenderEffect;" not in s:
    s = s.replace(
        "import android.graphics.PixelFormat;",
        "import android.graphics.PixelFormat;\n"
        "import android.graphics.ColorMatrix;\n"
        "import android.graphics.ColorMatrixColorFilter;\n"
        "import android.graphics.RenderEffect;\n"
        "import android.graphics.RuntimeShader;",
        1
    )
if "import android.os.Build;" not in s:
    s = s.replace("import android.os.IBinder;", "import android.os.Build;\nimport android.os.IBinder;", 1)

# Actions/constants and field.
s = s.replace(
'''    public static final String ACTION_STOP = "se.projektorlage.app.MIRROR_STOP";
    public static final String EXTRA_RESULT_CODE = "result_code";''',
'''    public static final String ACTION_STOP = "se.projektorlage.app.MIRROR_STOP";
    public static final String ACTION_PROFILE = "se.projektorlage.app.MIRROR_PROFILE";
    public static final String EXTRA_PROFILE = "picture_profile";
    public static final String EXTRA_RESULT_CODE = "result_code";''',
1)

if "private RuntimeShader toneShader;" not in s:
    s = s.replace(
        "    private Surface captureSurface;",
        "    private Surface captureSurface;\n"
        "    private RuntimeShader toneShader;\n"
        "    private String currentProfile = \"PROJECTOR\";",
        1
    )

# Handle profile command without rebuilding projection.
needle = '''        if (ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }

        startForeground(NOTIFICATION_ID, buildNotification());'''
repl = '''        if (ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }

        if (ACTION_PROFILE.equals(intent.getAction())) {
            String profile = intent.getStringExtra(EXTRA_PROFILE);
            applyPictureProfile(profile);
            return START_NOT_STICKY;
        }

        startForeground(NOTIFICATION_ID, buildNotification());'''
if needle not in s:
    raise SystemExit("Patch misslyckades: mirror onStartCommand")
s = s.replace(needle, repl, 1)

# Set current profile from preference before constructing TextureView.
needle = '''        overlay = new FrameLayout(this);
        textureView = new TextureView(this);
        textureView.setScaleX(-1f);'''
repl = '''        overlay = new FrameLayout(this);
        textureView = new TextureView(this);
        textureView.setScaleX(-1f);

        currentProfile = getSharedPreferences("state", MODE_PRIVATE)
                .getString("picture_profile", "PROJECTOR");
        applyPictureProfile(currentProfile);'''
if needle not in s:
    raise SystemExit("Patch misslyckades: texture setup")
s = s.replace(needle, repl, 1)

# Add profile methods before releaseVirtualDisplay.
anchor = '''    private void releaseVirtualDisplay() {'''
if anchor not in s:
    raise SystemExit("Patch misslyckades: releaseVirtualDisplay anchor")

methods = r'''    private void applyPictureProfile(String profile) {
        if (profile == null) profile = "PROJECTOR";
        currentProfile = profile;
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("picture_profile", profile)
                .apply();

        if (textureView == null) return;

        try {
            if ("NATURAL".equals(profile)) {
                if (Build.VERSION.SDK_INT >= 31) textureView.setRenderEffect(null);
                return;
            }

            if (Build.VERSION.SDK_INT >= 33) {
                float gamma = "MAX".equals(profile) ? 0.72f : 0.84f;
                float saturation = "MAX".equals(profile) ? 1.08f : 1.04f;

                String agsl =
                        "uniform shader input;\n" +
                        "uniform float gamma;\n" +
                        "uniform float saturation;\n" +
                        "half4 main(float2 p) {\n" +
                        "  half4 c = input.eval(p);\n" +
                        "  float3 rgb = float3(c.rgb);\n" +
                        "  float lum = dot(rgb, float3(0.2126, 0.7152, 0.0722));\n" +
                        "  if (lum <= 0.001) return c;\n" +
                        "  float target = pow(clamp(lum, 0.0, 1.0), gamma);\n" +
                        "  float scale = target / max(lum, 0.0001);\n" +
                        "  float3 lifted = clamp(rgb * scale, 0.0, 1.0);\n" +
                        "  float l2 = dot(lifted, float3(0.2126, 0.7152, 0.0722));\n" +
                        "  float3 graded = clamp(float3(l2) + (lifted - float3(l2)) * saturation, 0.0, 1.0);\n" +
                        "  return half4(half3(graded), c.a);\n" +
                        "}";

                toneShader = new RuntimeShader(agsl);
                toneShader.setFloatUniform("gamma", gamma);
                toneShader.setFloatUniform("saturation", saturation);
                textureView.setRenderEffect(
                        RenderEffect.createRuntimeShaderEffect(toneShader, "input"));
                return;
            }

            // Android 12 fallback: simple gain preserves black at 0 while lifting the picture.
            if (Build.VERSION.SDK_INT >= 31) {
                float gain = "MAX".equals(profile) ? 1.16f : 1.08f;
                ColorMatrix matrix = new ColorMatrix(new float[] {
                        gain, 0f,   0f,   0f, 0f,
                        0f,   gain, 0f,   0f, 0f,
                        0f,   0f,   gain, 0f, 0f,
                        0f,   0f,   0f,   1f, 0f
                });
                textureView.setRenderEffect(
                        RenderEffect.createColorFilterEffect(
                                new ColorMatrixColorFilter(matrix)));
            }
        } catch (Throwable ignored) {
            // If a device/GPU rejects the shader, keep the unfiltered mirrored image.
            if (Build.VERSION.SDK_INT >= 31) {
                try { textureView.setRenderEffect(null); } catch (Throwable ignoredAgain) {}
            }
        }
    }

'''
s = s.replace(anchor, methods + anchor, 1)

mirror.write_text(s)

# ---------- RotationService: remote picture-profile commands ----------
s = svc.read_text()

needle = '''            case "BOOST_25":
                return setLightBoost(25);
            case "NETFLIX":'''
repl = '''            case "BOOST_25":
                return setLightBoost(25);
            case "PICTURE_NATURAL":
                return setMirrorPictureProfile("NATURAL");
            case "PICTURE_PROJECTOR":
                return setMirrorPictureProfile("PROJECTOR");
            case "PICTURE_MAX":
                return setMirrorPictureProfile("MAX");
            case "NETFLIX":'''
if needle not in s:
    raise SystemExit("Patch misslyckades: rotation command switch")
s = s.replace(needle, repl, 1)

anchor = '''    private String setLightBoost(int percent) {'''
if anchor not in s:
    raise SystemExit("Patch misslyckades: setLightBoost anchor")

helper = '''    private String setMirrorPictureProfile(String profile) {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("picture_profile", profile)
                .apply();

        Intent intent = new Intent(this, MirrorOverlayService.class);
        intent.setAction(MirrorOverlayService.ACTION_PROFILE);
        intent.putExtra(MirrorOverlayService.EXTRA_PROFILE, profile);
        try {
            startService(intent);
        } catch (Exception ignored) {
        }

        if ("NATURAL".equals(profile)) return "OK|PICTURE_NATURAL";
        if ("MAX".equals(profile)) return "OK|PICTURE_MAX";
        return "OK|PICTURE_PROJECTOR";
    }

'''
s = s.replace(anchor, helper + anchor, 1)
svc.write_text(s)

# ---------- Version ----------
b = build.read_text()
b = b.replace("versionCode 19", "versionCode 20", 1)
b = b.replace("versionName '1.9.0'", "versionName '2.0.0'", 1)
build.write_text(b)

print("v2.0 GPU projector picture profiles applied")
