from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

s = main.read_text()

s = replace_once(s,
'''    private boolean enableAfterOverlayPermission;
''',
'''    private boolean enableAfterOverlayPermission;
    private boolean enableAfterWriteSettings;
''',
"write settings flag")

s = replace_once(s,
'''        if (enableAfterOverlayPermission && Settings.canDrawOverlays(this)) {
            enableAfterOverlayPermission = false;
            enableProjectorMode();
        }
        refreshProjectorStatus();''',
'''        if (enableAfterOverlayPermission && Settings.canDrawOverlays(this)) {
            enableAfterOverlayPermission = false;
            requestOverlayAndEnable();
        }
        if (enableAfterWriteSettings && Settings.System.canWrite(this)) {
            enableAfterWriteSettings = false;
            enableProjectorMode();
        }
        refreshProjectorStatus();''',
"onResume permissions")

s = replace_once(s,
'''Den här mobilen sitter vid linsen och spelar Netflix. När projektorläget är aktivt startas även fjärrservern.''',
'''Den här mobilen sitter vid linsen och spelar Netflix. Projektorläget låser skärmen i vald landskapsriktning och startar fjärrservern.''',
"projector intro")

s = replace_once(s,
'''        Button reverse = makeButton("REVERSE 180°");
        Button normal = makeButton("NORMAL");''',
'''        Button reverse = makeButton("LANDSKAP ↺");
        Button normal = makeButton("LANDSKAP ↻");''',
"local rotation labels")

s = replace_once(s,
'''        Button brightness = makeButton("TILLÅT FJÄRRSTYRD LJUSSTYRKA");''',
'''        Button brightness = makeButton("TILLÅT ROTATION + LJUSSTYRKA");''',
"permission label")

s = replace_once(s,
'''        Button remoteReverse = makeButton("REVERSE 180°");
        Button remoteNormal = makeButton("NORMAL");''',
'''        Button remoteReverse = makeButton("LANDSKAP ↺");
        Button remoteNormal = makeButton("LANDSKAP ↻");''',
"remote rotation labels")

s = replace_once(s,
'''        if (!Settings.canDrawOverlays(this)) {
            enableAfterOverlayPermission = true;
            Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
            startActivity(intent);
            return;
        }
        enableProjectorMode();''',
'''        if (!Settings.canDrawOverlays(this)) {
            enableAfterOverlayPermission = true;
            Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
            startActivity(intent);
            return;
        }
        if (!Settings.System.canWrite(this)) {
            enableAfterWriteSettings = true;
            Toast.makeText(this, "Tillåt Ändra systeminställningar – det behövs för att låsa skärmen åt rätt håll", Toast.LENGTH_LONG).show();
            Intent intent = new Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:" + getPackageName()));
            startActivity(intent);
            return;
        }
        enableProjectorMode();''',
"enable requires write settings")

s = replace_once(s,
'''        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "Aktivera projektorläget först", Toast.LENGTH_SHORT).show();
            requestOverlayAndEnable();
            return;
        }
        Intent intent = new Intent(this, RotationService.class);''',
'''        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "Aktivera projektorläget först", Toast.LENGTH_SHORT).show();
            requestOverlayAndEnable();
            return;
        }
        if (!Settings.System.canWrite(this)) {
            Toast.makeText(this, "Tillåt Ändra systeminställningar först", Toast.LENGTH_LONG).show();
            requestWriteSettings();
            return;
        }
        Intent intent = new Intent(this, RotationService.class);''',
"local rotation permission")

s = replace_once(s,
'''        Toast.makeText(this, reverse ? "Reverse 180° aktiverat" : "Normal landskap aktiverat", Toast.LENGTH_SHORT).show();''',
'''        Toast.makeText(this, reverse ? "Landskap ↺ aktiverat" : "Landskap ↻ aktiverat", Toast.LENGTH_SHORT).show();''',
"local rotation toast")

s = replace_once(s,
'''            Toast.makeText(this, "Ljusstyrning är redan tillåten", Toast.LENGTH_SHORT).show();''',
'''            Toast.makeText(this, "Rotation och ljusstyrning är redan tillåtna", Toast.LENGTH_SHORT).show();''',
"write settings toast")

s = replace_once(s,
'''            projectorStatus.setText("● Projektorläge PÅ – " + ("NORMAL".equals(rotationMode) ? "normal landscape" : "REVERSE 180°"));''',
'''            projectorStatus.setText("● Projektorläge PÅ – " + ("NORMAL".equals(rotationMode) ? "LANDSKAP ↻" : "LANDSKAP ↺"));''',
"status label")

s = replace_once(s,
'''        } else if ("ERR|BRIGHTNESS_PERMISSION".equals(response)) {
            remoteStatus.setText("Tillåt ljusstyrning på projektormobilen först.");
            remoteStatus.setTextColor(Color.rgb(255, 190, 120));''',
'''        } else if ("ERR|BRIGHTNESS_PERMISSION".equals(response)) {
            remoteStatus.setText("Tillåt rotation + ljusstyrka på projektormobilen först.");
            remoteStatus.setTextColor(Color.rgb(255, 190, 120));
        } else if ("ERR|ROTATION_PERMISSION".equals(response)) {
            remoteStatus.setText("På projektormobilen: tillåt 'Ändra systeminställningar'.");
            remoteStatus.setTextColor(Color.rgb(255, 190, 120));''',
"remote rotation permission response")

s = replace_once(s,
'''            case "ROTATE_REVERSE": return "REVERSE 180° aktiverat";
            case "ROTATE_NORMAL": return "normal landskap aktiverat";''',
'''            case "ROTATE_REVERSE": return "LANDSKAP ↺ aktiverat";
            case "ROTATE_NORMAL": return "LANDSKAP ↻ aktiverat";''',
"friendly rotation labels")

main.write_text(s)

s = svc.read_text()

s = replace_once(s,
'''import android.view.KeyEvent;
import android.view.View;''',
'''import android.view.KeyEvent;
import android.view.Surface;
import android.view.View;''',
"Surface import")

s = replace_once(s,
'''        if (ACTION_REVERSE.equals(action)) {
            saveRotationMode(true);
        } else if (ACTION_NORMAL.equals(action)) {
            saveRotationMode(false);
        }

        if (Settings.canDrawOverlays(this)) {''',
'''        if (ACTION_REVERSE.equals(action)) {
            saveRotationMode(true);
        } else if (ACTION_NORMAL.equals(action)) {
            saveRotationMode(false);
        }

        applySavedSystemRotation();

        if (Settings.canDrawOverlays(this)) {''',
"apply global rotation on start")

s = replace_once(s,
'''    private String setRotationMode(boolean reverse) {
        saveRotationMode(reverse);
        new Handler(Looper.getMainLooper()).post(this::applySavedOrientation);
        return reverse ? "OK|ROTATE_REVERSE" : "OK|ROTATE_NORMAL";
    }''',
'''    private String setRotationMode(boolean reverse) {
        saveRotationMode(reverse);
        boolean systemApplied = applySystemRotation(reverse);
        new Handler(Looper.getMainLooper()).post(this::applySavedOrientation);
        if (!systemApplied) return "ERR|ROTATION_PERMISSION";
        return reverse ? "OK|ROTATE_REVERSE" : "OK|ROTATE_NORMAL";
    }

    private boolean applySavedSystemRotation() {
        String mode = getSharedPreferences("state", MODE_PRIVATE).getString("rotation_mode", "REVERSE");
        return applySystemRotation(!"NORMAL".equals(mode));
    }

    private boolean applySystemRotation(boolean reverse) {
        if (!Settings.System.canWrite(this)) return false;
        try {
            captureOriginalRotationSettings();
            Settings.System.putInt(getContentResolver(), Settings.System.ACCELEROMETER_ROTATION, 0);
            int target = reverse ? Surface.ROTATION_270 : Surface.ROTATION_90;
            boolean ok = Settings.System.putInt(getContentResolver(), Settings.System.USER_ROTATION, target);
            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putInt("forced_surface_rotation", target)
                    .apply();
            return ok;
        } catch (Exception e) {
            return false;
        }
    }

    private void captureOriginalRotationSettings() {
        android.content.SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);
        if (prefs.getBoolean("rotation_backup_valid", false)) return;
        try {
            int autoRotate = Settings.System.getInt(getContentResolver(), Settings.System.ACCELEROMETER_ROTATION, 1);
            int userRotation = Settings.System.getInt(getContentResolver(), Settings.System.USER_ROTATION, Surface.ROTATION_0);
            prefs.edit()
                    .putBoolean("rotation_backup_valid", true)
                    .putInt("rotation_backup_auto", autoRotate)
                    .putInt("rotation_backup_user", userRotation)
                    .apply();
        } catch (Exception ignored) {
        }
    }

    private void restoreOriginalRotationSettings() {
        if (!Settings.System.canWrite(this)) return;
        android.content.SharedPreferences prefs = getSharedPreferences("state", MODE_PRIVATE);
        if (!prefs.getBoolean("rotation_backup_valid", false)) return;
        try {
            int autoRotate = prefs.getInt("rotation_backup_auto", 1);
            int userRotation = prefs.getInt("rotation_backup_user", Surface.ROTATION_0);
            Settings.System.putInt(getContentResolver(), Settings.System.USER_ROTATION, userRotation);
            Settings.System.putInt(getContentResolver(), Settings.System.ACCELEROMETER_ROTATION, autoRotate);
        } catch (Exception ignored) {
        } finally {
            prefs.edit().putBoolean("rotation_backup_valid", false).remove("forced_surface_rotation").apply();
        }
    }''',
"system rotation implementation")

s = replace_once(s,
'''    private void shutdownEverything() {
        stopRemoteServer();
        removeOrientationOverlay();''',
'''    private void shutdownEverything() {
        stopRemoteServer();
        restoreOriginalRotationSettings();
        removeOrientationOverlay();''',
"restore rotation on shutdown")

s = replace_once(s,
'''                .setContentText("Reverse landscape + fjärrkontroll på lokala nätverket")''',
'''                .setContentText("Låst landskapsriktning + fjärrkontroll på lokala nätverket")''',
"notification text")

svc.write_text(s)

s = build.read_text()
s = s.replace("versionCode 3", "versionCode 4", 1)
s = s.replace("versionName '0.3.0'", "versionName '0.4.0'", 1)
build.write_text(s)

print("v0.4 patch applied")
