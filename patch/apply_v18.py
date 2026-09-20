from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
activity = root / "app/src/main/java/se/projektorlage/app/MirrorPermissionActivity.java"
mirror = root / "app/src/main/java/se/projektorlage/app/MirrorOverlayService.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

# --- MainActivity: STARTA PROJEKTOR now starts the mirror pipeline itself ---
s = main.read_text()

old = '''    private void startProjectorAutomatic() {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("rotation_mode", "REVERSE")
                .putInt("light_boost_percent", 12)
                .putBoolean("auto_launch_netflix", true)
                .apply();

        requestOverlayAndEnable();
    }'''
new = '''    private void startProjectorAutomatic() {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("rotation_mode", "REVERSE")
                .putInt("light_boost_percent", 12)
                .putBoolean("auto_launch_netflix", false)
                .apply();

        startActivity(new Intent(this, MirrorPermissionActivity.class)
                .putExtra("auto_projector", true));
    }'''
if old not in s:
    raise SystemExit("Patch misslyckades: startProjectorAutomatic")
s = s.replace(old, new, 1)

s = s.replace(
    "Tryck Starta. Appen ställer in bildriktning och ljus, startar fjärren och öppnar Netflix automatiskt.",
    "Tryck Starta. Appen spegelvänder skärmen, väljer rätt bildriktning, maxar ljuset, startar fjärren och öppnar Netflix automatiskt.",
    1
)
s = s.replace("SPEGELVÄND VALD APP", "STARTA SPEGELPROJEKTION", 1)
main.write_text(s)

# --- MirrorPermissionActivity: one guided system consent, then everything starts automatically ---
activity.write_text(r'''package se.projektorlage.app;

import android.app.Activity;
import android.content.Intent;
import android.media.projection.MediaProjectionConfig;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Toast;

public class MirrorPermissionActivity extends Activity {
    private static final int REQ_CAPTURE = 9021;

    private MediaProjectionManager projectionManager;
    private boolean captureRequested;
    private boolean overlaySettingsOpened;
    private boolean writeSettingsOpened;

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
                Toast.makeText(this,
                        "Projektorläge behöver tillåtelsen 'Visa över andra appar'.",
                        Toast.LENGTH_LONG).show();
                finish();
                return;
            }
            continueSetup();
            return;
        }

        if (writeSettingsOpened) {
            writeSettingsOpened = false;
            if (!Settings.System.canWrite(this)) {
                Toast.makeText(this,
                        "Projektorläge behöver 'Ändra systeminställningar' för rotation och maxljus.",
                        Toast.LENGTH_LONG).show();
                finish();
                return;
            }
            continueSetup();
        }
    }

    private void continueSetup() {
        if (!Settings.canDrawOverlays(this)) {
            overlaySettingsOpened = true;
            Intent settings = new Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName()));
            startActivity(settings);
            return;
        }

        if (!Settings.System.canWrite(this)) {
            writeSettingsOpened = true;
            Intent settings = new Intent(
                    Settings.ACTION_MANAGE_WRITE_SETTINGS,
                    Uri.parse("package:" + getPackageName()));
            startActivity(settings);
            return;
        }

        if (captureRequested) return;
        captureRequested = true;

        Toast.makeText(this,
                "Android kräver ett godkännande per projektorsession. Tryck 'Dela hela skärmen'.",
                Toast.LENGTH_LONG).show();

        Intent captureIntent;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            captureIntent = projectionManager.createScreenCaptureIntent(
                    MediaProjectionConfig.createConfigForDefaultDisplay());
        } else {
            captureIntent = projectionManager.createScreenCaptureIntent();
        }
        startActivityForResult(captureIntent, REQ_CAPTURE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_CAPTURE) return;

        if (resultCode != RESULT_OK || data == null) {
            Toast.makeText(this, "Projektorstart avbröts.", Toast.LENGTH_SHORT).show();
            finish();
            return;
        }

        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("rotation_mode", "REVERSE")
                .putInt("light_boost_percent", 12)
                .putBoolean("auto_launch_netflix", false)
                .apply();

        Intent projector = new Intent(this, RotationService.class);
        projector.setAction(RotationService.ACTION_ENABLE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(projector);
        } else {
            startService(projector);
        }

        Intent mirror = new Intent(this, MirrorOverlayService.class);
        mirror.setAction(MirrorOverlayService.ACTION_START);
        mirror.putExtra(MirrorOverlayService.EXTRA_RESULT_CODE, resultCode);
        mirror.putExtra(MirrorOverlayService.EXTRA_RESULT_DATA, data);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(mirror);
        } else {
            startService(mirror);
        }

        Intent netflix = getPackageManager().getLaunchIntentForPackage("com.netflix.mediaclient");
        if (netflix != null) {
            netflix.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(netflix);
        } else {
            Toast.makeText(this, "Netflix hittades inte på mobilen.", Toast.LENGTH_LONG).show();
        }

        finish();
    }
}
''')

# --- Mirror overlay: mark the mirrored output secure so it is NOT re-captured.
# This removes the hall-of-mirrors feedback loop during full-screen capture. ---
s = mirror.read_text()
old_flags = '''        int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS;'''
new_flags = '''        int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                | WindowManager.LayoutParams.FLAG_SECURE;'''
if old_flags not in s:
    raise SystemExit("Patch misslyckades: mirror overlay flags")
s = s.replace(old_flags, new_flags, 1)
s = s.replace(
    "Den valda appen visas horisontellt spegelvänd. Tryck för att stoppa.",
    "Skärmen visas horisontellt spegelvänd utan att spegelbilden fångas igen.",
    1
)
mirror.write_text(s)

# --- Light boost overlay must also stay out of MediaProjection capture. ---
s = svc.read_text()
old_boost = '''        int overlayFlags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON;'''
new_boost = '''        int overlayFlags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                | WindowManager.LayoutParams.FLAG_SECURE;'''
if old_boost not in s:
    raise SystemExit("Patch misslyckades: boost overlay flags")
s = s.replace(old_boost, new_boost, 1)
svc.write_text(s)

# --- Version ---
b = build.read_text()
b = b.replace("versionCode 17", "versionCode 18", 1)
b = b.replace("versionName '1.7.0'", "versionName '1.8.0'", 1)
build.write_text(b)

print("v1.8 integrated mirror projector patch applied")
