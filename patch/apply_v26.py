from pathlib import Path
import sys

root=Path(sys.argv[1])
build=root/"app/build.gradle"
b=build.read_text()
b=b.replace("versionCode 25","versionCode 26",1)
b=b.replace("versionName '2.5.0'","versionName '2.6.0'",1)
build.write_text(b)
print("v2.6 release candidate version applied")
