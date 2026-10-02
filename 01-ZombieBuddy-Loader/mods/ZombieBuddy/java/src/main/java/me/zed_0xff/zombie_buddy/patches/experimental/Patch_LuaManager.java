package me.zed_0xff.zombie_buddy.patches.experimental;

import me.zed_0xff.zombie_buddy.*;

import zombie.Lua.LuaManager;

public class Patch_LuaManager {
    public static boolean isInitialized = false;

    @Patch(className = "zombie.Lua.LuaManager", methodName = "init")
    public class Patch_init {
        @Patch.OnEnter
        public static void enter() {
            Logger.debug("before LuaManager.init");
        }

        @Patch.OnExit
        public static void exit() {
            Logger.debug("after LuaManager.init");
            if (!isInitialized) {
                isInitialized = true;
                if (Agent.arguments.containsKey("lua_init_script")) {
                    String initScript = Agent.arguments.get("lua_init_script");
                    Logger.info("Running init script: " + initScript);
                    LuaManager.RunLua(initScript);
                }
            }
        }
    }

    @Patch(className = "zombie.Lua.LuaManager", methodName = "LoadDirBase")
    public class Patch_LoadDirBase {
        @Patch.OnEnter
        public static void enter(String sub, @Patch.Local("t0") long t0) {
            Logger.info("LuaManager.LoadDirBase(\"" + sub + "\") ...");
            t0 = System.nanoTime();
        }

        @Patch.OnExit
        public static void exit(String sub, @Patch.Local("t0") long t0) {
            long elapsedMS = (System.nanoTime() - t0) / 1_000_000L;
            if ( elapsedMS > 1000 ) Logger.info("LuaManager.LoadDirBase(\"" + sub + "\") took " + elapsedMS + " ms");
        }
    }

    @Patch(className = "zombie.Lua.LuaManager", methodName = "RunLua")
    public class Patch_RunLua {
        @Patch.OnEnter
        public static void enter(String filename, @Patch.Local("t0") long t0) {
            // Logger.info("LuaManager.RunLua(\"" + filename + "\") ...");
            t0 = System.nanoTime();
        }

        @Patch.OnExit
        public static void exit(String filename, @Patch.Local("t0") long t0) {
            long elapsedMS = (System.nanoTime() - t0) / 1_000_000L;
            if ( elapsedMS > 1000 ) Logger.info("LuaManager.RunLua(\"" + filename + "\") took " + elapsedMS + " ms");
        }
    }
}
