package me.zed_0xff.zombie_buddy;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public record ModFlags(int value) {
    public static final int MF_NONE = 0;

    public static final int MF_VALID        = 1 << 0;
    public static final int MF_SIGNED       = 1 << 1;
    public static final int MF_ACTIVE       = 1 << 2;
    public static final int MF_PERSIST      = 1 << 3;
    public static final int MF_BANNED       = 1 << 4;
    public static final int MF_PRELOAD      = 1 << 5;
    public static final int MF_TRUST_AUTHOR = 1 << 6;

    private static final List<Integer> STICKY_FLAGS = List.of(MF_ACTIVE, MF_BANNED, MF_PRELOAD);

    public static final ModFlags EMPTY = new ModFlags(0);

    public boolean has(int flag) {
        return (value & flag) != 0;
    }

    public boolean hasAll(int... flags) {
        for (int flag : flags) {
            if ((value & flag) == 0) return false;
        }
        return true;
    }

    public ModFlags getSticky() {
        int newValue = 0;
        for (int flag : STICKY_FLAGS) {
            if ((value & flag) != 0) {
                newValue |= flag;
            }
        }
        return new ModFlags(newValue);
    }

    public ModFlags merge(ModFlags other) {
        return new ModFlags(this.value | other.value);
    }

    public ModFlags with(int flag) {
        return new ModFlags(value | flag);
    }

    public ModFlags without(int flag) {
        return new ModFlags(value & ~flag);
    }

    public Map<String, Boolean> toMap() {
        Map<String, Boolean> map = new HashMap<>();
        map.put("valid", has(MF_VALID));
        map.put("signed", has(MF_SIGNED));
        map.put("active", has(MF_ACTIVE));
        map.put("persist", has(MF_PERSIST));
        map.put("banned", has(MF_BANNED));
        map.put("preload", has(MF_PRELOAD));
        map.put("trustAuthor", has(MF_TRUST_AUTHOR));
        return map;
    }
}
