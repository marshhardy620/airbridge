package com.airbridge.android;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class MainActivity extends Activity {
    private static final int PICK_FILES_REQUEST = 7001;

    private AirBridgeService service;
    private LinearLayout peerList;
    private LinearLayout eventList;
    private TextView statusText;
    private TextView localUrlText;
    private EditText manualInput;
    private EditText messageInput;
    private Button sendMessageButton;
    private Button sendFileButton;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
        service = new AirBridgeService(this, new AirBridgeService.Callback() {
            @Override
            public void onChanged() {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        refreshUi();
                    }
                });
            }

            @Override
            public void onStatus(final String message) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        statusText.setText(message);
                    }
                });
            }
        });
        service.start();
        refreshUi();
    }

    @Override
    protected void onDestroy() {
        if (service != null) {
            service.stop();
        }
        super.onDestroy();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_FILES_REQUEST || resultCode != RESULT_OK || data == null || service == null) {
            return;
        }
        List<Uri> uris = new ArrayList<>();
        if (data.getClipData() != null) {
            for (int i = 0; i < data.getClipData().getItemCount(); i++) {
                uris.add(data.getClipData().getItemAt(i).getUri());
            }
        } else if (data.getData() != null) {
            uris.add(data.getData());
        }
        if (!uris.isEmpty()) {
            service.sendFiles(uris);
        }
    }

    private void buildUi() {
        int green = Color.rgb(29, 127, 99);
        int ink = Color.rgb(22, 32, 29);
        int muted = Color.rgb(96, 112, 107);
        int bg = Color.rgb(245, 248, 247);

        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(bg);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(18), dp(18), dp(24));
        scrollView.addView(root, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        TextView title = new TextView(this);
        title.setText("AirBridge");
        title.setTextColor(ink);
        title.setTextSize(28);
        title.setGravity(Gravity.START);
        title.setTypeface(title.getTypeface(), 1);
        root.addView(title);

        statusText = new TextView(this);
        statusText.setText("Starting...");
        statusText.setTextColor(muted);
        statusText.setTextSize(14);
        statusText.setPadding(0, dp(6), 0, dp(10));
        root.addView(statusText);

        localUrlText = label("Local address: loading", muted, 14);
        root.addView(localUrlText);

        root.addView(sectionTitle("Nearby Devices"));
        peerList = new LinearLayout(this);
        peerList.setOrientation(LinearLayout.VERTICAL);
        root.addView(peerList);

        LinearLayout manualRow = new LinearLayout(this);
        manualRow.setOrientation(LinearLayout.HORIZONTAL);
        manualRow.setPadding(0, dp(8), 0, 0);
        manualInput = new EditText(this);
        manualInput.setSingleLine(true);
        manualInput.setHint("Add manually, e.g. 10.85.168.94:8765");
        manualInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        manualRow.addView(manualInput, new LinearLayout.LayoutParams(0, dp(48), 1));
        Button addButton = actionButton("Add", green);
        addButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                service.addManualPeer(manualInput.getText().toString());
            }
        });
        manualRow.addView(addButton, new LinearLayout.LayoutParams(dp(84), dp(48)));
        root.addView(manualRow);

        root.addView(sectionTitle("Send Message"));
        messageInput = new EditText(this);
        messageInput.setMinLines(3);
        messageInput.setGravity(Gravity.TOP);
        messageInput.setHint("Type the message to send");
        messageInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        root.addView(messageInput, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        LinearLayout sendRow = new LinearLayout(this);
        sendRow.setOrientation(LinearLayout.HORIZONTAL);
        sendRow.setPadding(0, dp(10), 0, 0);
        sendMessageButton = actionButton("Send Message", green);
        sendMessageButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                service.sendMessage(messageInput.getText().toString());
                messageInput.setText("");
            }
        });
        sendRow.addView(sendMessageButton, new LinearLayout.LayoutParams(0, dp(48), 1));

        sendFileButton = actionButton("Choose File", Color.rgb(39, 110, 241));
        sendFileButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                openFilePicker();
            }
        });
        LinearLayout.LayoutParams fileParams = new LinearLayout.LayoutParams(0, dp(48), 1);
        fileParams.setMargins(dp(10), 0, 0, 0);
        sendRow.addView(sendFileButton, fileParams);
        root.addView(sendRow);

        root.addView(sectionTitle("Received History"));
        eventList = new LinearLayout(this);
        eventList.setOrientation(LinearLayout.VERTICAL);
        root.addView(eventList);

        setContentView(scrollView);
    }

    private void openFilePicker() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        startActivityForResult(intent, PICK_FILES_REQUEST);
    }

    private void refreshUi() {
        if (service == null) {
            return;
        }
        localUrlText.setText("Local address: " + service.localUrl());

        peerList.removeAllViews();
        List<Peer> peers = service.peers();
        if (peers.isEmpty()) {
            peerList.addView(label("No devices found yet. You can manually add the address shown by Windows.", Color.rgb(96, 112, 107), 14));
        } else {
            for (final Peer peer : peers) {
                Button row = actionButton(peer.name + "\n" + peer.url, peer.id.equals(service.selectedPeerId()) ? Color.rgb(29, 127, 99) : Color.rgb(84, 96, 92));
                row.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
                row.setAllCaps(false);
                row.setOnClickListener(new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        service.selectPeer(peer.id);
                    }
                });
                LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        dp(58)
                );
                params.setMargins(0, 0, 0, dp(8));
                peerList.addView(row, params);
            }
        }

        boolean hasPeer = service.selectedPeer() != null;
        sendMessageButton.setEnabled(hasPeer);
        sendFileButton.setEnabled(hasPeer);

        eventList.removeAllViews();
        List<TransferEvent> events = service.events();
        if (events.isEmpty()) {
            eventList.addView(label("No messages or files yet.", Color.rgb(96, 112, 107), 14));
        } else {
            for (TransferEvent event : events) {
                eventList.addView(eventRow(event));
            }
        }
    }

    private TextView eventRow(TransferEvent event) {
        TextView view = label(event.summary(), Color.rgb(22, 32, 29), 14);
        view.setPadding(dp(12), dp(10), dp(12), dp(10));
        view.setBackgroundColor(Color.WHITE);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, 0, 0, dp(8));
        view.setLayoutParams(params);
        return view;
    }

    private TextView sectionTitle(String text) {
        TextView view = label(text, Color.rgb(22, 32, 29), 18);
        view.setTypeface(view.getTypeface(), 1);
        view.setPadding(0, dp(22), 0, dp(8));
        return view;
    }

    private TextView label(String text, int color, int sp) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(color);
        view.setTextSize(sp);
        view.setLineSpacing(0, 1.08f);
        return view;
    }

    private Button actionButton(String text, int color) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(Color.WHITE);
        button.setTextSize(14);
        button.setBackgroundColor(color);
        button.setAllCaps(false);
        return button;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static final class AirBridgeService {
        interface Callback {
            void onChanged();
            void onStatus(String message);
        }

        private static final String APP_NAME = "AirBridge";
        private static final String APP_VERSION = "0.1.3";
        private static final int DISCOVERY_PORT = 45678;
        private static final int PREFERRED_HTTP_PORT = 8765;
        private static final long PEER_TTL_MS = 20_000;
        private static final int[] SCAN_PORTS = new int[]{8765, 8766, 8767};

        private final Context context;
        private final Callback callback;
        private final Handler mainHandler = new Handler(Looper.getMainLooper());
        private final ExecutorService networkPool = Executors.newCachedThreadPool();
        private final ExecutorService scanPool = Executors.newFixedThreadPool(32);
        private final Map<String, Peer> peers = Collections.synchronizedMap(new HashMap<String, Peer>());
        private final List<TransferEvent> events = Collections.synchronizedList(new ArrayList<TransferEvent>());
        private final Map<String, File> receivedFiles = Collections.synchronizedMap(new HashMap<String, File>());
        private final String deviceId;
        private final File receivedDir;

        private volatile boolean running;
        private volatile String selectedPeerId;
        private volatile int httpPort = PREFERRED_HTTP_PORT;
        private ServerSocket serverSocket;
        private DatagramSocket discoverySocket;
        private WifiManager.MulticastLock multicastLock;

        AirBridgeService(Context context, Callback callback) {
            this.context = context.getApplicationContext();
            this.callback = callback;
            SharedPreferences preferences = this.context.getSharedPreferences("airbridge", Context.MODE_PRIVATE);
            String savedId = preferences.getString("device_id", null);
            if (savedId == null) {
                savedId = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
                preferences.edit().putString("device_id", savedId).apply();
            }
            deviceId = savedId;
            File baseDir = this.context.getExternalFilesDir(null);
            if (baseDir == null) {
                baseDir = this.context.getFilesDir();
            }
            receivedDir = new File(baseDir, "AirBridge Received");
            if (!receivedDir.exists()) {
                receivedDir.mkdirs();
            }
        }

        void start() {
            if (running) {
                return;
            }
            running = true;
            acquireMulticastLock();
            networkPool.execute(new Runnable() {
                @Override
                public void run() {
                    startHttpServer();
                }
            });
            networkPool.execute(new Runnable() {
                @Override
                public void run() {
                    startDiscovery();
                }
            });
            networkPool.execute(new Runnable() {
                @Override
                public void run() {
                    scanLoop();
                }
            });
            status("Finding nearby devices...");
        }

        void stop() {
            running = false;
            closeQuietly(discoverySocket);
            closeQuietly(serverSocket);
            if (multicastLock != null && multicastLock.isHeld()) {
                multicastLock.release();
            }
            networkPool.shutdownNow();
            scanPool.shutdownNow();
        }

        List<Peer> peers() {
            removeStalePeers();
            List<Peer> copy;
            synchronized (peers) {
                copy = new ArrayList<>(peers.values());
            }
            Collections.sort(copy, new Comparator<Peer>() {
                @Override
                public int compare(Peer a, Peer b) {
                    return a.name.compareToIgnoreCase(b.name);
                }
            });
            return copy;
        }

        List<TransferEvent> events() {
            synchronized (events) {
                return new ArrayList<>(events);
            }
        }

        String selectedPeerId() {
            return selectedPeerId;
        }

        Peer selectedPeer() {
            return selectedPeerId == null ? null : peers.get(selectedPeerId);
        }

        void selectPeer(String peerId) {
            selectedPeerId = peerId;
            Peer peer = peers.get(peerId);
            if (peer != null) {
                status("Selected " + peer.name);
            }
            changed();
        }

        String localUrl() {
            return "http://" + currentIPv4Address() + ":" + httpPort;
        }

        void addManualPeer(String rawValue) {
            final String value = normalizeUrl(rawValue);
            if (value.length() == 0) {
                status("Enter the peer address");
                return;
            }
            networkPool.execute(new Runnable() {
                @Override
                public void run() {
                    try {
                        Peer peer = fetchPeer(value, "manual", 1800);
                        upsertPeer(peer);
                        selectedPeerId = peer.id;
                        status("Device added");
                        changed();
                    } catch (Exception error) {
                        status("Add failed: " + error.getMessage());
                    }
                }
            });
        }

        void sendMessage(final String text) {
            final Peer peer = selectedPeer();
            if (peer == null) {
                status("Select a device first");
                return;
            }
            final String clean = text == null ? "" : text.trim();
            if (clean.length() == 0) {
                status("Enter a message first");
                return;
            }
            networkPool.execute(new Runnable() {
                @Override
                public void run() {
                    try {
                        JSONObject payload = new JSONObject();
                        payload.put("fromId", deviceId);
                        payload.put("fromName", deviceName());
                        payload.put("text", clean);
                        payload.put("createdAt", nowMs());
                        postJson(peer, "/api/inbox/message", payload);
                        addEvent(new TransferEvent("sent", peer.name, "message", clean, "", 0));
                        status("Message sent");
                    } catch (Exception error) {
                        status("Message send failed: " + error.getMessage());
                    }
                }
            });
        }

        void sendFiles(final List<Uri> uris) {
            final Peer peer = selectedPeer();
            if (peer == null) {
                status("Select a device first");
                return;
            }
            for (final Uri uri : uris) {
                networkPool.execute(new Runnable() {
                    @Override
                    public void run() {
                        sendFile(uri, peer);
                    }
                });
            }
        }

        private void startHttpServer() {
            try {
                serverSocket = makeServerSocket();
                httpPort = serverSocket.getLocalPort();
                changed();
                while (running) {
                    Socket socket = serverSocket.accept();
                    socket.setSoTimeout(15_000);
                    networkPool.execute(new HttpHandler(socket));
                }
            } catch (SocketTimeoutException ignored) {
            } catch (IOException error) {
                if (running) {
                    status("HTTP service failed to start: " + error.getMessage());
                }
            }
        }

        private ServerSocket makeServerSocket() throws IOException {
            IOException lastError = null;
            for (int port = PREFERRED_HTTP_PORT; port <= PREFERRED_HTTP_PORT + 100; port++) {
                try {
                    ServerSocket socket = new ServerSocket();
                    socket.setReuseAddress(true);
                    socket.bind(new InetSocketAddress(port));
                    return socket;
                } catch (IOException error) {
                    lastError = error;
                }
            }
            throw lastError == null ? new IOException("No available port") : lastError;
        }

        private void startDiscovery() {
            try {
                discoverySocket = new DatagramSocket(null);
                discoverySocket.setReuseAddress(true);
                discoverySocket.setBroadcast(true);
                discoverySocket.bind(new InetSocketAddress(DISCOVERY_PORT));
            } catch (IOException error) {
                status("Discovery service failed to start: " + error.getMessage());
                return;
            }

            networkPool.execute(new Runnable() {
                @Override
                public void run() {
                    broadcastLoop();
                }
            });

            byte[] buffer = new byte[4096];
            while (running) {
                try {
                    DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                    discoverySocket.receive(packet);
                    String text = new String(packet.getData(), packet.getOffset(), packet.getLength(), StandardCharsets.UTF_8);
                    JSONObject object = new JSONObject(text);
                    if (!APP_NAME.equals(object.optString("app"))) {
                        continue;
                    }
                    String id = object.optString("id");
                    if (deviceId.equals(id) || id.length() == 0) {
                        continue;
                    }
                    String host = object.optString("host", packet.getAddress().getHostAddress());
                    if (host.startsWith("127.")) {
                        host = packet.getAddress().getHostAddress();
                    }
                    Peer peer = new Peer(
                            id,
                            object.optString("name", "Nearby device"),
                            host,
                            object.optInt("port", PREFERRED_HTTP_PORT),
                            "http://" + host + ":" + object.optInt("port", PREFERRED_HTTP_PORT),
                            "auto",
                            nowMs()
                    );
                    upsertPeer(peer);
                    changed();
                } catch (Exception ignored) {
                }
            }
        }

        private void broadcastLoop() {
            while (running) {
                try {
                    byte[] data = discoveryPayload().toString().getBytes(StandardCharsets.UTF_8);
                    for (InetAddress address : broadcastAddresses()) {
                        DatagramPacket packet = new DatagramPacket(data, data.length, address, DISCOVERY_PORT);
                        discoverySocket.send(packet);
                    }
                } catch (Exception ignored) {
                }
                sleep(2500);
            }
        }

        private JSONObject discoveryPayload() throws JSONException {
            JSONObject object = new JSONObject();
            object.put("app", APP_NAME);
            object.put("version", APP_VERSION);
            object.put("id", deviceId);
            object.put("name", deviceName());
            object.put("host", currentIPv4Address());
            object.put("port", httpPort);
            object.put("url", localUrl());
            object.put("ts", nowMs());
            return object;
        }

        private void scanLoop() {
            sleep(3000);
            while (running) {
                scanLanOnce();
                sleep(35_000);
            }
        }

        private void scanLanOnce() {
            String ip = currentIPv4Address();
            String[] parts = ip.split("\\.");
            if (parts.length != 4 || ip.startsWith("127.")) {
                return;
            }
            int a;
            int b;
            int c;
            try {
                a = Integer.parseInt(parts[0]);
                b = Integer.parseInt(parts[1]);
                c = Integer.parseInt(parts[2]);
            } catch (NumberFormatException error) {
                return;
            }

            List<String> hosts = new ArrayList<>();
            for (int subnet = Math.max(0, c - 1); subnet <= Math.min(255, c + 1); subnet++) {
                for (int host = 1; host <= 254; host++) {
                    String candidate = a + "." + b + "." + subnet + "." + host;
                    if (!candidate.equals(ip)) {
                        hosts.add(candidate);
                    }
                }
            }

            final Set<String> seen = Collections.synchronizedSet(new HashSet<String>());
            final CountDownLatch latch = new CountDownLatch(hosts.size() * SCAN_PORTS.length);
            for (final String host : hosts) {
                for (final int port : SCAN_PORTS) {
                    scanPool.execute(new Runnable() {
                        @Override
                        public void run() {
                            try {
                                if (!running || seen.contains(host + ":" + port)) {
                                    return;
                                }
                                Peer peer = fetchPeer("http://" + host + ":" + port, "scan", 550);
                                seen.add(host + ":" + port);
                                upsertPeer(peer);
                                changed();
                            } catch (Exception ignored) {
                            } finally {
                                latch.countDown();
                            }
                        }
                    });
                }
            }
            try {
                latch.await(45, TimeUnit.SECONDS);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }

        private Peer fetchPeer(String rawUrl, String source, int timeoutMs) throws IOException, JSONException {
            URL base = new URL(rawUrl);
            int port = base.getPort() > 0 ? base.getPort() : 80;
            URL stateUrl = new URL("http", base.getHost(), port, "/api/state");
            HttpURLConnection conn = (HttpURLConnection) stateUrl.openConnection();
            conn.setConnectTimeout(timeoutMs);
            conn.setReadTimeout(timeoutMs);
            conn.setRequestMethod("GET");
            try {
                if (conn.getResponseCode() >= 400) {
                    throw new IOException("HTTP " + conn.getResponseCode());
                }
                String body = readString(conn.getInputStream());
                JSONObject state = new JSONObject(body);
                JSONObject device = state.getJSONObject("device");
                String host = device.optString("host", base.getHost());
                if (host.startsWith("127.")) {
                    host = base.getHost();
                }
                int peerPort = device.optInt("port", port);
                return new Peer(
                        device.optString("id", UUID.randomUUID().toString()),
                        device.optString("name", base.getHost()),
                        host,
                        peerPort,
                        "http://" + host + ":" + peerPort,
                        source,
                        nowMs()
                );
            } finally {
                conn.disconnect();
            }
        }

        private void postJson(Peer peer, String path, JSONObject payload) throws IOException {
            byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
            URL url = new URL("http", peer.host, peer.port, path);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(8000);
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            conn.setFixedLengthStreamingMode(body.length);
            try (OutputStream out = conn.getOutputStream()) {
                out.write(body);
            }
            try {
                int code = conn.getResponseCode();
                if (code >= 400) {
                    throw new IOException(readString(conn.getErrorStream()));
                }
            } finally {
                conn.disconnect();
            }
        }

        private void sendFile(Uri uri, Peer peer) {
            String filename = displayName(uri);
            String boundary = "airbridge-" + UUID.randomUUID();
            try {
                URL url = new URL("http", peer.host, peer.port, "/api/inbox/file");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(60_000);
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

                ByteArrayOutputStream body = new ByteArrayOutputStream();
                writeField(body, boundary, "from_id", deviceId);
                writeField(body, boundary, "from_name", deviceName());
                writeField(body, boundary, "created_at", String.valueOf(nowMs()));
                writeFileHeader(body, boundary, "file", filename);
                long sentBytes;
                try (InputStream input = context.getContentResolver().openInputStream(uri)) {
                    if (input == null) {
                        throw new IOException("Unable to read file");
                    }
                    sentBytes = copy(input, body);
                }
                body.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
                byte[] payload = body.toByteArray();

                conn.setDoOutput(true);
                conn.setFixedLengthStreamingMode(payload.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(payload);
                }
                int code = conn.getResponseCode();
                if (code >= 400) {
                    throw new IOException(readString(conn.getErrorStream()));
                }
                addEvent(new TransferEvent("sent", peer.name, "file", "", filename, sentBytes));
                status("File sent: " + filename);
                conn.disconnect();
            } catch (Exception error) {
                status("File send failed: " + error.getMessage());
            }
        }

        private void writeField(OutputStream out, String boundary, String name, String value) throws IOException {
            out.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
            out.write(("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            out.write(value.getBytes(StandardCharsets.UTF_8));
            out.write("\r\n".getBytes(StandardCharsets.UTF_8));
        }

        private void writeFileHeader(OutputStream out, String boundary, String name, String filename) throws IOException {
            out.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
            out.write(("Content-Disposition: form-data; name=\"" + name + "\"; filename=\"" + safeFilename(filename) + "\"\r\n").getBytes(StandardCharsets.UTF_8));
            out.write("Content-Type: application/octet-stream\r\n\r\n".getBytes(StandardCharsets.UTF_8));
        }

        private void upsertPeer(Peer peer) {
            if (deviceId.equals(peer.id)) {
                return;
            }
            peers.put(peer.id, peer);
            if (selectedPeerId == null) {
                selectedPeerId = peer.id;
            }
        }

        private void removeStalePeers() {
            long cutoff = nowMs() - PEER_TTL_MS;
            synchronized (peers) {
                List<String> remove = new ArrayList<>();
                for (Peer peer : peers.values()) {
                    if (peer.lastSeen < cutoff && !"manual".equals(peer.source)) {
                        remove.add(peer.id);
                    }
                }
                for (String id : remove) {
                    peers.remove(id);
                    if (id.equals(selectedPeerId)) {
                        selectedPeerId = null;
                    }
                }
            }
        }

        private JSONObject stateJson() throws JSONException {
            JSONObject state = new JSONObject();
            state.put("app", APP_NAME);
            state.put("version", APP_VERSION);
            JSONObject device = new JSONObject();
            device.put("id", deviceId);
            device.put("name", deviceName());
            device.put("host", currentIPv4Address());
            device.put("port", httpPort);
            device.put("url", localUrl());
            device.put("receivedDir", receivedDir.getAbsolutePath());
            state.put("device", device);

            JSONArray peerArray = new JSONArray();
            for (Peer peer : peers()) {
                JSONObject item = new JSONObject();
                item.put("id", peer.id);
                item.put("name", peer.name);
                item.put("host", peer.host);
                item.put("port", peer.port);
                item.put("url", peer.url);
                item.put("source", peer.source);
                item.put("lastSeen", peer.lastSeen);
                peerArray.put(item);
            }
            state.put("peers", peerArray);

            JSONArray inbox = new JSONArray();
            synchronized (events) {
                for (TransferEvent event : events) {
                    if (!"received".equals(event.direction)) {
                        continue;
                    }
                    JSONObject item = new JSONObject();
                    item.put("id", event.id);
                    item.put("kind", event.kind);
                    item.put("fromName", event.peerName);
                    item.put("createdAt", event.createdAt);
                    item.put("text", event.text);
                    item.put("filename", event.filename);
                    item.put("size", event.size);
                    if ("file".equals(event.kind)) {
                        item.put("download_url", "/download/" + event.id);
                    }
                    inbox.put(item);
                }
            }
            state.put("inbox", inbox);
            return state;
        }

        private void receiveMessage(JSONObject payload) {
            String fromName = payload.optString("fromName", payload.optString("from_name", "Nearby device"));
            String text = payload.optString("text", "");
            addEvent(new TransferEvent("received", fromName, "message", text, "", 0));
            status("Received message from " + fromName + "");
        }

        private JSONObject receiveFile(MultipartUpload upload) throws IOException, JSONException {
            File saved = uniqueFile(receivedDir, upload.filename);
            try (FileOutputStream out = new FileOutputStream(saved)) {
                out.write(upload.fileData);
            }
            TransferEvent event = new TransferEvent("received", upload.fromName, "file", "", saved.getName(), upload.fileData.length);
            addEvent(event);
            receivedFiles.put(event.id, saved);
            status("Received file: " + saved.getName());

            JSONObject response = new JSONObject();
            response.put("ok", true);
            response.put("id", event.id);
            response.put("filename", saved.getName());
            response.put("size", upload.fileData.length);
            return response;
        }

        private void addEvent(TransferEvent event) {
            synchronized (events) {
                events.add(0, event);
                while (events.size() > 100) {
                    events.remove(events.size() - 1);
                }
            }
            changed();
        }

        private List<InetAddress> broadcastAddresses() {
            List<InetAddress> addresses = new ArrayList<>();
            try {
                addresses.add(InetAddress.getByName("255.255.255.255"));
                Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
                while (interfaces.hasMoreElements()) {
                    NetworkInterface networkInterface = interfaces.nextElement();
                    if (!networkInterface.isUp() || networkInterface.isLoopback()) {
                        continue;
                    }
                    for (InterfaceAddress item : networkInterface.getInterfaceAddresses()) {
                        InetAddress broadcast = item.getBroadcast();
                        if (broadcast != null && !addresses.contains(broadcast)) {
                            addresses.add(broadcast);
                        }
                    }
                }
            } catch (Exception ignored) {
            }
            return addresses;
        }

        private String currentIPv4Address() {
            try {
                List<String> candidates = new ArrayList<>();
                Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
                while (interfaces.hasMoreElements()) {
                    NetworkInterface networkInterface = interfaces.nextElement();
                    if (!networkInterface.isUp() || networkInterface.isLoopback()) {
                        continue;
                    }
                    Enumeration<InetAddress> addresses = networkInterface.getInetAddresses();
                    while (addresses.hasMoreElements()) {
                        InetAddress address = addresses.nextElement();
                        if (address instanceof Inet4Address && !address.isLoopbackAddress()) {
                            candidates.add(address.getHostAddress());
                        }
                    }
                }
                Collections.sort(candidates, new Comparator<String>() {
                    @Override
                    public int compare(String a, String b) {
                        return ipRank(a) - ipRank(b);
                    }
                });
                if (!candidates.isEmpty()) {
                    return candidates.get(0);
                }
            } catch (Exception ignored) {
            }
            return "127.0.0.1";
        }

        private int ipRank(String ip) {
            if (ip.startsWith("192.168.")) {
                return 0;
            }
            if (ip.startsWith("10.")) {
                return 1;
            }
            if (ip.startsWith("172.")) {
                return 2;
            }
            return 5;
        }

        private String deviceName() {
            String manufacturer = android.os.Build.MANUFACTURER == null ? "" : android.os.Build.MANUFACTURER;
            String model = android.os.Build.MODEL == null ? "Android" : android.os.Build.MODEL;
            if (model.toLowerCase(Locale.ROOT).startsWith(manufacturer.toLowerCase(Locale.ROOT))) {
                return model;
            }
            return (manufacturer + " " + model).trim();
        }

        private String displayName(Uri uri) {
            ContentResolver resolver = context.getContentResolver();
            try (Cursor cursor = resolver.query(uri, null, null, null, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                    if (index >= 0) {
                        String name = cursor.getString(index);
                        if (!TextUtils.isEmpty(name)) {
                            return name;
                        }
                    }
                }
            } catch (Exception ignored) {
            }
            String fallback = uri.getLastPathSegment();
            return fallback == null ? "file" : fallback;
        }

        private void acquireMulticastLock() {
            try {
                WifiManager wifiManager = (WifiManager) context.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
                if (wifiManager != null) {
                    multicastLock = wifiManager.createMulticastLock("airbridge-discovery");
                    multicastLock.setReferenceCounted(false);
                    multicastLock.acquire();
                }
            } catch (Exception ignored) {
            }
        }

        private String normalizeUrl(String raw) {
            if (raw == null) {
                return "";
            }
            String value = raw.trim();
            if (value.length() == 0) {
                return "";
            }
            if (!value.startsWith("http://") && !value.startsWith("https://")) {
                value = "http://" + value;
            }
            return value;
        }

        private void changed() {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    callback.onChanged();
                }
            });
        }

        private void status(final String message) {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    callback.onStatus(message);
                }
            });
        }

        private static long nowMs() {
            return System.currentTimeMillis();
        }

        private static String safeFilename(String value) {
            String name = value == null || value.trim().length() == 0 ? "file" : new File(value).getName();
            name = name.replaceAll("[\\\\/:*?\"<>|\\r\\n]", "_");
            return name.length() > 180 ? name.substring(0, 180) : name;
        }

        private static File uniqueFile(File directory, String filename) {
            if (!directory.exists()) {
                directory.mkdirs();
            }
            File candidate = new File(directory, safeFilename(filename));
            if (!candidate.exists()) {
                return candidate;
            }
            String name = candidate.getName();
            String stem = name;
            String suffix = "";
            int dot = name.lastIndexOf('.');
            if (dot > 0) {
                stem = name.substring(0, dot);
                suffix = name.substring(dot);
            }
            for (int i = 1; i < 10_000; i++) {
                candidate = new File(directory, stem + " (" + i + ")" + suffix);
                if (!candidate.exists()) {
                    return candidate;
                }
            }
            return new File(directory, UUID.randomUUID() + "-" + name);
        }

        private static void sleep(long ms) {
            try {
                Thread.sleep(ms);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }

        private static String readString(InputStream input) throws IOException {
            if (input == null) {
                return "";
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }
            return out.toString("UTF-8");
        }

        private static long copy(InputStream input, OutputStream output) throws IOException {
            byte[] buffer = new byte[256 * 1024];
            int count;
            long total = 0;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
                total += count;
            }
            return total;
        }

        private static void closeQuietly(ServerSocket socket) {
            if (socket != null) {
                try {
                    socket.close();
                } catch (IOException ignored) {
                }
            }
        }

        private static void closeQuietly(DatagramSocket socket) {
            if (socket != null) {
                socket.close();
            }
        }

        private final class HttpHandler implements Runnable {
            private final Socket socket;

            HttpHandler(Socket socket) {
                this.socket = socket;
            }

            @Override
            public void run() {
                try {
                    HttpRequest request = HttpRequest.read(socket.getInputStream());
                    if (request == null) {
                        respond(400, new JSONObject().put("ok", false).put("error", "Bad request"));
                        return;
                    }
                    route(request);
                } catch (Exception error) {
                    try {
                        respond(500, new JSONObject().put("ok", false).put("error", error.getMessage()));
                    } catch (Exception ignored) {
                    }
                } finally {
                    try {
                        socket.close();
                    } catch (IOException ignored) {
                    }
                }
            }

            private void route(HttpRequest request) throws Exception {
                if ("GET".equals(request.method) && "/api/state".equals(request.path)) {
                    respond(200, stateJson());
                    return;
                }
                if ("POST".equals(request.method) && "/api/inbox/message".equals(request.path)) {
                    receiveMessage(new JSONObject(new String(request.body, StandardCharsets.UTF_8)));
                    respond(200, new JSONObject().put("ok", true));
                    return;
                }
                if ("POST".equals(request.method) && "/api/inbox/file".equals(request.path)) {
                    MultipartUpload upload = MultipartUpload.parse(request);
                    if (upload == null) {
                        respond(400, new JSONObject().put("ok", false).put("error", "Invalid multipart body"));
                    } else {
                        respond(200, receiveFile(upload));
                    }
                    return;
                }
                if ("GET".equals(request.method) && request.path.startsWith("/download/")) {
                    String id = request.path.substring("/download/".length());
                    File file = receivedFiles.get(id);
                    if (file == null || !file.exists()) {
                        respond(404, new JSONObject().put("ok", false).put("error", "File not found"));
                    } else {
                        respondFile(file);
                    }
                    return;
                }
                respond(404, new JSONObject().put("ok", false).put("error", "Not found"));
            }

            private void respond(int status, JSONObject body) throws IOException {
                byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
                writeResponseHeader(status, "application/json; charset=utf-8", data.length);
                socket.getOutputStream().write(data);
                socket.getOutputStream().flush();
            }

            private void respondFile(File file) throws IOException {
                writeResponseHeader(200, "application/octet-stream", file.length(), "Content-Disposition: attachment; filename=\"" + file.getName() + "\"\r\n");
                try (FileInputStream input = new FileInputStream(file)) {
                    byte[] buffer = new byte[256 * 1024];
                    int count;
                    while ((count = input.read(buffer)) != -1) {
                        socket.getOutputStream().write(buffer, 0, count);
                    }
                }
                socket.getOutputStream().flush();
            }

            private void writeResponseHeader(int status, String contentType, long length) throws IOException {
                writeResponseHeader(status, contentType, length, "");
            }

            private void writeResponseHeader(int status, String contentType, long length, String extra) throws IOException {
                String reason = status == 200 ? "OK" : status == 400 ? "Bad Request" : status == 404 ? "Not Found" : "Server Error";
                String header = "HTTP/1.1 " + status + " " + reason + "\r\n"
                        + "Content-Type: " + contentType + "\r\n"
                        + "Content-Length: " + length + "\r\n"
                        + "Access-Control-Allow-Origin: *\r\n"
                        + "Connection: close\r\n"
                        + extra
                        + "\r\n";
                socket.getOutputStream().write(header.getBytes(StandardCharsets.UTF_8));
            }
        }
    }

    private static final class Peer {
        final String id;
        final String name;
        final String host;
        final int port;
        final String url;
        final String source;
        final long lastSeen;

        Peer(String id, String name, String host, int port, String url, String source, long lastSeen) {
            this.id = id;
            this.name = name;
            this.host = host;
            this.port = port;
            this.url = url;
            this.source = source;
            this.lastSeen = lastSeen;
        }
    }

    private static final class TransferEvent {
        final String id = UUID.randomUUID().toString().replace("-", "");
        final String direction;
        final String peerName;
        final String kind;
        final String text;
        final String filename;
        final long size;
        final long createdAt = System.currentTimeMillis();

        TransferEvent(String direction, String peerName, String kind, String text, String filename, long size) {
            this.direction = direction;
            this.peerName = peerName;
            this.kind = kind;
            this.text = text;
            this.filename = filename;
            this.size = size;
        }

        String summary() {
            String arrow = "sent".equals(direction) ? "Sent to " : "Received message from ";
            String time = new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date(createdAt));
            if ("message".equals(kind)) {
                return time + "  " + arrow + peerName + "：\n" + text;
            }
            return time + "  " + arrow + peerName + " file: \n" + filename + " (" + formatBytes(size) + ")";
        }

        private String formatBytes(long value) {
            if (value < 1024) {
                return value + " B";
            }
            if (value < 1024 * 1024) {
                return String.format(Locale.ROOT, "%.1f KB", value / 1024.0);
            }
            if (value < 1024L * 1024L * 1024L) {
                return String.format(Locale.ROOT, "%.1f MB", value / 1024.0 / 1024.0);
            }
            return String.format(Locale.ROOT, "%.1f GB", value / 1024.0 / 1024.0 / 1024.0);
        }
    }

    private static final class HttpRequest {
        final String method;
        final String path;
        final Map<String, String> headers;
        final byte[] body;

        private HttpRequest(String method, String path, Map<String, String> headers, byte[] body) {
            this.method = method;
            this.path = path;
            this.headers = headers;
            this.body = body;
        }

        static HttpRequest read(InputStream rawInput) throws IOException {
            BufferedInputStream input = new BufferedInputStream(rawInput);
            ByteArrayOutputStream headerOut = new ByteArrayOutputStream();
            int matched = 0;
            int value;
            byte[] ending = new byte[]{'\r', '\n', '\r', '\n'};
            while ((value = input.read()) != -1) {
                headerOut.write(value);
                if ((byte) value == ending[matched]) {
                    matched++;
                    if (matched == ending.length) {
                        break;
                    }
                } else {
                    matched = (byte) value == ending[0] ? 1 : 0;
                }
                if (headerOut.size() > 64 * 1024) {
                    return null;
                }
            }

            String headerText = headerOut.toString("UTF-8");
            String[] lines = headerText.split("\\r?\\n");
            if (lines.length == 0) {
                return null;
            }
            String[] first = lines[0].split(" ");
            if (first.length < 2) {
                return null;
            }

            Map<String, String> headers = new HashMap<>();
            for (int i = 1; i < lines.length; i++) {
                int colon = lines[i].indexOf(':');
                if (colon > 0) {
                    headers.put(lines[i].substring(0, colon).toLowerCase(Locale.ROOT), lines[i].substring(colon + 1).trim());
                }
            }
            int length = 0;
            if (headers.containsKey("content-length")) {
                try {
                    length = Integer.parseInt(headers.get("content-length"));
                } catch (NumberFormatException ignored) {
                }
            }
            byte[] body = new byte[length];
            int offset = 0;
            while (offset < length) {
                int count = input.read(body, offset, length - offset);
                if (count == -1) {
                    break;
                }
                offset += count;
            }
            return new HttpRequest(first[0], first[1].split("\\?")[0], headers, body);
        }
    }

    private static final class MultipartUpload {
        final String fromName;
        final String filename;
        final byte[] fileData;

        private MultipartUpload(String fromName, String filename, byte[] fileData) {
            this.fromName = fromName;
            this.filename = filename;
            this.fileData = fileData;
        }

        static MultipartUpload parse(HttpRequest request) {
            String contentType = request.headers.get("content-type");
            if (contentType == null) {
                return null;
            }
            int boundaryIndex = contentType.indexOf("boundary=");
            if (boundaryIndex < 0) {
                return null;
            }
            String boundary = contentType.substring(boundaryIndex + "boundary=".length()).trim();
            String body = new String(request.body, StandardCharsets.ISO_8859_1);
            String[] parts = body.split("--" + java.util.regex.Pattern.quote(boundary));
            String fromName = "Nearby device";
            String filename = "file";
            byte[] data = null;

            for (String part : parts) {
                int headerEnd = part.indexOf("\r\n\r\n");
                if (headerEnd < 0) {
                    continue;
                }
                String header = part.substring(0, headerEnd);
                String payload = part.substring(headerEnd + 4);
                if (payload.endsWith("\r\n")) {
                    payload = payload.substring(0, payload.length() - 2);
                }
                if (payload.endsWith("\r\n--")) {
                    payload = payload.substring(0, payload.length() - 4);
                }

                String name = capture(header, "name=\"([^\"]+)\"");
                if (name == null) {
                    continue;
                }
                if ("file".equals(name)) {
                    String foundFilename = capture(header, "filename=\"([^\"]+)\"");
                    filename = foundFilename == null ? "file" : foundFilename;
                    data = payload.getBytes(StandardCharsets.ISO_8859_1);
                } else if ("from_name".equals(name) || "fromName".equals(name)) {
                    fromName = payload;
                }
            }
            return data == null || data.length == 0 ? null : new MultipartUpload(fromName, filename, data);
        }

        private static String capture(String text, String pattern) {
            java.util.regex.Matcher matcher = java.util.regex.Pattern.compile(pattern).matcher(text);
            return matcher.find() ? matcher.group(1) : null;
        }
    }
}
