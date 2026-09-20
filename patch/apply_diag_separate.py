from pathlib import Path
import sys

root=Path(sys.argv[1])
build=root/"app/build.gradle"
manifest=root/"app/src/main/AndroidManifest.xml"

b=build.read_text()
# Separate install identity. Keep all runtime code identical to diagnostic v2.13.
if 'applicationId "se.projektorlage.app"' in b:
    b=b.replace('applicationId "se.projektorlage.app"',
                'applicationId "se.projektorlage.diagnostic"',1)
elif "applicationId 'se.projektorlage.app'" in b:
    b=b.replace("applicationId 'se.projektorlage.app'",
                "applicationId 'se.projektorlage.diagnostic'",1)
else:
    raise SystemExit("diag separate: applicationId not found")

b=b.replace("versionCode 33","versionCode 1",1)
b=b.replace("versionName '2.13.0-diag'","versionName '1.0.0-diag'",1)
build.write_text(b)

m=manifest.read_text()
# Give the side-by-side diagnostic build a distinct launcher label where present.
m=m.replace('android:label="Projektorläge"', 'android:label="Projektorläge Diagnostik"')
manifest.write_text(m)

print("separate diagnostic applicationId applied")
