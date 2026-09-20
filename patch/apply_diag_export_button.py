from pathlib import Path
import sys

root=Path(sys.argv[1])
main=root/"app/src/main/java/se/projektorlage/app/MainActivity.java"
build=root/"app/build.gradle"

m=main.read_text()

# Insert a visible export button directly after the STOP button in the projector panel.
needle='''        Button stop = makeButton("STOPPA PROJEKTOR");
        stop.setOnClickListener(v -> disableProjectorMode());
        panel.addView(stop, full(0, dp(16)));

        Button advancedToggle = makeButton("Avancerat");'''
repl='''        Button stop = makeButton("STOPPA PROJEKTOR");
        stop.setOnClickListener(v -> disableProjectorMode());
        panel.addView(stop, full(0, dp(12)));

        Button copyDiagnostics = makeButton("KOPIERA DIAGNOSTIK");
        copyDiagnostics.setOnClickListener(v -> copyDiagnosticReport());
        panel.addView(copyDiagnostics, full(0, dp(16)));

        Button advancedToggle = makeButton("Avancerat");'''
if needle not in m:
    raise SystemExit("export button insertion point not found")
m=m.replace(needle,repl,1)
main.write_text(m)

b=build.read_text()
b=b.replace("versionCode 1","versionCode 2",1)
b=b.replace("versionName '1.0.0-diag'","versionName '1.0.1-diag'",1)
build.write_text(b)

print("visible diagnostic export button applied")
