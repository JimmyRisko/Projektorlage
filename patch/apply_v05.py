from pathlib import Path
import sys

root = Path(sys.argv[1])
svc = root / "app/src/main/java/se/projektorlage/app/RotationService.java"
build = root / "app/build.gradle"

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

s = svc.read_text()

s = replace_once(s,
'''import java.net.ServerSocket;
import java.net.Socket;''',
'''import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;''',
"inet socket import")

s = replace_once(s,
'''    private void startRemoteServer() {
        if (serverRunning) return;
        serverRunning = true;
        serverExecutor = Executors.newCachedThreadPool();
        serverExecutor.execute(() -> {
            try (ServerSocket socket = new ServerSocket(REMOTE_PORT)) {
                serverSocket = socket;
                updateNetworkState(true);
                while (serverRunning) {
                    Socket client = socket.accept();
                    if (!serverRunning) break;
                    serverExecutor.execute(() -> handleClient(client));
                }
            } catch (Exception ignored) {
                if (serverRunning) updateNetworkState(false);
            } finally {
                serverSocket = null;
            }
        });
    }''',
'''    private synchronized void startRemoteServer() {
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
    }''',
"self healing server")

svc.write_text(s)

s = build.read_text()
s = s.replace("versionCode 4", "versionCode 5", 1)
s = s.replace("versionName '0.4.0'", "versionName '0.5.0'", 1)
build.write_text(s)

print("v0.5 patch applied")
