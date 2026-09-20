from pathlib import Path
import re, sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
build = root / "app/build.gradle"

s = main.read_text()

# Add UI state fields.
if "private LinearLayout roleChooser;" not in s:
    s = s.replace(
        "    private LinearLayout projectorPanel;\n    private LinearLayout remotePanel;",
        "    private LinearLayout projectorPanel;\n    private LinearLayout remotePanel;\n"
        "    private LinearLayout roleChooser;\n"
        "    private LinearLayout projectorAdvanced;\n"
        "    private LinearLayout remoteAdvanced;",
        1
    )

# Replace onCreate so the selected role is remembered.
pat = re.compile(r'''    @Override\n    protected void onCreate\(Bundle savedInstanceState\) \{.*?\n    \}\n\n    @Override\n    protected void onResume''', re.S)
m = pat.search(s)
if not m:
    raise SystemExit("Patch misslyckades: onCreate")

new_oncreate = '''    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
        askNotificationPermissionIfNeeded();
        askNearbyWifiPermissionIfNeeded();

        String savedRole = getSharedPreferences("ui", MODE_PRIVATE)
                .getString("role", "");
        if ("projector".equals(savedRole)) {
            showProjectorPanel();
        } else if ("remote".equals(savedRole)) {
            showRemotePanel();
        } else {
            showRoleChooser();
        }
    }

    @Override
    protected void onResume'''
s = s[:m.start()] + new_oncreate + s[m.end():]

# Replace buildUi.
pat = re.compile(r'''    private View buildUi\(\) \{.*?\n    \}\n\n    private LinearLayout buildProjectorPanel\(\)''', re.S)
m = pat.search(s)
if not m:
    raise SystemExit("Patch misslyckades: buildUi")

new_buildui = '''    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(34), dp(20), dp(30));
        root.setBackgroundColor(Color.rgb(16, 18, 20));
        scroll.addView(root);

        TextView title = text("Projektorläge", 30, Color.WHITE, true);
        title.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(title, full(0, dp(8)));

        TextView intro = text(
                "Starta projektorn med ett tryck. Tekniska inställningar finns bara under Avancerat.",
                15, muted(), false);
        intro.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(intro, full(0, dp(18)));

        roleChooser = new LinearLayout(this);
        roleChooser.setOrientation(LinearLayout.VERTICAL);

        TextView choose = text("Hur ska den här mobilen användas?", 18, Color.WHITE, true);
        choose.setGravity(Gravity.CENTER_HORIZONTAL);
        roleChooser.addView(choose, full(0, dp(12)));

        Button projectorRole = makeButton("PROJEKTOR");
        Button remoteRole = makeButton("FJÄRRKONTROLL");
        projectorRole.setOnClickListener(v -> {
            getSharedPreferences("ui", MODE_PRIVATE).edit().putString("role", "projector").apply();
            showProjectorPanel();
        });
        remoteRole.setOnClickListener(v -> {
            getSharedPreferences("ui", MODE_PRIVATE).edit().putString("role", "remote").apply();
            showRemotePanel();
        });
        roleChooser.addView(projectorRole, full(0, dp(10)));
        roleChooser.addView(remoteRole, full(0, dp(18)));
        root.addView(roleChooser, full(0, 0));

        projectorPanel = buildProjectorPanel();
        remotePanel = buildRemotePanel();
        root.addView(projectorPanel, full(0, 0));
        root.addView(remotePanel, full(0, 0));

        return scroll;
    }

    private LinearLayout buildProjectorPanel()'''
s = s[:m.start()] + new_buildui + s[m.end():]

# Replace projector panel completely.
pat = re.compile(r'''    private LinearLayout buildProjectorPanel\(\) \{.*?\n    \}\n\n    private LinearLayout buildRemotePanel\(\)''', re.S)
m = pat.search(s)
if not m:
    raise SystemExit("Patch misslyckades: projector panel")

new_projector = '''    private LinearLayout buildProjectorPanel() {
        LinearLayout panel = panel();

        panel.addView(sectionTitle("Projektor"), full(0, dp(8)));
        panel.addView(text(
                "Tryck Starta. Appen ställer in bildriktning och ljus, startar fjärren och öppnar Netflix automatiskt.",
                14, muted(), false), full(0, dp(14)));

        projectorStatus = text("", 17, Color.WHITE, true);
        panel.addView(projectorStatus, full(0, dp(14)));

        Button enable = makeButton("STARTA PROJEKTOR");
        enable.setTextSize(18);
        enable.setMinHeight(dp(66));
        enable.setOnClickListener(v -> startProjectorAutomatic());
        panel.addView(enable, full(0, dp(12)));

        Button stop = makeButton("STOPPA PROJEKTOR");
        stop.setOnClickListener(v -> disableProjectorMode());
        panel.addView(stop, full(0, dp(16)));

        Button advancedToggle = makeButton("Avancerat");
        panel.addView(advancedToggle, full(0, dp(8)));

        projectorAdvanced = new LinearLayout(this);
        projectorAdvanced.setOrientation(LinearLayout.VERTICAL);
        projectorAdvanced.setVisibility(View.GONE);

        pairInfo = text("", 14, muted(), false);
        pairInfo.setTextIsSelectable(true);
        projectorAdvanced.addView(pairInfo, full(0, dp(12)));

        Button repair = makeButton("REPARERA FJÄRR");
        repair.setOnClickListener(v -> repairRemoteServer());
        projectorAdvanced.addView(repair, full(0, dp(10)));

        projectorAdvanced.addView(text("Bildriktning", 14, muted(), true), full(dp(4), dp(6)));
        LinearLayout rotationRow = new LinearLayout(this);
        rotationRow.setOrientation(LinearLayout.HORIZONTAL);
        rotationRow.setWeightSum(2f);
        Button reverse = makeButton("LANDSKAP ↺");
        Button normal = makeButton("LANDSKAP ↻");
        reverse.setOnClickListener(v -> setLocalRotation(true));
        normal.setOnClickListener(v -> setLocalRotation(false));
        rotationRow.addView(reverse, weighted(dp(5)));
        rotationRow.addView(normal, weighted(0));
        projectorAdvanced.addView(rotationRow, full(0, dp(10)));

        Button netflix = makeButton("ÖPPNA NETFLIX");
        netflix.setOnClickListener(v -> openNetflix());
        projectorAdvanced.addView(netflix, full(0, dp(10)));

        Button mirror = makeButton("SPEGELVÄND VALD APP");
        mirror.setOnClickListener(v -> startActivity(new Intent(this, MirrorPermissionActivity.class)));
        projectorAdvanced.addView(mirror, full(0, dp(10)));

        Button localVideo = makeButton("LOKAL VIDEO – SPEGEL / 180°");
        localVideo.setOnClickListener(v -> startActivity(new Intent(this, VideoPlayerActivity.class)));
        projectorAdvanced.addView(localVideo, full(0, dp(10)));

        Button permissions = makeButton("ROTATION + LJUSSTYRKA");
        permissions.setOnClickListener(v -> requestWriteSettings());
        projectorAdvanced.addView(permissions, full(0, dp(10)));

        panel.addView(projectorAdvanced, full(0, dp(12)));

        advancedToggle.setOnClickListener(v -> {
            boolean open = projectorAdvanced.getVisibility() == View.VISIBLE;
            projectorAdvanced.setVisibility(open ? View.GONE : View.VISIBLE);
            advancedToggle.setText(open ? "Avancerat" : "Dölj avancerat");
        });

        Button changeRole = makeButton("Byt roll på den här mobilen");
        changeRole.setOnClickListener(v -> showRoleChooser());
        panel.addView(changeRole, full(dp(6), 0));

        return panel;
    }

    private LinearLayout buildRemotePanel()'''
s = s[:m.start()] + new_projector + s[m.end():]

# Replace remote panel completely.
pat = re.compile(r'''    private LinearLayout buildRemotePanel\(\) \{.*?\n    \}\n\n    private void showProjectorPanel\(\)''', re.S)
m = pat.search(s)
if not m:
    raise SystemExit("Patch misslyckades: remote panel")

new_remote = '''    private LinearLayout buildRemotePanel() {
        LinearLayout panel = panel();

        panel.addView(sectionTitle("Fjärrkontroll"), full(0, dp(8)));
        panel.addView(text(
                "Appen använder den senast parkopplade projektorn automatiskt.",
                14, muted(), false), full(0, dp(12)));

        remoteStatus = text("Ansluter…", 15, muted(), false);
        panel.addView(remoteStatus, full(0, dp(14)));

        Button netflix = makeButton("ÖPPNA NETFLIX");
        netflix.setOnClickListener(v -> sendRemote("NETFLIX"));
        panel.addView(netflix, full(0, dp(10)));

        Button playPause = makeButton("SPELA / PAUSA");
        playPause.setTextSize(17);
        playPause.setMinHeight(dp(62));
        playPause.setOnClickListener(v -> sendRemote("PLAY_PAUSE"));
        panel.addView(playPause, full(0, dp(10)));

        LinearLayout seekRow = new LinearLayout(this);
        seekRow.setOrientation(LinearLayout.HORIZONTAL);
        seekRow.setWeightSum(2f);
        Button rewind = makeButton("BAKÅT");
        Button forward = makeButton("FRAMÅT");
        rewind.setOnClickListener(v -> sendRemote("REWIND"));
        forward.setOnClickListener(v -> sendRemote("FAST_FORWARD"));
        seekRow.addView(rewind, weighted(dp(5)));
        seekRow.addView(forward, weighted(0));
        panel.addView(seekRow, full(0, dp(10)));

        LinearLayout volumeRow = new LinearLayout(this);
        volumeRow.setOrientation(LinearLayout.HORIZONTAL);
        volumeRow.setWeightSum(3f);
        Button volDown = makeButton("VOL −");
        Button mute = makeButton("MUTE");
        Button volUp = makeButton("VOL +");
        volDown.setOnClickListener(v -> sendRemote("VOL_DOWN"));
        mute.setOnClickListener(v -> sendRemote("MUTE"));
        volUp.setOnClickListener(v -> sendRemote("VOL_UP"));
        volumeRow.addView(volDown, weighted(dp(4)));
        volumeRow.addView(mute, weighted(dp(4)));
        volumeRow.addView(volUp, weighted(0));
        panel.addView(volumeRow, full(0, dp(10)));

        LinearLayout lightRow = new LinearLayout(this);
        lightRow.setOrientation(LinearLayout.HORIZONTAL);
        lightRow.setWeightSum(3f);
        Button lightDown = makeButton("LJUS −");
        Button lightMax = makeButton("MAX");
        Button lightUp = makeButton("LJUS +");
        lightDown.setOnClickListener(v -> sendRemote("BRIGHTNESS_DOWN"));
        lightMax.setOnClickListener(v -> sendRemote("BRIGHTNESS_MAX"));
        lightUp.setOnClickListener(v -> sendRemote("BRIGHTNESS_UP"));
        lightRow.addView(lightDown, weighted(dp(4)));
        lightRow.addView(lightMax, weighted(dp(4)));
        lightRow.addView(lightUp, weighted(0));
        panel.addView(lightRow, full(0, dp(12)));

        Button stop = makeButton("STOPPA PROJEKTORN");
        stop.setOnClickListener(v -> sendRemote("STOP"));
        panel.addView(stop, full(0, dp(16)));

        Button advancedToggle = makeButton("Avancerat");
        panel.addView(advancedToggle, full(0, dp(8)));

        remoteAdvanced = new LinearLayout(this);
        remoteAdvanced.setOrientation(LinearLayout.VERTICAL);
        remoteAdvanced.setVisibility(View.GONE);

        ipInput = new EditText(this);
        ipInput.setHint("Projektorns IP-adress");
        ipInput.setTextColor(Color.WHITE);
        ipInput.setHintTextColor(Color.rgb(125, 133, 140));
        ipInput.setTextSize(17);
        ipInput.setSingleLine(true);
        ipInput.setInputType(InputType.TYPE_CLASS_PHONE);
        remoteAdvanced.addView(ipInput, full(0, dp(10)));

        pinInput = new EditText(this);
        pinInput.setHint("6-siffrig PIN");
        pinInput.setTextColor(Color.WHITE);
        pinInput.setHintTextColor(Color.rgb(125, 133, 140));
        pinInput.setTextSize(17);
        pinInput.setSingleLine(true);
        pinInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        remoteAdvanced.addView(pinInput, full(0, dp(10)));

        SharedPreferences prefs = getSharedPreferences("remote", MODE_PRIVATE);
        ipInput.setText(prefs.getString("ip", ""));
        pinInput.setText(prefs.getString("pin", ""));

        Button connect = makeButton("PARKOPPLA / TESTA");
        connect.setOnClickListener(v -> sendRemote("PING"));
        remoteAdvanced.addView(connect, full(0, dp(10)));

        remoteAdvanced.addView(text("Bildriktning", 14, muted(), true), full(dp(6), dp(6)));
        LinearLayout rotationRow = new LinearLayout(this);
        rotationRow.setOrientation(LinearLayout.HORIZONTAL);
        rotationRow.setWeightSum(2f);
        Button reverse = makeButton("LANDSKAP ↺");
        Button normal = makeButton("LANDSKAP ↻");
        reverse.setOnClickListener(v -> sendRemote("ROTATE_REVERSE"));
        normal.setOnClickListener(v -> sendRemote("ROTATE_NORMAL"));
        rotationRow.addView(reverse, weighted(dp(5)));
        rotationRow.addView(normal, weighted(0));
        remoteAdvanced.addView(rotationRow, full(0, dp(10)));

        LinearLayout boostRow = new LinearLayout(this);
        boostRow.setOrientation(LinearLayout.HORIZONTAL);
        boostRow.setWeightSum(3f);
        Button boostOff = makeButton("BOOST AV");
        Button boost12 = makeButton("+12%");
        Button boost25 = makeButton("+25%");
        boostOff.setOnClickListener(v -> sendRemote("BOOST_0"));
        boost12.setOnClickListener(v -> sendRemote("BOOST_12"));
        boost25.setOnClickListener(v -> sendRemote("BOOST_25"));
        boostRow.addView(boostOff, weighted(dp(4)));
        boostRow.addView(boost12, weighted(dp(4)));
        boostRow.addView(boost25, weighted(0));
        remoteAdvanced.addView(boostRow, full(0, dp(10)));

        panel.addView(remoteAdvanced, full(0, dp(12)));

        advancedToggle.setOnClickListener(v -> {
            boolean open = remoteAdvanced.getVisibility() == View.VISIBLE;
            remoteAdvanced.setVisibility(open ? View.GONE : View.VISIBLE);
            advancedToggle.setText(open ? "Avancerat" : "Dölj avancerat");
        });

        Button changeRole = makeButton("Byt roll på den här mobilen");
        changeRole.setOnClickListener(v -> showRoleChooser());
        panel.addView(changeRole, full(dp(6), 0));

        return panel;
    }

    private void showProjectorPanel()'''
s = s[:m.start()] + new_remote + s[m.end():]

# Replace role switching methods and add role chooser.
pat = re.compile(r'''    private void showProjectorPanel\(\) \{.*?\n    \}\n\n    private void showRemotePanel\(\) \{.*?\n    \}\n''', re.S)
m = pat.search(s)
if not m:
    raise SystemExit("Patch misslyckades: show role methods")

new_roles = '''    private void showProjectorPanel() {
        getSharedPreferences("ui", MODE_PRIVATE).edit().putString("role", "projector").apply();
        roleChooser.setVisibility(View.GONE);
        projectorPanel.setVisibility(View.VISIBLE);
        remotePanel.setVisibility(View.GONE);
        refreshProjectorStatus();
    }

    private void showRemotePanel() {
        getSharedPreferences("ui", MODE_PRIVATE).edit().putString("role", "remote").apply();
        roleChooser.setVisibility(View.GONE);
        projectorPanel.setVisibility(View.GONE);
        remotePanel.setVisibility(View.VISIBLE);

        SharedPreferences prefs = getSharedPreferences("remote", MODE_PRIVATE);
        String ip = prefs.getString("ip", "");
        String pin = prefs.getString("pin", "");
        if (ipInput != null) ipInput.setText(ip);
        if (pinInput != null) pinInput.setText(pin);

        if (!ip.isEmpty() && pin.matches("\\\\d{6}")) {
            remoteStatus.setText("Ansluter automatiskt…");
            uiHandler.postDelayed(() -> sendRemote("PING"), 350);
        } else {
            remoteStatus.setText("Ingen projektor parkopplad ännu. Öppna Avancerat en gång för att parkoppla.");
        }
    }

    private void showRoleChooser() {
        getSharedPreferences("ui", MODE_PRIVATE).edit().remove("role").apply();
        roleChooser.setVisibility(View.VISIBLE);
        projectorPanel.setVisibility(View.GONE);
        remotePanel.setVisibility(View.GONE);
    }
'''
s = s[:m.start()] + new_roles + s[m.end():]

main.write_text(s)

# Version
b = build.read_text()
b = b.replace("versionCode 14", "versionCode 15", 1)
b = b.replace("versionName '1.4.0'", "versionName '1.5.0'", 1)
build.write_text(b)

print("v1.5 simplified UX patch applied")
