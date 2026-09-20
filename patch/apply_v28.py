from pathlib import Path
import re, sys

root = Path(sys.argv[1])
perm = root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java"
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

# --- Keep Samsung adaptive/HBM mode alive instead of forcing manual mode. ---
s = svc.read_text()
pat = re.compile(r'''    private boolean forceProjectorBrightness\(\) \{.*?\n    \}\n\n    private void startBrightnessKick\(\)''', re.S)
m = pat.search(s)
if not m:
    raise SystemExit("v2.8: forceProjectorBrightness block not found")

replacement = r'''    private boolean forceProjectorBrightness() {
        if (!Settings.System.canWrite(this)) {
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("brightness_verified", false)
                    .apply();
            return false;
        }

        try {
            android.content.SharedPreferences prefs =
                    getSharedPreferences("state", MODE_PRIVATE);

            int currentMode = Settings.System.getInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS_MODE,
                    Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL);
            int currentBrightness = Settings.System.getInt(
                    getContentResolver(),
                    Settings.System.SCREEN_BRIGHTNESS,
                    128);

            if (!prefs.getBoolean("brightness_backup_valid", false)) {
                prefs.edit()
                        .putBoolean("brightness_backup_valid", true)
                        .putInt("brightness_backup_mode", currentMode)
                        .putInt("brightness_backup_value", currentBrightness)
                        .apply();
            }

            int maximum = getDeviceBrightnessMaximum();
            boolean adaptive = currentMode == Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC;
            int actual = currentBrightness;
            boolean verified;

            if (adaptive) {
                // Samsung can use high-brightness/HBM above the normal manual range
                // while adaptive brightness is active. Switching it to MANUAL can
                // visibly DIM the panel even when SCREEN_BRIGHTNESS is set to max.
                // Keep the device's adaptive/HBM path intact. The mirror overlay
                // separately requests BRIGHTNESS_OVERRIDE_FULL.
                verified = true;
            } else {
                Settings.System.putInt(
                        getContentResolver(),
                        Settings.System.SCREEN_BRIGHTNESS,
                        maximum);

                actual = Settings.System.getInt(
                        getContentResolver(),
                        Settings.System.SCREEN_BRIGHTNESS,
                        currentBrightness);

                verified = actual >= Math.max(1, maximum - 1);
            }

            prefs.edit()
                    .putInt("projector_brightness_max", maximum)
                    .putInt("projector_brightness_actual", actual)
                    .putBoolean("projector_adaptive_brightness_preserved", adaptive)
                    .putBoolean("brightness_verified", verified)
                    .apply();

            return verified;
        } catch (Exception ignored) {
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putBoolean("brightness_verified", false)
                    .apply();
            return false;
        }
    }

    private void startBrightnessKick()'''
s = s[:m.start()] + replacement + s[m.end():]
svc.write_text(s)

# --- Default to a black-preserving projector gamma instead of NATURAL. ---
p = perm.read_text()
p = p.replace('.putString("picture_profile", "NATURAL")',
              '.putString("picture_profile", "PROJECTOR")', 1)
perm.write_text(p)

# --- Brighten captured pixels without a white/gray veil. ---
m = mirror.read_text()

m = m.replace(
    'import android.graphics.PixelFormat;\nimport android.graphics.SurfaceTexture;',
    'import android.graphics.PixelFormat;\n'
    'import android.graphics.RenderEffect;\n'
    'import android.graphics.RuntimeShader;\n'
    'import android.graphics.SurfaceTexture;',
    1)

if 'import android.os.Build;' not in m:
    m = m.replace('import android.os.Handler;',
                  'import android.os.Build;\nimport android.os.Handler;', 1)

if 'import android.content.pm.ActivityInfo;' not in m:
    m = m.replace('import android.content.Intent;',
                  'import android.content.Intent;\nimport android.content.pm.ActivityInfo;', 1)

m = m.replace(
    '    private int updatedFrames;\n\n    private int captureWidth;',
    '    private int updatedFrames;\n'
    '    private RuntimeShader toneShader;\n'
    '    private String currentProfile = "PROJECTOR";\n\n'
    '    private int captureWidth;',
    1)

old_profile = '''        if (ACTION_PROFILE.equals(action)) {
            return START_NOT_STICKY;
        }'''
new_profile = '''        if (ACTION_PROFILE.equals(action)) {
            String profile = intent.getStringExtra(EXTRA_PROFILE);
            applyPictureProfile(profile);
            return START_NOT_STICKY;
        }'''
if old_profile not in m:
    raise SystemExit("v2.8: ACTION_PROFILE block not found")
m = m.replace(old_profile, new_profile, 1)

old_texture = '''        textureView = new TextureView(this);
        textureView.setOpaque(true);
        textureView.setScaleX(-1f);
        textureView.setAlpha(0f);'''
new_texture = '''        textureView = new TextureView(this);
        textureView.setOpaque(true);
        textureView.setScaleX(-1f);
        textureView.setAlpha(0f);

        currentProfile = getSharedPreferences("state", MODE_PRIVATE)
                .getString("picture_profile", "PROJECTOR");
        applyPictureProfile(currentProfile);'''
if old_texture not in m:
    raise SystemExit("v2.8: TextureView setup block not found")
m = m.replace(old_texture, new_texture, 1)

old_lp = '''        lp.gravity = Gravity.TOP | Gravity.START;
        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL;
        lp.setTitle("Projektorläge spegel");'''
new_lp = '''        lp.gravity = Gravity.TOP | Gravity.START;
        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL;

        // MediaProjection is normally SDR/tone-mapped. On Android 15+ explicitly
        // reserve no extra HDR headroom so SDR white does not get unnecessarily dim.
        if (Build.VERSION.SDK_INT >= 35) {
            lp.setDesiredHdrHeadroom(1.0f);
        }
        lp.setColorMode(ActivityInfo.COLOR_MODE_DEFAULT);
        lp.setTitle("Projektorläge spegel");'''
if old_lp not in m:
    raise SystemExit("v2.8: Window brightness block not found")
m = m.replace(old_lp, new_lp, 1)

anchor = '''    private void setMirrorError(String message, String code) {'''
if anchor not in m:
    raise SystemExit("v2.8: setMirrorError anchor not found")

methods = r'''    private void applyPictureProfile(String profile) {
        if (profile == null) profile = "PROJECTOR";
        currentProfile = profile;

        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("picture_profile", currentProfile)
                .apply();

        if (textureView == null || Build.VERSION.SDK_INT < 33) return;

        try {
            if ("NATURAL".equals(currentProfile)) {
                textureView.setRenderEffect(null);
                toneShader = null;
                return;
            }

            // Gamma lift only: black remains 0, white remains 1. There is no
            // translucent white layer, so we do not recreate the old gray veil.
            float gamma = "MAX".equals(currentProfile) ? 0.64f : 0.74f;
            float saturation = "MAX".equals(currentProfile) ? 1.05f : 1.025f;

            String agsl =
                    "uniform shader input;\n" +
                    "uniform float gamma;\n" +
                    "uniform float saturation;\n" +
                    "half4 main(float2 p) {\n" +
                    "  half4 c = input.eval(p);\n" +
                    "  float3 rgb = clamp(float3(c.rgb), 0.0, 1.0);\n" +
                    "  float lum = dot(rgb, float3(0.2126, 0.7152, 0.0722));\n" +
                    "  if (lum <= 0.001) return c;\n" +
                    "  float target = pow(lum, gamma);\n" +
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
        } catch (Throwable ignored) {
            // Never sacrifice working mirroring for a picture-profile failure.
            try { textureView.setRenderEffect(null); } catch (Throwable ignored2) {}
            toneShader = null;
        }
    }

'''
m = m.replace(anchor, methods + anchor, 1)
mirror.write_text(m)

b = build.read_text()
b = b.replace("versionCode 27", "versionCode 28", 1)
b = b.replace("versionName '2.7.0'", "versionName '2.8.0'", 1)
build.write_text(b)

print("v2.8 Samsung brightness + black-preserving gamma fix applied")
