package me.zed_0xff.zombie_buddy.patches.experimental;

import org.lwjgl.glfw.GLFW;
import org.lwjgl.glfw.GLFWKeyCallbackI;

import sun.misc.Signal;

import me.zed_0xff.zombie_buddy.*;

/**
 * Ctrl+T dumps all Java thread stacks.
 * Uses GLFW key callback - works even if game loop hangs.
 */
public class JavaStateDumper {
    private static GLFWKeyCallbackI _originalKeyCallback = null;
    private static boolean _initialized = false;
    private static long _window = 0;

    static void init() {
        if (!_initialized) {
            _initialized = true;
            Callbacks.onDisplayCreate.register(JavaStateDumper::installKeyCallback);
            Signal.handle(new Signal("INFO"), JavaStateDumper::handleSignal);
        }
    }

    public static void handleSignal(Signal signal) {
        if ("INFO".equals(signal.getName())) {
            dumpThreadStacks();
        } else {
            Logger.warn("Received unexpected signal: " + signal);
        }
    }

    public static void installKeyCallback() {
        try {
            if (!org.lwjglx.opengl.Display.isCreated()) return;
            long window = org.lwjglx.opengl.Display.getWindow();
            if (window == _window) return; // already installed for this window
                                               //
            _window = window;
            _originalKeyCallback = GLFW.glfwSetKeyCallback(window, JavaStateDumper::handleKey);
            Logger.info("Installed GLFW key callback for Ctrl+T thread dump");
        } catch (Throwable t) {
            Logger.warn("Failed to install GLFW key callback: " + t);
        }
    }
    
    private static void handleKey(long window, int key, int scancode, int action, int mods) {
        if (key == GLFW.GLFW_KEY_T && action == GLFW.GLFW_PRESS && (mods & GLFW.GLFW_MOD_CONTROL) != 0) {
            dumpThreadStacks();
        }
        if (_originalKeyCallback != null) {
            _originalKeyCallback.invoke(window, key, scancode, action, mods);
        }
    }
    
    public static void dumpThreadStacks() {
        Logger.info("=== Thread Dump ===");
        for (var entry : Thread.getAllStackTraces().entrySet()) {
            Thread t = entry.getKey();
            StackTraceElement[] stack = entry.getValue();
            Logger.info(String.format("Thread: %s (id=%d, state=%s)", t.getName(), t.getId(), t.getState()));
            for (StackTraceElement el : stack) {
                Logger.info("    at " + el);
            }
        }
        Logger.info("=== End Thread Dump ===");
    }
}
