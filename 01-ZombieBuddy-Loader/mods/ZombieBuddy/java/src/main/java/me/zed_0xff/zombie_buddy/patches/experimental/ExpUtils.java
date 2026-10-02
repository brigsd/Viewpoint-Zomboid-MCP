package me.zed_0xff.zombie_buddy.patches.experimental;

import me.zed_0xff.zombie_buddy.Utils;

// separate from Utils for less dependencies (ZomboidFileSystem)
public final class ExpUtils {
    private ExpUtils() {}

    /**
     * Returns the console log file path for the current process.
     * Server uses Server/server-console.txt, client/SP use console.txt.
     */
    public static String getConsoleLogPath() {
        String cacheDir = Utils.getCacheDir();
        if (Utils.isServer()) {
            return cacheDir + "/server-console.txt";
        }
        return cacheDir + "/console.txt";
    }
}
