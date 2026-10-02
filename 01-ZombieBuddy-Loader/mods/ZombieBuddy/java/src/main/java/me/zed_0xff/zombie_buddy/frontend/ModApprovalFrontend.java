package me.zed_0xff.zombie_buddy.frontend;

import java.util.List;

import me.zed_0xff.zombie_buddy.JarBatchApprovalProtocol;

/**
 * UI for Java mod approvals. Implementations present {@code pending} to the user and return
 * the decided entries (may be the same list mutated in-place or a new list). Never returns null.
 */
public interface ModApprovalFrontend {

    /**
     * Collect approval decisions for every entry in {@code pending} and return the decided list.
     * Empty {@code pending} must return an empty list.
     */
    List<JarBatchApprovalProtocol.Entry> approvePendingMods(List<JarBatchApprovalProtocol.Entry> pending);
}
