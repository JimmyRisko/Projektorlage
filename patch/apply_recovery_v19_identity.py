from pathlib import Path
import sys
root=Path(sys.argv[1])
build=root/"app/build.gradle"
manifest=root/"app/src/main/AndroidManifest.xml"

b=build.read_text()
if 'applicationId "se.projektorlage.app"' in b:
    b=b.replace('applicationId "se.projektorlage.app"',
                'applicationId "se.projektorlage.recovery19"',1)
elif "applicationId 'se.projektorlage.app'" in b:
    b=b.replace("applicationId 'se.projektorlage.app'",
                "applicationId 'se.projektorlage.recovery19'",1)
else:
    raise SystemExit("recovery applicationId not found")
b=b.replace("versionCode 19","versionCode 1",1)
b=b.replace("versionName '1.9.0'","versionName 'RECOVERY-1.9'",1)
build.write_text(b)

m=manifest.read_text()
m=m.replace('android:label="Projektorläge"',
            'android:label="Projektorläge Recovery 1.9"')
manifest.write_text(m)
print("Recovery 1.9 identity applied")
