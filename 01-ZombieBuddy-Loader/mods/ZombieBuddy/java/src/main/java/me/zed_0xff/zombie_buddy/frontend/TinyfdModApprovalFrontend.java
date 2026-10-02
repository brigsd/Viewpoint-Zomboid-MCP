package me.zed_0xff.zombie_buddy.frontend;

import me.zed_0xff.zombie_buddy.*;

import zombie.core.Core;
import zombie.core.GameVersion;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * LWJGL {@code TinyFileDialogs} (works when the game JVM is {@code java.awt.headless=true}).
 * No multi-mod window: {@link #approvePendingMods} prompts one entry at a time.
 */
public final class TinyfdModApprovalFrontend implements ModApprovalFrontend {

    private static final String DIALOG_TITLE = "ZombieBuddy Java mod approval";
    private static final String DATE_FORMAT = "yyyy-MM-dd";

    @Override
    public List<JarBatchApprovalProtocol.Entry> approvePendingMods(List<JarBatchApprovalProtocol.Entry> pending) {
        if (pending.isEmpty()) {
            return pending;
        }
        for (JarBatchApprovalProtocol.Entry e : pending) {
            Boolean allow = promptForEntry(e);
            if (allow != null) {
                e.decision = allow;
            }
        }
        return pending;
    }

    private static Boolean promptForEntry(JarBatchApprovalProtocol.Entry e) {
        if (e.zbs.invalid()) {
            String note = !Utils.isBlank(e.zbs.notice())
                ? e.zbs.notice()
                : "Invalid ZBS — load will be denied.";
            tinyfdYesNo(
                "ZBS invalid — this Java mod cannot be loaded.\n\n"
                    + note
                    + "\n\nIt will be denied."
            );
            return false;
        }

        String modified = formatDate(e.date);
        String zbsLine = "";
        if (e.zbs.valid() || e.zbs.invalid() || e.zbs.unsigned()) {
            String sid = e.zbs.authorSteamId() != null ? e.zbs.authorSteamId().toString() : "";
            zbsLine = "ZBS: " + zbsStatus(e)
                + (!sid.isEmpty() ? " (Steam: " + sid + ")" : "")
                + "\n\n";
        }
        Boolean allow = tinyfdYesNo(
            "Allow Java mod to load?\n\n"
                + zbsLine
                + "Mod: " + e.modId + "\n\n"
                + "JAR: " + e.jarAbsolutePath + "\n\n"
                + "Modified: " + modified + "\n\n"
                + "SHA-256: " + e.sha256 + "\n\n"
                + "Only allow if you trust this mod source."
        );
        if (allow == null) {
            return false;
        }
        return allow;
    }

    private static String zbsStatus(JarBatchApprovalProtocol.Entry e) {
        if (e.zbs.valid()) {
            return "valid";
        }
        if (e.zbs.invalid()) {
            return "invalid";
        }
        return "unsigned";
    }

    private static String formatDate(Date date) {
        if (date == null) {
            return "<unknown>";
        }
        return new SimpleDateFormat(DATE_FORMAT, Locale.ROOT).format(date);
    }

    /**
     * Returns TRUE (Yes), FALSE (No), or null if the dialog could not be shown.
     */
    private static Boolean tinyfdYesNo(String msg) {
        Class<?> dialogClass = Accessor.findClass("org.lwjgl.util.tinyfd.TinyFileDialogs");
        if (dialogClass == null) {
            if (Core.getInstance().getGameVersion().isGreaterThan(GameVersion.parse("42.14"))) {
                Logger.error("tinyfdYesNo(): game version > 42.14 but TinyFileDialogs missing; returning null");
                return null;
            }
            Logger.info("tinyfdYesNo(): pre-42.15 and TinyFileDialogs missing; defaulting YES");
            return Boolean.TRUE;
        }
        try {
            Object result = Accessor.callByName(
                dialogClass,
                "tinyfd_messageBox",
                DIALOG_TITLE,
                msg,
                "yesno",
                "warning",
                false
            );
            return Boolean.TRUE.equals(result);
        } catch (Throwable t) {
            Logger.error("Could not show dialog: " + t);
            return null;
        }
    }
}
