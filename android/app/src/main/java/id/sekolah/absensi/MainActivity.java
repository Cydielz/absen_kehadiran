package id.sekolah.absensi;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends AppCompatActivity {
    private static final String PREFS = "absensi_prefs";
    private static final String KEY_SERVER = "server_url";
    private static final String KEY_DEVICE_KEY = "device_api_key";
    private static final String DEFAULT_SERVER = "http://192.168.1.10:5000";

    private EditText serverInput;
    private EditText deviceKeyInput;
    private TextView resultText;
    private ProgressBar progress;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        buildUi();
    }

    private int dp(float value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private TextView text(String value, float size, int color) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextSize(size);
        t.setTextColor(color);
        return t;
    }

    private void buildUi() {
        int blue900 = Color.rgb(11, 61, 145);
        int blue700 = Color.rgb(21, 101, 192);
        int dark = Color.rgb(16, 35, 63);
        int white = Color.WHITE;

        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(22), dp(18), dp(26));
        root.setBackgroundColor(Color.rgb(244, 248, 253));
        scroll.addView(root);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setPadding(dp(18), dp(20), dp(18), dp(20));
        header.setBackgroundColor(blue900);
        header.setGravity(Gravity.CENTER_HORIZONTAL);

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.logo);
        LinearLayout.LayoutParams logoLp = new LinearLayout.LayoutParams(dp(84), dp(84));
        logoLp.bottomMargin = dp(10);
        logo.setLayoutParams(logoLp);
        header.addView(logo);

        TextView title = text("ABSENSI SISWA", 25, white);
        title.setTypeface(null, android.graphics.Typeface.BOLD);
        title.setGravity(Gravity.CENTER_HORIZONTAL);
        header.addView(title);
        TextView subtitle = text("Scan QR Code NISN untuk mencatat kehadiran", 14, Color.WHITE);
        subtitle.setPadding(0, dp(6), 0, 0);
        subtitle.setGravity(Gravity.CENTER_HORIZONTAL);
        header.addView(subtitle);
        root.addView(header, new LinearLayout.LayoutParams(-1, -2));

        TextView lbl = text("Alamat Server Flask", 14, dark);
        lbl.setTypeface(null, android.graphics.Typeface.BOLD);
        lbl.setPadding(0, dp(22), 0, dp(6));
        root.addView(lbl);

        serverInput = new EditText(this);
        serverInput.setSingleLine(true);
        serverInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        serverInput.setHint("contoh: http://192.168.1.10:5000");
        serverInput.setText(prefs.getString(KEY_SERVER, DEFAULT_SERVER));
        root.addView(serverInput, new LinearLayout.LayoutParams(-1, dp(54)));

        TextView lblKey = text("Kode Perangkat (dari admin)", 14, dark);
        lblKey.setTypeface(null, android.graphics.Typeface.BOLD);
        lblKey.setPadding(0, dp(14), 0, dp(6));
        root.addView(lblKey);

        deviceKeyInput = new EditText(this);
        deviceKeyInput.setSingleLine(true);
        deviceKeyInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        deviceKeyInput.setHint("Tempel kode perangkat dari panel admin di sini");
        deviceKeyInput.setText(prefs.getString(KEY_DEVICE_KEY, ""));
        root.addView(deviceKeyInput, new LinearLayout.LayoutParams(-1, dp(54)));

        Button saveButton = new Button(this);
        saveButton.setText("Simpan Pengaturan");
        saveButton.setOnClickListener(v -> saveSettings());
        root.addView(saveButton, new LinearLayout.LayoutParams(-1, dp(52)));

        Button scanButton = new Button(this);
        scanButton.setText("SCAN QR CODE");
        scanButton.setTextSize(17);
        scanButton.setTextColor(white);
        scanButton.setBackgroundColor(blue700);
        LinearLayout.LayoutParams scanLp = new LinearLayout.LayoutParams(-1, dp(60));
        scanLp.topMargin = dp(18);
        root.addView(scanButton, scanLp);
        scanButton.setOnClickListener(v -> startQrScanner());

        progress = new ProgressBar(this);
        progress.setVisibility(View.GONE);
        LinearLayout.LayoutParams pp = new LinearLayout.LayoutParams(-2, -2);
        pp.gravity = Gravity.CENTER_HORIZONTAL;
        pp.topMargin = dp(18);
        root.addView(progress, pp);

        resultText = text("Siap melakukan absensi.\n\nPastikan HP/laptop berada pada jaringan yang sama dengan server.", 16, dark);
        resultText.setGravity(Gravity.CENTER);
        resultText.setPadding(dp(10), dp(24), dp(10), dp(10));
        root.addView(resultText, new LinearLayout.LayoutParams(-1, -2));

        TextView footer = text("QR Code harus berisi NISN siswa (contoh: 0012345678).\nScan pertama = catat jam masuk, scan kedua di hari yang sama = catat jam pulang.", 13, Color.DKGRAY);
        footer.setGravity(Gravity.CENTER);
        footer.setPadding(0, dp(22), 0, 0);
        root.addView(footer);

        setContentView(scroll);
    }

    private void saveSettings() {
        String url = normalizeServerUrl(serverInput.getText().toString());
        if (url.isEmpty()) {
            Toast.makeText(this, "Alamat server belum diisi", Toast.LENGTH_SHORT).show();
            return;
        }
        serverInput.setText(url);
        String deviceKey = deviceKeyInput.getText().toString().trim();
        prefs.edit()
                .putString(KEY_SERVER, url)
                .putString(KEY_DEVICE_KEY, deviceKey)
                .apply();
        Toast.makeText(this, "Pengaturan disimpan", Toast.LENGTH_SHORT).show();
    }

    private String normalizeServerUrl(String value) {
        String s = value == null ? "" : value.trim();
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        return s;
    }

    private void startQrScanner() {
        saveSettings();
        IntentIntegrator integrator = new IntentIntegrator(this);
        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE);
        integrator.setPrompt("Arahkan kamera ke QR Code NISN siswa");
        integrator.setCameraId(0);
        integrator.setBeepEnabled(true);
        integrator.setOrientationLocked(false);
        integrator.initiateScan();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, android.content.Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        IntentResult result = IntentIntegrator.parseActivityResult(requestCode, resultCode, data);
        if (result == null) return;
        if (result.getContents() == null) {
            resultText.setText("Scan dibatalkan.\nSilakan tekan SCAN QR CODE lagi.");
            return;
        }
        String nisn = extractNisn(result.getContents());
        if (nisn.isEmpty()) {
            resultText.setText("QR terbaca, tetapi isinya tidak dikenali sebagai NISN.\n\nIsi QR: " + result.getContents());
            return;
        }
        submitScan(nisn);
    }

    private String extractNisn(String raw) {
        String s = raw == null ? "" : raw.trim();
        if (s.regionMatches(true, 0, "NISN:", 0, 5)) s = s.substring(5).trim();
        // This system expects NISN digits. Remove separators often found in printed QR payloads.
        s = s.replaceAll("[^0-9]", "");
        return s;
    }

    private void submitScan(String nisn) {
        String server = normalizeServerUrl(serverInput.getText().toString());
        String deviceKey = deviceKeyInput.getText().toString().trim();
        if (server.isEmpty()) {
            resultText.setText("Alamat server belum diatur.");
            return;
        }
        if (deviceKey.isEmpty()) {
            resultText.setText("Kode perangkat belum diisi.\n\nMinta kode perangkat ke admin sekolah lalu isi di kolom \"Kode Perangkat\", baru scan bisa dipakai.");
            return;
        }
        prefs.edit().putString(KEY_SERVER, server).putString(KEY_DEVICE_KEY, deviceKey).apply();
        progress.setVisibility(View.VISIBLE);
        resultText.setText("Memproses NISN " + nisn + " ...");

        executor.execute(() -> {
            String response;
            int status = 0;
            try {
                URL url = new URL(server + "/scan");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(15000);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                conn.setRequestProperty("Accept", "application/json");
                conn.setRequestProperty("X-Device-Key", deviceKey);

                String deviceId = Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID);
                if (deviceId == null || deviceId.isEmpty()) deviceId = "ANDROID";
                JSONObject body = new JSONObject();
                body.put("nisn", nisn);
                body.put("device_id", deviceId);

                byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(bytes);
                }
                status = conn.getResponseCode();
                InputStream stream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
                response = readAll(stream);
                conn.disconnect();
            } catch (Exception e) {
                response = "NETWORK_ERROR:" + e.getMessage();
            }

            final int httpStatus = status;
            final String finalResponse = response;
            runOnUiThread(() -> showScanResponse(nisn, httpStatus, finalResponse));
        });
    }

    private String readAll(InputStream stream) throws Exception {
        if (stream == null) return "";
        StringBuilder sb = new StringBuilder();
        try (BufferedReader br = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
        }
        return sb.toString();
    }

    private void showScanResponse(String nisn, int httpStatus, String raw) {
        progress.setVisibility(View.GONE);
        try {
            if (raw.startsWith("NETWORK_ERROR:")) {
                resultText.setText("GAGAL TERHUBUNG\n\nPastikan server Flask aktif dan HP berada di Wi-Fi yang sama.\n\nDetail: " + raw.substring(14));
                return;
            }
            JSONObject obj = new JSONObject(raw);
            String code = obj.optString("code", "");
            String message = obj.optString("message", "Tidak ada pesan.");
            String student = "";
            if (obj.has("student")) {
                JSONObject s = obj.getJSONObject("student");
                student = "\n\nNama: " + s.optString("nama", "-") +
                        "\nNISN: " + s.optString("nisn", nisn) +
                        "\nKelas: " + s.optString("kelas", "-");
            }
            String extra = "";
            JSONObject a = obj.optJSONObject("attendance");
            if (a != null) {
                if ("ATTENDANCE_RECORDED".equals(code)) {
                    extra = "\nJam masuk: " + a.optString("jam_masuk", "-");
                } else if ("CHECKOUT_RECORDED".equals(code)) {
                    extra = "\nJam masuk: " + a.optString("jam_masuk", "-") + "\nJam pulang: " + a.optString("jam_keluar", "-");
                } else if ("ALREADY_ATTENDED".equals(code) || "ALREADY_COMPLETE".equals(code)) {
                    extra = "\nJam masuk: " + a.optString("jam_masuk", "-");
                    if (a.has("jam_keluar") && !a.isNull("jam_keluar")) {
                        extra += "\nJam pulang: " + a.optString("jam_keluar", "-");
                    }
                }
            }
            String wa = "";
            if (obj.has("whatsapp")) {
                JSONObject w = obj.optJSONObject("whatsapp");
                if (w != null) {
                    boolean sent = w.optBoolean("sent", false);
                    if (sent) {
                        wa = "\nWhatsApp: notifikasi terkirim";
                    } else {
                        String reason = w.optString("reason", "");
                        wa = "\nWhatsApp: GAGAL terkirim" + (reason.isEmpty() ? "" : " (" + reason + ")");
                    }
                }
            }
            resultText.setText(message + student + extra + wa + "\n\nHTTP " + httpStatus);
        } catch (Exception e) {
            resultText.setText("Respons server tidak dapat dibaca.\n\n" + raw);
        }
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}
