package me.zed_0xff.zombie_buddy.patches;

import me.zed_0xff.zombie_buddy.Callbacks;
import me.zed_0xff.zombie_buddy.Loader;
import me.zed_0xff.zombie_buddy.Patch;

public class Patch_GameWindow {
    @Patch(className = "zombie.GameWindow", methodName = "init")
    public static class Patch_init {
        @Patch.OnExit
        static void exit() {
            Callbacks.onGameInitComplete.run();
        }
    }

    @Patch(className = "zombie.GameWindow", methodName = "DoLoadingText")
    public static class Patch_DoLoadingText {
        @Patch.OnExit
        static void exit(String text) {
            Loader.g_hasDoLoadingText = true;
        }
    }
}
