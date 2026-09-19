from pathlib import Path
import sys

root = Path(sys.argv[1])
main = root / "app/src/main/java/se/projektorlage/app/MainActivity.java"
manifest = root / "app/src/main/AndroidManifest.xml"
build = root / "app/build.gradle"
player = root / "app/src/main/java/se/projektorlage/app/VideoPlayerActivity.java"

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Patch misslyckades: {label}")
    return text.replace(old, new, 1)

s = main.read_text()

s = replace_once(s,
'''        Button netflix = makeButton("ÖPPNA NETFLIX");
        netflix.setOnClickListener(v -> openNetflix());
        panel.addView(netflix, full(0, dp(10)));

        Button brightness = makeButton("TILLÅT ROTATION + LJUSSTYRKA");''',
'''        Button netflix = makeButton("ÖPPNA NETFLIX");
        netflix.setOnClickListener(v -> openNetflix());
        panel.addView(netflix, full(0, dp(10)));

        Button localVideo = makeButton("LOKAL VIDEO – SPEGEL / 180°");
        localVideo.setOnClickListener(v -> startActivity(new Intent(this, VideoPlayerActivity.class)));
        panel.addView(localVideo, full(0, dp(10)));

        Button brightness = makeButton("TILLÅT ROTATION + LJUSSTYRKA");''',
"local video button")

main.write_text(s)

m = manifest.read_text()
m = replace_once(m,
'''        <activity
            android:name=".MainActivity"''',
'''        <activity
            android:name=".VideoPlayerActivity"
            android:exported="false"
            android:screenOrientation="landscape"
            android:configChanges="orientation|screenSize" />

        <activity
            android:name=".MainActivity"''',
"video activity manifest")
manifest.write_text(m)

player.write_text(r'''package se.projektorlage.app;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.MediaController;
import android.widget.TextView;
import android.widget.VideoView;

public class VideoPlayerActivity extends Activity {
    private static final int PICK_VIDEO = 7101;

    private VideoView videoView;
    private TextView status;
    private boolean mirrored = true;
    private boolean rotated180 = true;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN,
                WindowManager.LayoutParams.FLAG_FULLSCREEN);
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
        setContentView(buildUi());
        applyTransform();
    }

    private View buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);

        videoView = new VideoView(this);
        FrameLayout.LayoutParams videoLp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
                Gravity.CENTER);
        root.addView(videoView, videoLp);

        MediaController controller = new MediaController(this);
        controller.setAnchorView(videoView);
        videoView.setMediaController(controller);

        LinearLayout controls = new LinearLayout(this);
        controls.setOrientation(LinearLayout.HORIZONTAL);
        controls.setGravity(Gravity.CENTER_VERTICAL);
        controls.setPadding(dp(10), dp(6), dp(10), dp(6));
        controls.setBackgroundColor(Color.argb(210, 12, 12, 12));

        Button pick = button("VÄLJ VIDEO");
        Button mirror = button("SPEGEL");
        Button rotate = button("180°");
        Button close = button("STÄNG");
        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(14f);
        status.setPadding(dp(10), 0, dp(10), 0);

        pick.setOnClickListener(v -> pickVideo());
        mirror.setOnClickListener(v -> {
            mirrored = !mirrored;
            applyTransform();
        });
        rotate.setOnClickListener(v -> {
            rotated180 = !rotated180;
            applyTransform();
        });
        close.setOnClickListener(v -> finish());

        controls.addView(pick);
        controls.addView(mirror);
        controls.addView(rotate);
        controls.addView(status, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        controls.addView(close);

        FrameLayout.LayoutParams controlLp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.TOP);
        root.addView(controls, controlLp);

        TextView help = new TextView(this);
        help.setText("För projektorn: testa SPEGEL och 180° var för sig tills texten på väggen är rätt.");
        help.setTextColor(Color.WHITE);
        help.setTextSize(14f);
        help.setGravity(Gravity.CENTER);
        help.setBackgroundColor(Color.argb(180, 0, 0, 0));
        help.setPadding(dp(10), dp(6), dp(10), dp(6));

        FrameLayout.LayoutParams helpLp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM);
        root.addView(help, helpLp);

        return root;
    }

    private Button button(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setTextSize(13f);
        b.setAllCaps(false);
        return b;
    }

    private void pickVideo() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("video/*");
        startActivityForResult(intent, PICK_VIDEO);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_VIDEO || resultCode != RESULT_OK || data == null) return;
        Uri uri = data.getData();
        if (uri == null) return;

        try {
            getContentResolver().takePersistableUriPermission(uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Exception ignored) {}

        videoView.setVideoURI(uri);
        videoView.setOnPreparedListener(mp -> {
            applyTransform();
            videoView.start();
        });
        videoView.requestFocus();
    }

    private void applyTransform() {
        videoView.setScaleX(mirrored ? -1f : 1f);
        videoView.setRotation(rotated180 ? 180f : 0f);
        if (status != null) {
            status.setText((mirrored ? "SPEGEL PÅ" : "SPEGEL AV") +
                    " • " + (rotated180 ? "180° PÅ" : "180° AV"));
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
''')

s = build.read_text()
s = s.replace("versionCode 5", "versionCode 6", 1)
s = s.replace("versionName '0.5.0'", "versionName '0.6.0'", 1)
build.write_text(s)

print("v0.6 patch applied")
