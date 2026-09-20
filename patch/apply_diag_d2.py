from pathlib import Path
import sys

root=Path(sys.argv[1])
build=root/"app/build.gradle"
main=root/"app/src/main/java/se/projektorlage/app/MainActivity.java"
manifest=root/"app/src/main/AndroidManifest.xml"

b=build.read_text()
# Unique identity so this diagnostic build never collides with any previous debug-signed APK.
for old in [
    'applicationId "se.projektorlage.diagnostic"',
    "applicationId 'se.projektorlage.diagnostic'"
]:
    if old in b:
        q='"' if '"' in old else "'"
        b=b.replace(old, f'applicationId {q}se.projektorlage.diagnostic2{q}',1)
        break
else:
    raise SystemExit("diagnostic applicationId not found")

b=b.replace("versionCode 2","versionCode 1",1)
b=b.replace("versionName '1.0.1-diag'","versionName 'D2-1.0'",1)
build.write_text(b)

m=manifest.read_text()
m=m.replace('android:label="Projektorläge Diagnostik"',
            'android:label="Projektorläge Diagnostik D2"')
manifest.write_text(m)

s=main.read_text()
# Add unmistakable build/version text under the main title/introduction.
needle='''        TextView intro = text(
                "Starta projektorn med ett tryck. Tekniska inställningar finns bara under Avancerat.",
                15, muted(), false);
        intro.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(intro, full(0, dp(18)));'''
repl='''        TextView intro = text(
                "Starta projektorn med ett tryck. Tekniska inställningar finns bara under Avancerat.",
                15, muted(), false);
        intro.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(intro, full(0, dp(8)));

        TextView diagnosticBuild = text(
                "DIAGNOSTIK D2 • loggning aktiv",
                14, Color.rgb(255, 184, 77), true);
        diagnosticBuild.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(diagnosticBuild, full(0, dp(18)));'''
if needle not in s:
    raise SystemExit("D2 version label insertion point not found")
s=s.replace(needle,repl,1)

# Make sure visible export button is present and loud.
if 'KOPIERA DIAGNOSTIK' not in s:
    raise SystemExit("D2 export button missing before build")
s=s.replace('makeButton("KOPIERA DIAGNOSTIK")',
            'makeButton("KOPIERA DIAGNOSTIK / LOGG")',1)

main.write_text(s)
print("diagnostic D2 unique build identity applied")
