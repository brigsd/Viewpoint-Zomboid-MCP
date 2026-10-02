package me.zed_0xff.zombie_buddy;

import me.zed_0xff.zombie_buddy.frontend.LogOverlay;

import java.io.PrintStream;
import java.util.Arrays;

public class Logger {
    private static final String PREFIX = "[ZB] ";
    public static final int MAX_ARG_STRING_LENGTH = 220;

    // save before PZ overrides them, so we can still log to console even if PZ's logger is messed up
    private static PrintStream out = System.out;
    private static PrintStream err = System.err;

    public static final int TRACE =  2;
    public static final int DEBUG =  1;
    public static final int INFO  =  0;
    public static final int WARN  = -1;
    public static final int ERROR = -2;

    private static void out_msg(String msg) {
        msg = PREFIX + msg;
        try {
            System.out.println(msg);
        } catch (Exception e) { // might fail on game boot
            out.println(msg);
            LogOverlay.addLine(msg);
        }
    }

    private static void err_msg(String msg) {
        msg = PREFIX + msg;
        try {
            System.err.println(msg);
        } catch (Exception e) { // see above
            err.println(msg);
            LogOverlay.addLine(msg);
        }
    }

    public static void log(int level, String message, Object... args) {
        if (Loader.g_verbosity < level) return;

        if (args != null && args.length > 0) {
            message += " " + formatArgs(args);
        }

        switch (level) {
            case TRACE -> out_msg("[t] " + message);
            case DEBUG -> out_msg("[d] " + message);
            case INFO  -> out_msg(message);
            case WARN  -> err_msg("[?] " + message);
            case ERROR -> err_msg("[!] " + message);
            default -> out_msg("[x] " + message);
        }
    }

    public static void trace(String message, Object... args) { log(TRACE, message, args); }
    public static void debug(String message, Object... args) { log(DEBUG, message, args); }
    public static void info( String message, Object... args) { log(INFO,  message, args); }
    public static void warn( String message, Object... args) { log(WARN,  message, args); }
    public static void error(String message, Object... args) { log(ERROR, message, args); }

    /** Format an object for logging: strings quoted, arrays expanded, length capped. */
    public static String formatArg(Object o) {
        if (o == null) return "null";
        if (o instanceof Object[] arr) return Arrays.toString(arr);
        String s = o.toString();
        if (s.length() > MAX_ARG_STRING_LENGTH) s = s.substring(0, MAX_ARG_STRING_LENGTH - 3) + "...";
        if (o instanceof String) return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
        return s;
    }

    /** Format an array of arguments for logging (each via {@link #formatArg}, joined by ", "). */
    public static String formatArgs(Object[] args) {
        return formatArgs(args, 0);
    }

    /** Format arguments from {@code fromIndex} to end (no array copy). */
    public static String formatArgs(Object[] args, int fromIndex) {
        if (args == null || fromIndex >= args.length) return "";
        StringBuilder sb = new StringBuilder();
        for (int i = fromIndex; i < args.length; i++) {
            if (i > fromIndex) sb.append(", ");
            sb.append(formatArg(args[i]));
        }
        return sb.toString();
    }
}
