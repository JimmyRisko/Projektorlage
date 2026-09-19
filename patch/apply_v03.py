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
'''        Button enable = makeButton("AKTIVERA PROJEKTOR + FJÄRR");
        enable.setOnClickListener(v -> requestOverlayAndEnable());
        panel.addView(enable, full(0, dp(10)));

        Button netflix = makeButton("ÖPPNA NETFLIX");''',
'''        Button enable = makeButton("AKTIVERA PROJEKTOR + FJÄRR");
        enable.setOnClickListener(v -> requestOverlayAndEnable());
        panel.addView(enable, full(0, dp(10)));

        panel.addView(text("Bildriktning", 14, muted(), true), full(dp(6), dp(6)));
        LinearLayout rotationRow = new LinearLayout(this);
        rotationRow.setOrientation(LinearLayout.HORIZONTAL);
        rotationRow.setWeightSum(2f);
        Button reverse = makeButton("REVERSE 180°");
        Button normal = makeButton("NORMAL");
        reverse.setOnClickListener(v -> setLocalRotation(true));
        normal.setOnClickListener(v -> setLocalRotation(false));
        rotationRow.addView(reverse, weighted(dp(5)));
        rotationRow.addView(normal, weighted(0));
        panel.addView(rotationRow, full(0, dp(10)));

        Button netflix = makeButton("ÖPPNA NETFLIX");''',
"lokala rotationsknappar")

s = replace_once(s,
'''        Button netflix = makeButton("ÖPPNA NETFLIX PÅ PROJEKTORN");
        netflix.setOnClickListener(v -> sendRemote("NETFLIX"));
        panel.addView(netflix, full(0, dp(10)));

        Button playPause = makeButton("SPELA / PAUSA");''',
'''        Button netflix = makeButton("ÖPPNA NETFLIX PÅ PROJEKTORN");
        netflix.setOnClickListener(v -> sendRemote("NETFLIX"));
        panel.addView(netflix, full(0, dp(10)));

        panel.addView(text("Bildriktning på projektormobilen", 14, muted(), true), full(dp(6), dp(6)));
        LinearLayout remoteRotationRow = new LinearLayout(this);
        remoteRotationRow.setOrientation(LinearLayout.HORIZONTAL);
        remoteRotationRow.setWeightSum(2f);
        Button remoteReverse = makeButton("REVERSE 180°");
        Button remoteNormal = makeButton("NORMAL");
        remoteReverse.setOnClickListener(v -> sendRemote("ROTATE_REVERSE"));
        remoteNormal.setOnClickListener(v -> sendRemote("ROTATE_NORMAL"));
        remoteRotationRow.addView(remoteReverse, weighted(dp(5)));
        remoteRotationRow.addView(remoteNormal, weighted(0));
        panel.addView(remoteRotationRow, full(0, dp(10)));

        Button playPause = makeButton("SPELA / PAUSA");''',
"fjärrens rotationsknappar")

s = replace_once(s,
'''    private void requestWriteSettings() {''',
'''    private void setLocalRotation(boolean reverse) {
        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "Aktivera projektorläget först", Toast.LENGTH_SHORT).show();
            requestOverlayAndEnable();
            return;
        }
        Intent intent = new Intent(this, RotationService.class);
        intent.setAction(reverse ? RotationService.ACTION_REVERSE : RotationService.ACTION_NORMAL);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent);
        else startService(intent);
        Toast.makeText(this, reverse ? "Reverse 180° aktiverat" : "Normal landskap aktiverat", Toast.LENGTH_SHORT).show();
        uiHandler.postDelayed(this::refreshProjectorStatus, 250);
    }

    private void requestWriteSettings() {''',
"lokal rotationsmetod")

s = replace_once(s,
'''        String pin = prefs.getString("pair_pin", "------");

        if (enabled) {
            projectorStatus.setText("● Projektorläge PÅ – reverse landscape");''',
'''        String pin = prefs.getString("pair_pin", "------");
        String rotationMode = prefs.getString("rotation_mode", "REVERSE");

        if (enabled) {
            projectorStatus.setText("● Projektorläge PÅ – " + ("NORMAL".equals(rotationMode) ? "normal landscape" : "REVERSE 180°"));''',
"rotationsstatus")

s = replace_once(s,
'''            case "NETFLIX": return "Netflix startas";
            case "STOPPING": return "projektorläget stängs";''',
'''            case "NETFLIX": return "Netflix startas";
            case "ROTATE_REVERSE": return "REVERSE 180° aktiverat";
            case "ROTATE_NORMAL": return "normal landskap aktiverat";
            case "STOPPING": return "projektorläget stängs";''',
"fjärrsvar")

main.write_text(s)

s = svc.read_text()

s = replace_once(s,
'''    public static final String ACTION_ENABLE = "se.projektorlage.app.ENABLE";
    public static final String ACTION_DISABLE = "se.projektorlage.app.DISABLE";''',
'''    public static final String ACTION_ENABLE = "se.projektorlage.app.ENABLE";
    public static final String ACTION_DISABLE = "se.projektorlage.app.DISABLE";
    public static final String ACTION_REVERSE = "se.projektorlage.app.REVERSE";
    public static final String ACTION_NORMAL = "se.projektorlage.app.NORMAL";''',
"service actions")

s = replace_once(s,
'''        startForeground(NOTIFICATION_ID, buildNotification());

        if (Settings.canDrawOverlays(this)) {
            addOrientationOverlay();''',
'''        startForeground(NOTIFICATION_ID, buildNotification());

        if (ACTION_REVERSE.equals(action)) {
            saveRotationMode(true);
        } else if (ACTION_NORMAL.equals(action)) {
            saveRotationMode(false);
        }

        if (Settings.canDrawOverlays(this)) {
            addOrientationOverlay();
            applySavedOrientation();''',
"service start rotation")

s = replace_once(s,
'''        params.screenOrientation = ActivityInfo.SCREEN_ORIENTATION_REVERSE_LANDSCAPE;
        params.setTitle("Projektorläge rotation lock");''',
'''        params.screenOrientation = desiredOrientation();
        params.setTitle("Projektorläge rotation lock");''',
"overlay orientation")

s = replace_once(s,
'''    private void removeOrientationOverlay() {''',
'''    private int desiredOrientation() {
        String mode = getSharedPreferences("state", MODE_PRIVATE).getString("rotation_mode", "REVERSE");
        return "NORMAL".equals(mode)
                ? ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
                : ActivityInfo.SCREEN_ORIENTATION_REVERSE_LANDSCAPE;
    }

    private void saveRotationMode(boolean reverse) {
        getSharedPreferences("state", MODE_PRIVATE).edit()
                .putString("rotation_mode", reverse ? "REVERSE" : "NORMAL")
                .apply();
    }

    private void applySavedOrientation() {
        if (orientationView == null || windowManager == null) return;
        try {
            WindowManager.LayoutParams params = (WindowManager.LayoutParams) orientationView.getLayoutParams();
            params.screenOrientation = desiredOrientation();
            windowManager.updateViewLayout(orientationView, params);
        } catch (Exception ignored) {
        }
    }

    private String setRotationMode(boolean reverse) {
        saveRotationMode(reverse);
        new Handler(Looper.getMainLooper()).post(this::applySavedOrientation);
        return reverse ? "OK|ROTATE_REVERSE" : "OK|ROTATE_NORMAL";
    }

    private void removeOrientationOverlay() {''',
"orientation helpers")

s = replace_once(s,
'''            case "NETFLIX":
                return openNetflix();
            case "STOP":''',
'''            case "NETFLIX":
                return openNetflix();
            case "ROTATE_REVERSE":
                return setRotationMode(true);
            case "ROTATE_NORMAL":
                return setRotationMode(false);
            case "STOP":''',
"remote rotation commands")

svc.write_text(s)

s = build.read_text()
s = s.replace("versionCode 2", "versionCode 3", 1)
s = s.replace("versionName '0.2.0'", "versionName '0.3.0'", 1)
build.write_text(s)
print("v0.3 patch applied")
