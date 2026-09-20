from pathlib import Path
import re, sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
manifest = root / "app/src/main/AndroidManifest.xml"
build = root / "app/build.gradle"

def must_replace(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

# Manifest: Android 13+/Android 16 LAN permission.
m = manifest.read_text()
if "android.permission.NEARBY_WIFI_DEVICES" not in m:
    m = m.replace(
        '<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />',
        '<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />\n'
        '    <uses-permission android:name="android.permission.NEARBY_WIFI_DEVICES" android:usesPermissionFlags="neverForLocation" />',
        1
    )
manifest.write_text(m)

# MainActivity
s = main.read_text()

if "REQ_NEARBY_WIFI" not in s:
    s = s.replace(
        'private static final int REQ_NOTIFICATIONS = 2002;',
        'private static final int REQ_NOTIFICATIONS = 2002;\n'
        '    private static final int REQ_NEARBY_WIFI = 2003;',
        1
    )

s = s.replace(
    'askNotificationPermissionIfNeeded();',
    'askNotificationPermissionIfNeeded();\n        askNearbyWifiPermissionIfNeeded();',
    1
)

anchor = '''    private void askNotificationPermissionIfNeeded() {'''
if anchor in s and "askNearbyWifiPermissionIfNeeded" not in s[s.find(anchor)-300:s.find(anchor)]:
    method = '''    private void askNearbyWifiPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.NEARBY_WIFI_DEVICES}, REQ_NEARBY_WIFI);
        }
    }

'''
    s = s.replace(anchor, method + anchor, 1)

# Add local repair button after enable.
needle = '''        panel.addView(enable, full(0, dp(10)));'''
if needle in s and "REPARERA FJÄRR" not in s:
    s = s.replace(needle, needle + '''
        Button repair = makeButton("REPARERA FJÄRR");
        repair.setOnClickListener(v -> repairRemoteServer());
        panel.addView(repair, full(0, dp(10)));''', 1)

# Add method before disableProjectorMode.
anchor2 = '''    private void disableProjectorMode() {'''
if anchor2 in s and "private void repairRemoteServer()" not in s:
    method2 = '''    private void repairRemoteServer() {
        askNearbyWifiPermissionIfNeeded();
        Intent intent = new Intent(this, RotationService.class);
        intent.setAction(RotationService.ACTION_REPAIR);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent);
        else startService(intent);
        Toast.makeText(this, "Fjärrservern repareras", Toast.LENGTH_SHORT).show();
        uiHandler.postDelayed(this::refreshProjectorStatus, 700);
    }

'''
    s = s.replace(anchor2, method2 + anchor2, 1)

# Better error diagnostics on remote.
s = s.replace(
    'remoteStatus.setText("Ingen kontakt. Kontrollera samma Wi‑Fi/hotspot och IP-adressen.");',
    'String why = e.getMessage();\n'
    '                    remoteStatus.setText("Ingen kontakt" + (why == null ? "." : ": " + why));',
    1
)

main.write_text(s)

# Service: repair action.
s = svc.read_text()
if "ACTION_REPAIR" not in s:
    s = s.replace(
        'public static final String ACTION_NORMAL = "se.projektorlage.app.NORMAL";',
        'public static final String ACTION_NORMAL = "se.projektorlage.app.NORMAL";\n'
        '    public static final String ACTION_REPAIR = "se.projektorlage.app.REPAIR";',
        1
    )

# Handle repair after foreground start.
needle2 = '''        startForeground(NOTIFICATION_ID, buildNotification());'''
if needle2 in s and "ACTION_REPAIR.equals(action)" not in s:
    s = s.replace(needle2, needle2 + '''

        if (ACTION_REPAIR.equals(action)) {
            acquireConnectivityLocks();
            startHealthWatchdog();
            restartRemoteServer();
            setEnabled(true);
            return START_STICKY;
        }''', 1)

svc.write_text(s)

# Version
b = build.read_text()
b = b.replace("versionCode 12", "versionCode 13", 1)
b = b.replace("versionName '1.2.0'", "versionName '1.3.0'", 1)
build.write_text(b)

print("v1.3 LAN permission/repair patch applied")
