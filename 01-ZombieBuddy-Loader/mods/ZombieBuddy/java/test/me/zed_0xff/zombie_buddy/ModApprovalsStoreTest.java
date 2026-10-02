package me.zed_0xff.zombie_buddy;

import static me.zed_0xff.zombie_buddy.SteamWorkshop.SteamID64;
import static me.zed_0xff.zombie_buddy.SteamWorkshop.WorkshopItemID;
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

class ModApprovalsStoreTest {

    @Test
    void parseFixture_loadsAllFields() throws IOException {
        String json = loadFixture("mod_approvals_sample.json");
        ModApprovalsStore.FileData data = ZBGson.PRETTY.fromJson(json, ModApprovalsStore.FileData.class);

        assertEquals(2, data.formatVersion);
        assertEquals(3, data.mods.size());

        // Check first mod
        ModApprovalsStore.ModEntry mod1 = data.mods.get(0);
        assertEquals("TestMod1", mod1.id);
        assertEquals(3709229404L, mod1.workshopId.value());
        assertEquals("c180d888eac78369a58dd266e98095ca7e86e16533294ee43ec750e729827064", mod1.jarHash);
        assertTrue(mod1.decision);
        assertEquals("2026-04-01T12:34:56Z", mod1.time);
        assertEquals(76561198043849998L, mod1.authorId.value());

        // Check second mod
        ModApprovalsStore.ModEntry mod2 = data.mods.get(1);
        assertEquals("TestMod2", mod2.id);
        assertFalse(mod2.decision);

        // Check third mod (no workshop_id, no author_id)
        ModApprovalsStore.ModEntry mod3 = data.mods.get(2);
        assertEquals("LocalMod", mod3.id);
        assertNull(mod3.workshopId);
        assertNull(mod3.authorId);
        assertTrue(mod3.decision);
    }

    @Test
    void roundTrip_preservesData() {
        ModApprovalsStore.FileData original = new ModApprovalsStore.FileData();

        ModApprovalsStore.ModEntry mod = new ModApprovalsStore.ModEntry(
            "RoundTripMod",
            new WorkshopItemID(9876543210L),
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            true,
            "2026-04-24T15:30:00Z",
            new SteamID64(76561198099999999L)
        );
        original.mods.add(mod);

        String json = ZBGson.PRETTY.toJson(original);
        ModApprovalsStore.FileData parsed = ZBGson.PRETTY.fromJson(json, ModApprovalsStore.FileData.class);

        assertEquals(original.formatVersion, parsed.formatVersion);
        assertEquals(original.mods.size(), parsed.mods.size());

        ModApprovalsStore.ModEntry parsedMod = parsed.mods.get(0);
        assertEquals(mod.id, parsedMod.id);
        assertEquals(mod.workshopId.value(), parsedMod.workshopId.value());
        assertEquals(mod.jarHash, parsedMod.jarHash);
        assertEquals(mod.decision, parsedMod.decision);
        assertEquals(mod.time, parsedMod.time);
        assertEquals(mod.authorId.value(), parsedMod.authorId.value());
    }

    @Test
    void serialize_writesNumbersNotStrings() {
        ModApprovalsStore.FileData data = new ModApprovalsStore.FileData();
        data.mods.add(new ModApprovalsStore.ModEntry(
            "NumericTest",
            new WorkshopItemID(1234567890L),
            "hash",
            true,
            null,
            new SteamID64(76561198000000000L)
        ));

        String json = ZBGson.PRETTY.toJson(data);

        // workshop_id should be a number, not a quoted string
        assertTrue(json.contains("\"workshop_id\": 1234567890"),
            "workshop_id should be numeric: " + json);
        assertFalse(json.contains("\"workshop_id\": \"1234567890\""),
            "workshop_id should not be a string: " + json);

        // author_id in mods should be a number
        assertTrue(json.contains("\"author_id\": 76561198000000000"),
            "author_id should be numeric: " + json);
    }

    @Test
    void nullFields_handledGracefully() {
        ModApprovalsStore.FileData data = new ModApprovalsStore.FileData();
        data.mods.add(new ModApprovalsStore.ModEntry(
            "NullFieldsMod",
            null,  // no workshop_id
            "somehash",
            false,
            null,  // no time
            null   // no author_id
        ));

        String json = ZBGson.PRETTY.toJson(data);
        ModApprovalsStore.FileData parsed = ZBGson.PRETTY.fromJson(json, ModApprovalsStore.FileData.class);

        assertEquals(1, parsed.mods.size());
        ModApprovalsStore.ModEntry mod = parsed.mods.get(0);
        assertEquals("NullFieldsMod", mod.id);
        assertNull(mod.workshopId);
        assertNull(mod.authorId);
        assertNull(mod.time);
    }

    private static String loadFixture(String name) throws IOException {
        try (InputStream is = ModApprovalsStoreTest.class.getResourceAsStream("/fixtures/" + name)) {
            if (is == null) {
                // Try alternate path for gradle test runner
                Path p = Path.of("test/fixtures", name);
                if (Files.exists(p)) {
                    return Files.readString(p, StandardCharsets.UTF_8);
                }
                throw new IOException("Fixture not found: " + name);
            }
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
