from pathlib import Path
import sys

root = Path(sys.argv[1])
client = root / "app/src/main/java/se/projektorlage/app/RemoteClient.java"
build = root / "app/build.gradle"

s = client.read_text()

bad = 'writer.write(pin + "|" + command + "\\\\n");'
good = 'writer.write(pin + "|" + command + "\\n");'

if bad not in s:
    raise SystemExit("Patch misslyckades: klienten hade inte det förväntade newline-felet")

s = s.replace(bad, good, 1)
client.write_text(s)

b = build.read_text()
b = b.replace("versionCode 15", "versionCode 16", 1)
b = b.replace("versionName '1.5.0'", "versionName '1.6.0'", 1)
build.write_text(b)

print("v1.6 newline protocol fix applied")
