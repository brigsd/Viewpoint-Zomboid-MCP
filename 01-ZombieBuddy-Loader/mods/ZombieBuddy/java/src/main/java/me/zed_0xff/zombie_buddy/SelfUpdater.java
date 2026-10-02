package me.zed_0xff.zombie_buddy;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

/**
 * Handles replacing the running ZombieBuddy JAR with a newer version
 * (e.g. from the mods directory). Supports immediate replace or deferred
 * replace via a .new file when the current JAR is locked (e.g. on Windows).
 * Also handles verification of JAR signatures and certificates.
 */
public final class SelfUpdater {
    private SelfUpdater() {}

    private static String pendingNewVersion = null;

    /**
     * Expected SHA-256 fingerprint of the ZombieBuddy signing certificate.
     * Used to verify that a JAR is signed by the trusted ZombieBuddy key.
     */
    private static final byte[] EXPECTED_FINGERPRINT = {
        (byte)0xA7, (byte)0x75, (byte)0x10, (byte)0x1B, (byte)0xFB, (byte)0x6C, (byte)0x33, (byte)0xA9,
        (byte)0x2C, (byte)0xDF, (byte)0x25, (byte)0x20, (byte)0xAC, (byte)0x8D, (byte)0x02, (byte)0x95,
        (byte)0xCE, (byte)0xBF, (byte)0x89, (byte)0x0C, (byte)0x84, (byte)0x05, (byte)0x97, (byte)0x37,
        (byte)0x7F, (byte)0xD0, (byte)0x9B, (byte)0x17, (byte)0xD0, (byte)0xEA, (byte)0xDD, (byte)0x97
    };

    public static String getNewVersion() {
        return pendingNewVersion;
    }

    public static String getExclusionReasonSuffix(Path jarPath) {
        if (jarPath == null) {
            return " (null not found)";
        }
        if (!Files.isRegularFile(jarPath)) {
            return " (" + jarPath.toAbsolutePath() + " not found)";
        }

        StringBuilder sb = new StringBuilder();
        Manifest manifest = getJarManifest(jarPath);
        if (manifest != null) {
            String manifestVersion = manifest.getMainAttributes().getValue("Implementation-Version");
            if (manifestVersion != null) {
                sb.append(" (version ").append(manifestVersion).append(")");
            }
        }

        Path currentJarPath = Utils.getCurrentJarPath();
        if (checkAndUpdateIfNewer(jarPath, currentJarPath, ZombieBuddy.getVersion(), Loader.g_verbosity)) {
            String newVer = getNewVersion();
            if (newVer != null) {
                sb.append(" -> updating to ").append(newVer);
            }
        }
        return sb.toString();
    }

    public static void performUpdate(Path currentJarPath, Path newJarPath, String newVersion) {
        if (currentJarPath == null) {
            return;
        }
        pendingNewVersion = newVersion;
        Logger.info("replacing " + currentJarPath + " with " + newJarPath);
        try {
            Path backupPath = currentJarPath.resolveSibling(currentJarPath.getFileName() + ".bak");
            if (Files.exists(currentJarPath)) {
                try {
                    Files.move(currentJarPath, backupPath, StandardCopyOption.REPLACE_EXISTING);
                    Logger.info("Renamed existing JAR to " + backupPath);
                } catch (Exception e) {
                    Logger.info("Could not rename existing JAR (may be locked): " + e.getMessage());
                }
            }

            Files.copy(newJarPath, currentJarPath, StandardCopyOption.REPLACE_EXISTING);
            Logger.info("Successfully replaced JAR file");
        } catch (Exception e) {
            Logger.error("Error replacing JAR file: " + e.getMessage());
            Logger.error("JAR may be locked (e.g., on Windows). Copying to .new file for deferred update...");
            try {
                Path deferredPath = currentJarPath.resolveSibling(currentJarPath.getFileName() + ".new");
                Files.copy(newJarPath, deferredPath, StandardCopyOption.REPLACE_EXISTING);
                Logger.info("Copied new JAR to " + deferredPath + " - update will be applied on next game launch");
            } catch (Exception e2) {
                Logger.error("Error copying to .new file: " + e2.getMessage());
                e2.printStackTrace();
            }
            e.printStackTrace();
        }
    }

    public static boolean checkAndUpdateIfNewer(Path jarPath, Path currentJarPath, String currentVersion, int verbosity) {
        if (jarPath == null || !Files.isRegularFile(jarPath)) {
            return false;
        }

        try {
            Certificate[] certs = verifyJarAndGetCerts(jarPath);
            if (certs == null || certs.length == 0) {
                return false;
            }

            if (verbosity > 0) {
                Logger.info("" + jarPath + " is signed with " + certs.length + " certificate(s)");
            }

            for (int certIdx = 0; certIdx < certs.length; certIdx++) {
                if (certs[certIdx] instanceof X509Certificate) {
                    X509Certificate x509Cert = (X509Certificate) certs[certIdx];
                    byte[] fingerprint = getCertFingerprint(x509Cert, certIdx + 1, verbosity);
                    if (fingerprint != null && java.util.Arrays.equals(fingerprint, EXPECTED_FINGERPRINT)) {
                        Manifest manifest = getJarManifest(jarPath);
                        if (manifest != null) {
                            String manifestVersion = manifest.getMainAttributes().getValue("Implementation-Version");
                            if (manifestVersion != null && Utils.isVersionNewer(manifestVersion, currentVersion)) {
                                performUpdate(currentJarPath, jarPath, manifestVersion);
                                return true;
                            }
                        }
                    }
                }
            }
        } catch (Exception e) {
            Logger.error("Error verifying JAR signature: " + e.getMessage());
        }
        return false;
    }

    public static Certificate[] verifyJarAndGetCerts(Path jarPath) throws Exception {
        Manifest mf = getJarManifest(jarPath);
        if (mf == null) {
            return null;
        }

        try (JarFile jar = new JarFile(jarPath.toFile(), true)) {
            Certificate[] signer = null;

            var entries = jar.entries();
            while (entries.hasMoreElements()) {
                JarEntry e = entries.nextElement();
                if (e.isDirectory()) continue;

                try (InputStream is = jar.getInputStream(e)) {
                    is.readAllBytes();
                }

                String name = e.getName();
                boolean isMeta = name.startsWith("META-INF/");
                Certificate[] certs = e.getCertificates();
                if (certs == null || certs.length == 0) {
                    if (!isMeta) {
                        throw new SecurityException("Unsigned entry: " + name);
                    }
                } else if (signer == null) {
                    signer = certs;
                }
            }

            if (signer == null) {
                throw new SecurityException("No signed entries found");
            }

            return signer;
        }
    }

    public static Manifest getJarManifest(Path jarPath) {
        if (jarPath == null) {
            return null;
        }
        try (JarFile jar = new JarFile(jarPath.toFile(), true)) {
            return jar.getManifest();
        } catch (Exception e) {
            Logger.error("Error getting JAR manifest: " + e);
            return null;
        }
    }

    private static byte[] getCertFingerprint(X509Certificate cert, int certNumber, int verbosity) {
        if (verbosity > 0) {
            Logger.info("  Certificate " + certNumber + ":");
            Logger.info("    Subject: " + cert.getSubjectX500Principal().getName());
            Logger.info("    Issuer: " + cert.getIssuerX500Principal().getName());
            Logger.info("    Serial Number: " + cert.getSerialNumber().toString(16).toUpperCase());
            Logger.info("    Valid From: " + cert.getNotBefore());
            Logger.info("    Valid Until: " + cert.getNotAfter());
        }

        try {
            byte[] sha256Bytes = Utils.sha256(cert.getEncoded());
            if (sha256Bytes != null && verbosity > 0) {
                Logger.info("    SHA-256 Fingerprint: " + Utils.bytesToHex(sha256Bytes, "%02X", ":"));
            }
            return sha256Bytes;
        } catch (Exception e) {
            Logger.error("    Error computing certificate fingerprints: " + e.getMessage());
        }
        return null;
    }
}
