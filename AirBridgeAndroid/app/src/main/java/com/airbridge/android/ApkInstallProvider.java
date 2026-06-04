package com.airbridge.android;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileNotFoundException;

public class ApkInstallProvider extends ContentProvider {
    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public String getType(Uri uri) {
        return "application/vnd.android.package-archive";
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) {
            throw new FileNotFoundException("Read-only provider");
        }
        Context context = getContext();
        if (context == null) {
            throw new FileNotFoundException("No context");
        }
        String filename = uri.getLastPathSegment();
        if (filename == null || filename.contains("/") || filename.contains("\\") || !filename.endsWith(".apk")) {
            throw new FileNotFoundException("Invalid APK name");
        }
        File updatesDir = new File(context.getCacheDir(), "updates");
        File apk = new File(updatesDir, filename);
        File root = updatesDir.getAbsoluteFile();
        File candidate = apk.getAbsoluteFile();
        if (!candidate.getPath().startsWith(root.getPath()) || !candidate.exists()) {
            throw new FileNotFoundException("APK not found");
        }
        return ParcelFileDescriptor.open(candidate, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] selectionArgs, String sortOrder) {
        return null;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        return 0;
    }
}
