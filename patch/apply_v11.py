from pathlib import Path
import sys

root = Path(sys.argv[1])
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
client = root / "app/src/main/java/se/projektorlage/app/RemoteClient.java"
manifest = root / "app/src/main/AndroidManifest.xml"
build = root / "app/build.gradle"

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

# ---- Manifest: keep CPU/Wi-Fi available while projector mode is active ----
m = manifest.read_text()
anchor = '<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />'
extra = '''<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    <uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />
    <uses-permission android:name="android.permission.WAKE_LOCK" />'''
if 'android.permission.WAKE_LOCK' not in m:
    m = replace_once(m, anchor, extra, "network/wakelock permissions")
manifest.write_text(m)

# ---- RotationService: robust long-running LAN server ----
s = svc.read_text()

s = replace_once(s,
'''import android.media.AudioManager;
import android.os.Build;''',
'''import android.media.AudioManager;
import android.net.ConnectivityManager;
import android.net.LinkProperties;
import android.net.Network;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.PowerManager;''',
"network imports")

s = replace_once(s,
'''    private ServerSocket serverSocket;
    private ExecutorService serverExecutor;
    private volatile boolean serverRunning;
    private String pairingPin;''',
'''    private ServerSocket serverSocket;
    private ExecutorService serverExecutor;
    private volatile boolean serverRunning;
    private volatile int serverGeneration;
    private String pairingPin;

    private final Handler healthHandler = new Handler(Looper.getMainLooper());
    private Runnable healthRunnable;
    private ConnectivityManager connectivityManager;
    private ConnectivityManager.NetworkCallback networkCallback;
    private WifiManager.WifiLock wifiLock;
    private PowerManager.WakeLock wakeLock;''',
"stability fields")

# onCreate initializes connectivity guards.
s = replace_once(s,
'''        createNotificationChannel();
        pairingPin = getOrCreatePin();
    }''',
'''        createNotificationChannel();
        pairingPin = getOrCreatePin();
        setupConnectivityGuards();
    }''',
"onCreate guards")

# Ensure guards every time service starts.
s = replace_once(s,
'''        startForeground(NOTIFICATION_ID, buildNotification());

        if (ACTION_REVERSE.equals(action)) {''',
'''        startForeground(NOTIFICATION_ID, buildNotification());
        acquireConnectivityLocks();
        startHealthWatchdog();

        if (ACTION_REVERSE.equals(action)) {''',
"start guards")

# Replace v0.5 server implementation with generation-safe implementation.
old_server = '''    private synchronized void startRemoteServer() {
        if (serverRunning && serverSocket != null && !serverSocket.isClosed()) return;

        serverRunning = true;
        final ExecutorService executor = Executors.newCachedThreadPool();
        serverExecutor = executor;

        executor.execute(() -> {
            try (ServerSocket socket = new ServerSocket()) {
                socket.setReuseAddress(true);
                socket.bind(new InetSocketAddress(REMOTE_PORT));
                serverSocket = socket;
                updateNetworkState(true);

                while (serverRunning && !socket.isClosed()) {
                    Socket client = socket.accept();
                    if (!serverRunning) {
                        try { client.close(); } catch (Exception ignored) {}
                        break;
                    }
                    executor.execute(() -> handleClient(client));
                }
            } catch (Exception ignored) {
                updateNetworkState(false);
            } finally {
                serverSocket = null;
                serverRunning = false;
                executor.shutdownNow();

                boolean enabled = getSharedPreferences("state", MODE_PRIVATE)
                        .getBoolean("enabled", false);
                if (enabled) {
                    new Handler(Looper.getMainLooper()).postDelayed(() -> {
                        boolean stillEnabled = getSharedPreferences("state", MODE_PRIVATE)
                                .getBoolean("enabled", false);
                        if (stillEnabled) startRemoteServer();
                    }, 1200);
                }
            }
        });
    }'''

new_server = '''    private synchronized void startRemoteServer() {
        if (serverRunning && serverSocket != null && !serverSocket.isClosed()) {
            updateNetworkState(true);
            return;
        }

        final int generation = ++serverGeneration;
        serverRunning = true;

        final ExecutorService executor = Executors.newCachedThreadPool();
        serverExecutor = executor;

        executor.execute(() -> {
            ServerSocket localServer = null;
            try {
                localServer = new ServerSocket();
                localServer.setReuseAddress(true);
                localServer.bind(new InetSocketAddress("0.0.0.0", REMOTE_PORT));

                synchronized (RotationService.this) {
                    if (generation != serverGeneration || !serverRunning) {
                        try { localServer.close(); } catch (Exception ignored) {}
                        return;
                    }
                    serverSocket = localServer;
                }

                updateNetworkState(true);

                while (serverRunning
                        && generation == serverGeneration
                        && !localServer.isClosed()) {
                    Socket client = localServer.accept();
                    client.setTcpNoDelay(true);
                    client.setKeepAlive(true);

                    if (!serverRunning || generation != serverGeneration) {
                        try { client.close(); } catch (Exception ignored) {}
                        break;
                    }

                    executor.execute(() -> handleClient(client));
                }
            } catch (Exception ignored) {
                if (generation == serverGeneration) updateNetworkState(false);
            } finally {
                synchronized (RotationService.this) {
                    if (generation == serverGeneration) {
                        if (serverSocket == localServer) serverSocket = null;
                        serverRunning = false;
                    }
                }
                try {
                    if (localServer != null && !localServer.isClosed()) localServer.close();
                } catch (Exception ignored) {}
                executor.shutdownNow();
            }
        });
    }

    private synchronized void repairRemoteServer() {
        boolean enabled = getSharedPreferences("state", MODE_PRIVATE)
                .getBoolean("enabled", false);
        if (!enabled) return;

        String currentIp = NetworkUtils.getLocalIpv4();
        String savedIp = getSharedPreferences("state", MODE_PRIVATE)
                .getString("server_ip", null);

        if (serverRunning && serverSocket != null && !serverSocket.isClosed()) {
            if (currentIp != null && !currentIp.equals(savedIp)) {
                updateNetworkState(true);
            }
            return;
        }

        startRemoteServer();
    }

    private synchronized void restartRemoteServer() {
        boolean enabled = getSharedPreferences("state", MODE_PRIVATE)
                .getBoolean("enabled", false);
        if (!enabled) return;

        serverGeneration++;
        serverRunning = false;

        try {
            if (serverSocket != null) serverSocket.close();
        } catch (Exception ignored) {}

        serverSocket = null;

        ExecutorService oldExecutor = serverExecutor;
        serverExecutor = null;
        if (oldExecutor != null) oldExecutor.shutdownNow();

        updateNetworkState(false);

        healthHandler.postDelayed(() -> {
            boolean stillEnabled = getSharedPreferences("state", MODE_PRIVATE)
                    .getBoolean("enabled", false);
            if (stillEnabled) startRemoteServer();
        }, 300);
    }'''

s = replace_once(s, old_server, new_server, "robust server")

# Insert connectivity guards before handleClient.
s = replace_once(s,
'''    private void handleClient(Socket client) {''',
'''    private void setupConnectivityGuards() {
        connectivityManager = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);

        if (connectivityManager != null && networkCallback == null) {
            networkCallback = new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network network) {
                    healthHandler.postDelayed(RotationService.this::repairRemoteServer, 250);
                }

                @Override
                public void onLost(Network network) {
                    healthHandler.postDelayed(RotationService.this::repairRemoteServer, 500);
                }

                @Override
                public void onLinkPropertiesChanged(Network network, LinkProperties linkProperties) {
                    healthHandler.postDelayed(RotationService.this::repairRemoteServer, 250);
                }
            };

            try {
                connectivityManager.registerDefaultNetworkCallback(networkCallback);
            } catch (Exception ignored) {
                networkCallback = null;
            }
        }

        if (healthRunnable == null) {
            healthRunnable = new Runnable() {
                @Override
                public void run() {
                    boolean enabled = getSharedPreferences("state", MODE_PRIVATE)
                            .getBoolean("enabled", false);

                    if (enabled) {
                        repairRemoteServer();
                        healthHandler.postDelayed(this, 1500);
                    }
                }
            };
        }
    }

    private void acquireConnectivityLocks() {
        try {
            WifiManager wifi = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
            if (wifi != null && (wifiLock == null || !wifiLock.isHeld())) {
                wifiLock = wifi.createWifiLock(
                        WifiManager.WIFI_MODE_FULL_HIGH_PERF,
                        "Projektorlage::RemoteWifi");
                wifiLock.setReferenceCounted(false);
                wifiLock.acquire();
            }
        } catch (Exception ignored) {
        }

        try {
            PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
            if (power != null && (wakeLock == null || !wakeLock.isHeld())) {
                wakeLock = power.newWakeLock(
                        PowerManager.PARTIAL_WAKE_LOCK,
                        "Projektorlage::RemoteCpu");
                wakeLock.setReferenceCounted(false);
                wakeLock.acquire();
            }
        } catch (Exception ignored) {
        }
    }

    private void releaseConnectivityLocks() {
        try {
            if (wifiLock != null && wifiLock.isHeld()) wifiLock.release();
        } catch (Exception ignored) {}
        wifiLock = null;

        try {
            if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        } catch (Exception ignored) {}
        wakeLock = null;
    }

    private void startHealthWatchdog() {
        if (healthRunnable == null) setupConnectivityGuards();
        healthHandler.removeCallbacks(healthRunnable);
        healthHandler.postDelayed(healthRunnable, 500);
    }

    private void stopHealthWatchdog() {
        if (healthRunnable != null) healthHandler.removeCallbacks(healthRunnable);
    }

    private void unregisterNetworkCallback() {
        if (connectivityManager != null && networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback);
            } catch (Exception ignored) {}
        }
        networkCallback = null;
    }

    private void handleClient(Socket client) {''',
"connectivity guards")

# Mark successful requests when the exact source fragment is available.
needle = '''            String response = executeCommand(parts[1]);'''
if needle in s:
    s = s.replace(needle, '''            getSharedPreferences("state", MODE_PRIVATE).edit()
                    .putLong("last_remote_contact_ms", System.currentTimeMillis())
                    .apply();

            String response = executeCommand(parts[1]);''', 1)

# Harden stopRemoteServer so old generations cannot interfere with new ones.
old_stop = '''    private void stopRemoteServer() {
        serverRunning = false;
        try {
            if (serverSocket != null) serverSocket.close();
        } catch (Exception ignored) {
        }
        serverSocket = null;
        if (serverExecutor != null) serverExecutor.shutdownNow();
        serverExecutor = null;
        updateNetworkState(false);
    }'''

new_stop = '''    private synchronized void stopRemoteServer() {
        serverGeneration++;
        serverRunning = false;

        try {
            if (serverSocket != null) serverSocket.close();
        } catch (Exception ignored) {
        }
        serverSocket = null;

        ExecutorService executor = serverExecutor;
        serverExecutor = null;
        if (executor != null) executor.shutdownNow();

        updateNetworkState(false);
    }'''

s = replace_once(s, old_stop, new_stop, "safe server stop")

# Shutdown releases locks and watchdog.
s = replace_once(s,
'''    private void shutdownEverything() {
        stopRemoteServer();''',
'''    private void shutdownEverything() {
        stopHealthWatchdog();
        stopRemoteServer();
        releaseConnectivityLocks();''',
"shutdown locks")

# onDestroy cleanup.
s = replace_once(s,
'''    public void onDestroy() {
        stopRemoteServer();''',
'''    public void onDestroy() {
        stopHealthWatchdog();
        stopRemoteServer();
        releaseConnectivityLocks();
        unregisterNetworkCallback();''',
"destroy locks")

svc.write_text(s)

# ---- Client: automatic retries for transient server/network hiccups ----
client.write_text(r'''package se.projektorlage.app;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public final class RemoteClient {
    private RemoteClient() {}

    public static String send(String host, int port, String pin, String command) throws Exception {
        Exception lastError = null;
        final int[] delays = new int[]{0, 250, 500, 900};

        for (int attempt = 0; attempt < delays.length; attempt++) {
            if (delays[attempt] > 0) {
                try {
                    Thread.sleep(delays[attempt]);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }
            }

            try (Socket socket = new Socket()) {
                socket.setTcpNoDelay(true);
                socket.setKeepAlive(true);
                socket.connect(new InetSocketAddress(host, port), 1600);
                socket.setSoTimeout(2200);

                BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(
                        socket.getOutputStream(), StandardCharsets.UTF_8));
                BufferedReader reader = new BufferedReader(new InputStreamReader(
                        socket.getInputStream(), StandardCharsets.UTF_8));

                writer.write(pin + "|" + command + "\\n");
                writer.flush();

                String response = reader.readLine();
                if (response == null) {
                    throw new IllegalStateException("Ingen respons från projektormobilen");
                }
                return response;
            } catch (Exception e) {
                lastError = e;
            }
        }

        throw lastError != null
                ? lastError
                : new IllegalStateException("Ingen kontakt med projektormobilen");
    }
}
''')

# Version
b = build.read_text()
b = b.replace("versionCode 10", "versionCode 11", 1)
b = b.replace("versionName '1.0.0'", "versionName '1.1.0'", 1)
build.write_text(b)

print("v1.1 stability patch applied")
