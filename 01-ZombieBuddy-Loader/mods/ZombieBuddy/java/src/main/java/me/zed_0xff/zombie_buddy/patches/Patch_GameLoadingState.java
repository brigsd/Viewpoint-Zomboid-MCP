package me.zed_0xff.zombie_buddy.patches;

import me.zed_0xff.zombie_buddy.Exposer;
import me.zed_0xff.zombie_buddy.Patch;

/**
 * Suppresses sandbox options logging that occurs in GameLoadingState.exit().
 *
 * Strategy: set a flag while inside exit(), then skip all DebugLog.log() calls
 * during that window when suppression is enabled.
 *
 * Exposed to Lua as ZombieBuddy.Patches.GameLoadingState.
 */
@Exposer.LuaClass(name = "ZombieBuddy.Patches.GameLoadingState")
public class Patch_GameLoadingState {

    /** Controlled from Lua via setSuppressSandboxLog(). */
    public static volatile boolean _suppress = false;

    /** True while GameLoadingState.exit() is on the call stack. */
    public static volatile boolean _in_exit = false;

    public static void setSuppressSandboxLog(boolean value) {
        _suppress = value;
    }

    // -------------------------------------------------------------------------
    // Track entry/exit of GameLoadingState.exit()
    // -------------------------------------------------------------------------

    @Patch(className = "zombie.gameStates.GameLoadingState", methodName = "exit")
    public static class Patch_exit {
        @Patch.OnEnter
        public static void enter() {
            _in_exit = true;
        }

        @Patch.OnExit
        public static void exit() {
            _in_exit = false;
        }
    }

    // -------------------------------------------------------------------------
    // Skip DebugLog.log() calls while inside exit() and suppression is enabled.
    // Matches both log(String) and log(DebugType, String) overloads — only the
    // former is called from exit(), so the extra coverage is harmless.
    // -------------------------------------------------------------------------

    @Patch(className = "zombie.debug.DebugLog", methodName = "log")
    public static class Patch_log {
        @Patch.OnEnter(skipOn = true)
        public static boolean enter() {
            return _suppress && _in_exit;
        }
    }
}
