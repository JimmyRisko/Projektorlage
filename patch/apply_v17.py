from pathlib import Path
import re, sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
disc = root / "app/src/main/java/se/projektorlage/app/ProjectorDiscovery.java"
build = root / "app/build.gradle"

# ---------- UDP discovery helper ----------
disc.write_text(r'''package se.projektorlage.app;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ProjectorDiscovery {
    public static final int DISCOVERY_PORT = 8766;
    private static final String DISCOVER = "PROJEKTORLAGE_DISCOVER_V1";
    private static final String HERE = "PROJEKTORLAGE_HERE_V1";

    private ProjectorDiscovery() {}

    public static final class Result {
        public final String host;
        public final String pin;
        public final int port;

        public Result(String host, String pin, int port) {
            this.host = host;
            this.pin = pin;
            this.port = port;
        }
    }

    public static Result discover(int timeoutMs) {
        DatagramSocket socket = null;
        try {
            socket = new DatagramSocket();
            socket.setBroadcast(true);
            socket.setSoTimeout(350);

            byte[] data = DISCOVER.getBytes(StandardCharsets.UTF_8);
            for (InetAddress target : broadcastTargets()) {
                try {
                    socket.send(new DatagramPacket(data, data.length, target, DISCOVERY_PORT));
                } catch (Exception ignored) {}
            }

            long deadline = System.currentTimeMillis() + Math.max(500, timeoutMs);
            byte[] buffer = new byte[512];

            while (System.currentTimeMillis() < deadline) {
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                try {
                    socket.receive(packet);
                } catch (SocketTimeoutException timeout) {
                    // Re-broadcast so discovery also works when the projector starts a moment later.
                    for (InetAddress target : broadcastTargets()) {
                        try {
                            socket.send(new DatagramPacket(data, data.length, target, DISCOVERY_PORT));
                        } catch (Exception ignored) {}
                    }
                    continue;
                }

                String response = new String(
                        packet.getData(), packet.getOffset(), packet.getLength(),
                        StandardCharsets.UTF_8).trim();

                String[] parts = response.split("\\|");
                if (parts.length >= 4 && HERE.equals(parts[0])) {
                    String host = parts[1].trim();
                    String pin = parts[2].trim();
                    int port = Integer.parseInt(parts[3].trim());

                    if (host.isEmpty()) host = packet.getAddress().getHostAddress();
                    if (pin.matches("\\d{6}")) {
                        return new Result(host, pin, port);
                    }
                }
            }
        } catch (Exception ignored) {
        } finally {
            if (socket != null) socket.close();
        }
        return null;
    }

    private static List<InetAddress> broadcastTargets() {
        List<InetAddress> targets = new ArrayList<>();
        try {
            targets.add(InetAddress.getByName("255.255.255.255"));
        } catch (Exception ignored) {}

        try {
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces != null && interfaces.hasMoreElements()) {
                NetworkInterface nif = interfaces.nextElement();
                if (!nif.isUp() || nif.isLoopback()) continue;

                for (InterfaceAddress ia : nif.getInterfaceAddresses()) {
                    InetAddress broadcast = ia.getBroadcast();
                    if (broadcast != null && !targets.contains(broadcast)) {
                        targets.add(broadcast);
                    }
                }
            }
        } catch (Exception ignored) {}
        return targets;
    }

    public static final class Responder {
        private final String pin;
        private final int remotePort;
        private final AtomicBoolean running = new AtomicBoolean(false);
        private DatagramSocket socket;
        private Thread thread;

        public Responder(String pin, int remotePort) {
            this.pin = pin;
            this.remotePort = remotePort;
        }

        public synchronized void start() {
            if (running.get()) return;
            running.set(true);

            thread = new Thread(() -> {
                try {
                    socket = new DatagramSocket(DISCOVERY_PORT);
                    socket.setBroadcast(true);

                    byte[] buffer = new byte[512];
                    while (running.get()) {
                        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                        socket.receive(packet);

                        String request = new String(
                                packet.getData(), packet.getOffset(), packet.getLength(),
                                StandardCharsets.UTF_8).trim();

                        if (!DISCOVER.equals(request)) continue;

                        String ip = NetworkUtils.getLocalIpv4();
                        if (ip == null || ip.trim().isEmpty()) {
                            ip = packet.getAddress().getHostAddress();
                        }

                        String response = HERE + "|" + ip + "|" + pin + "|" + remotePort;
                        byte[] out = response.getBytes(StandardCharsets.UTF_8);
                        DatagramPacket reply = new DatagramPacket(
                                out, out.length, packet.getAddress(), packet.getPort());
                        socket.send(reply);
                    }
                } catch (Exception ignored) {
                } finally {
                    running.set(false);
                    if (socket != null) socket.close();
                    socket = null;
                }
            }, "ProjektorlageDiscovery");
            thread.setDaemon(true);
            thread.start();
        }

        public synchronized void stop() {
            running.set(false);
            if (socket != null) {
                try { socket.close(); } catch (Exception ignored) {}
            }
            socket = null;
            thread = null;
        }
    }
}
''')

# ---------- RotationService: discovery responder follows remote server lifecycle ----------
s = svc.read_text()

if "private ProjectorDiscovery.Responder discoveryResponder;" not in s:
    anchor = '''    private PowerManager.WakeLock wakeLock;'''
    if anchor not in s:
        raise SystemExit("Patch misslyckades: responder field anchor")
    s = s.replace(anchor, anchor + '''
    private ProjectorDiscovery.Responder discoveryResponder;''', 1)

anchor = '''    private synchronized void startRemoteServer() {'''
if anchor not in s:
    raise SystemExit("Patch misslyckades: startRemoteServer anchor")

helpers = '''    private synchronized void startDiscoveryResponder() {
        if (discoveryResponder == null) {
            discoveryResponder = new ProjectorDiscovery.Responder(pairingPin, REMOTE_PORT);
        }
        discoveryResponder.start();
    }

    private synchronized void stopDiscoveryResponder() {
        if (discoveryResponder != null) {
            discoveryResponder.stop();
            discoveryResponder = null;
        }
    }

'''
if "private synchronized void startDiscoveryResponder()" not in s:
    s = s.replace(anchor, helpers + anchor, 1)

# Every server start makes the projector discoverable.
s = s.replace(
'''    private synchronized void startRemoteServer() {
        if (serverRunning''',
'''    private synchronized void startRemoteServer() {
        startDiscoveryResponder();
        if (serverRunning''',
1)

# A full server stop also removes discovery.
s = s.replace(
'''    private synchronized void stopRemoteServer() {
        serverGeneration++;''',
'''    private synchronized void stopRemoteServer() {
        stopDiscoveryResponder();
        serverGeneration++;''',
1)

svc.write_text(s)

# ---------- MainActivity: automatic discover/pair/reconnect ----------
s = main.read_text()

# Replace showRemotePanel so it always auto-connects, even when IP has changed.
pat = re.compile(r'''    private void showRemotePanel\(\) \{.*?\n    \}\n\n    private void showRoleChooser\(\)''', re.S)
m = pat.search(s)
if not m:
    raise SystemExit("Patch misslyckades: showRemotePanel")

new_remote = '''    private void showRemotePanel() {
        getSharedPreferences("ui", MODE_PRIVATE).edit().putString("role", "remote").apply();
        roleChooser.setVisibility(View.GONE);
        projectorPanel.setVisibility(View.GONE);
        remotePanel.setVisibility(View.VISIBLE);

        SharedPreferences prefs = getSharedPreferences("remote", MODE_PRIVATE);
        String ip = prefs.getString("ip", "");
        String pin = prefs.getString("pin", "");
        if (ipInput != null) ipInput.setText(ip);
        if (pinInput != null) pinInput.setText(pin);

        remoteStatus.setText("Söker efter projektorn…");
        uiHandler.postDelayed(this::autoConnectRemote, 250);
    }

    private void showRoleChooser()'''
s = s[:m.start()] + new_remote + s[m.end():]

# Add autoConnect method before showRoleChooser.
anchor = '''    private void showRoleChooser() {'''
if anchor not in s:
    raise SystemExit("Patch misslyckades: role chooser anchor")

auto_method = '''    private void autoConnectRemote() {
        new Thread(() -> {
            SharedPreferences prefs = getSharedPreferences("remote", MODE_PRIVATE);

            String ip = ipInput != null ? ipInput.getText().toString().trim() : "";
            String pin = pinInput != null ? pinInput.getText().toString().trim() : "";

            if (ip.isEmpty()) ip = prefs.getString("ip", "");
            if (!pin.matches("\\d{6}")) pin = prefs.getString("pin", "");

            // First try the last known projector. This makes normal startup almost instant.
            if (!ip.isEmpty() && pin.matches("\\d{6}")) {
                try {
                    String response = RemoteClient.send(ip, 8765, pin, "PING");
                    if (response != null && response.startsWith("OK|")) {
                        final String okIp = ip;
                        final String okPin = pin;
                        prefs.edit().putString("ip", okIp).putString("pin", okPin).apply();
                        runOnUiThread(() -> {
                            if (ipInput != null) ipInput.setText(okIp);
                            if (pinInput != null) pinInput.setText(okPin);
                            remoteStatus.setText("Projektor ansluten ✓");
                            remoteStatus.setTextColor(Color.rgb(110, 220, 140));
                        });
                        return;
                    }
                } catch (Exception ignored) {
                }
            }

            runOnUiThread(() -> {
                remoteStatus.setText("Hittar projektorn automatiskt…");
                remoteStatus.setTextColor(muted());
            });

            ProjectorDiscovery.Result found = ProjectorDiscovery.discover(4500);
            if (found == null) {
                runOnUiThread(() -> {
                    remoteStatus.setText("Ingen projektor hittades. Starta projektorn och kontrollera att båda är på samma Wi‑Fi.");
                    remoteStatus.setTextColor(Color.rgb(255, 125, 125));
                });
                return;
            }

            prefs.edit()
                    .putString("ip", found.host)
                    .putString("pin", found.pin)
                    .apply();

            try {
                String response = RemoteClient.send(found.host, found.port, found.pin, "PING");
                runOnUiThread(() -> {
                    if (ipInput != null) ipInput.setText(found.host);
                    if (pinInput != null) pinInput.setText(found.pin);

                    if (response != null && response.startsWith("OK|")) {
                        remoteStatus.setText("Projektor hittad och ansluten ✓");
                        remoteStatus.setTextColor(Color.rgb(110, 220, 140));
                    } else {
                        remoteStatus.setText("Projektorn hittades men svarade inte korrekt.");
                        remoteStatus.setTextColor(Color.rgb(255, 180, 110));
                    }
                });
            } catch (Exception e) {
                final String why = e.getMessage();
                runOnUiThread(() -> {
                    remoteStatus.setText("Projektorn hittades men anslutningen misslyckades"
                            + (why == null ? "." : ": " + why));
                    remoteStatus.setTextColor(Color.rgb(255, 125, 125));
                });
            }
        }, "ProjektorlageAutoConnect").start();
    }

'''
if "private void autoConnectRemote()" not in s:
    s = s.replace(anchor, auto_method + anchor, 1)

# Manual advanced pairing button becomes a simple rediscovery/reconnect button.
s = s.replace(
'''        Button connect = makeButton("PARKOPPLA / TESTA");
        connect.setOnClickListener(v -> sendRemote("PING"));''',
'''        Button connect = makeButton("HITTA / ÅTERANSLUT PROJEKTOR");
        connect.setOnClickListener(v -> autoConnectRemote());''',
1)

main.write_text(s)

# ---------- Version ----------
b = build.read_text()
b = b.replace("versionCode 16", "versionCode 17", 1)
b = b.replace("versionName '1.6.0'", "versionName '1.7.0'", 1)
build.write_text(b)

print("v1.7 automatic discovery patch applied")
