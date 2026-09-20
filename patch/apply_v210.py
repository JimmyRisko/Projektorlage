from pathlib import Path
import sys

root = Path(sys.argv[1])
build = root / "app/build.gradle"

# This build intentionally contains the exact v2.7 runtime architecture.
# Only bump the version so Android accepts it over the broken v2.9 install.
b = build.read_text()
b = b.replace("versionCode 27", "versionCode 30", 1)
b = b.replace("versionName '2.7.0'", "versionName '2.10.0'", 1)
build.write_text(b)

print("v2.10 stable restore version applied")
