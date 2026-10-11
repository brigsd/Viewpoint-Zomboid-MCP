"""Testes do extrator Java (extract_java.py) com um jar de fixture compilado na hora.

Precisa de `javac` e `javap` (JDK). Sem eles os testes de integração são pulados.
Nenhuma classe do jogo é usada: o fixture imita o mecanismo do PZ
(`zombie.Lua.LuaManager$Exposer.exposeAll`, `@HiddenFromLua`, `@LuaMethod`).
"""
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import extract_java as ej  # noqa: E402

SOURCES = {
    "zombie/HiddenFromLua.java": """
package zombie;
import java.lang.annotation.*;
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.FIELD})
public @interface HiddenFromLua {}
""",
    "se/krka/kahlua/integration/annotations/LuaMethod.java": """
package se.krka.kahlua.integration.annotations;
import java.lang.annotation.*;
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface LuaMethod { String name() default ""; boolean global() default false; }
""",
    "zombie/core/Core.java": """
package zombie.core;
public class Core { public static boolean debug; }
""",
    "fix/Barker.java": """
package fix;
public interface Barker { default String bark() { return "woof"; } int LOUD = 11; }
""",
    "fix/Animal.java": """
package fix;
import java.util.ArrayList;
public class Animal {
    public static final int MAX = 5;
    public static final String NAME = "animal";
    public static int counter;
    public int instanceField;
    @zombie.HiddenFromLua public static int hiddenStatic;
    public Animal() {}
    public Animal(String name, int age) {}
    public String getName() { return null; }
    public static Animal make(String n) { return null; }
    @zombie.HiddenFromLua public void secret() {}
    public ArrayList<String> tags(String... more) { return null; }
    protected void prot() {}
    private void priv() {}
}
""",
    "fix/Dog.java": """
package fix;
public class Dog extends Animal implements Barker {
    public String fetch(Animal other, long x, double[] ys) { return null; }
}
""",
    "fix/Shape.java": """
package fix;
public abstract class Shape { public Shape() {} public abstract float area(); }
""",
    "fix/other/Animal.java": """
package fix.other;
public class Animal { public void speak() {} }
""",
    "fix/NotExposed.java": """
package fix;
public class NotExposed { public void nope() {} }
""",
    "fix/DebugOnly.java": """
package fix;
public class DebugOnly { public void dbg() {} }
""",
    "fix/helper/Extra.java": """
package fix.helper;
public class Extra { public static final long BIG = 1L << 40; public void extra() {} }
""",
    "fix/helper/Helper.java": """
package fix.helper;
import zombie.Lua.LuaManager;
public class Helper {
    public static void setExposed(LuaManager.Exposer e) {
        e.setExposed(Extra.class);
    }
}
""",
    "fix/Keys.java": """
package fix;
public class Keys {
    public static final int KEY_A = 30;
    public static final int KEY_LWIN = 91;
    public static final int KEY_LEFTWIN = 92;
    public static final int OTHER = 1;
}
""",
    "zombie/Lua/LuaManager.java": """
package zombie.Lua;
import se.krka.kahlua.integration.annotations.LuaMethod;
public class LuaManager {
    public static void exposeKeyboardKeys() { Class<?> c = fix.Keys.class; }
    public static class Exposer {
        public void setExposed(Class<?> c) {}
        public void exposeGlobalFunctions(Object o) {}
        public void exposeAll() {
            setExposed(fix.Animal.class);
            setExposed(fix.Dog.class);
            setExposed(fix.Shape.class);
            setExposed(fix.other.Animal.class);
            if (zombie.core.Core.debug) {
                setExposed(fix.DebugOnly.class);
            }
            fix.helper.Helper.setExposed(this);
            exposeGlobalFunctions(new GlobalObject());
            LuaManager.exposeKeyboardKeys();
        }
    }
    public static class GlobalObject {
        @LuaMethod(name = "getAnimal", global = true)
        public static fix.Animal getAnimalJava(String n) { return null; }
        @LuaMethod(global = true)
        public static boolean isReady() { return true; }
        @LuaMethod(name = "getText", global = true)
        public static String getText(String k, Object... args) { return k; }
        @LuaMethod(name = "getText", global = true)
        public static String getText(String k) { return k; }
        @LuaMethod(name = "notGlobal")
        public static void ng() {}
        public static void plain() {}
    }
}
""",
}


def _build_fixture_jar(workdir: Path) -> Path:
    javac = ej.find_tool("javac")
    src_root = workdir / "src"
    out_root = workdir / "classes"
    out_root.mkdir(parents=True)
    files = []
    for rel, text in SOURCES.items():
        p = src_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        files.append(str(p))
    subprocess.run([javac, "-g", "-d", str(out_root)] + files, check=True,
                   capture_output=True, text=True)
    game_dir = workdir / "game"
    game_dir.mkdir()
    jar = game_dir / ej.JAR_NAME
    with zipfile.ZipFile(jar, "w") as z:
        for f in out_root.rglob("*.class"):
            z.write(f, f.relative_to(out_root).as_posix())
    return game_dir


class TypeRenderingTests(unittest.TestCase):
    def test_descriptor(self):
        params, ret = ej.parse_method_types("(Ljava/lang/String;I[J)Lzombie/scripting/objects/CraftRecipe;")
        self.assertEqual(params, ["String", "int", "long[]"])
        self.assertEqual(ret, "CraftRecipe")

    def test_generic_signature(self):
        params, ret = ej.parse_method_types(
            "<T:Ljava/lang/Object;>(Ljava/util/ArrayList<Lzombie/X;>;Ljava/util/Map<TT;+Ljava/lang/Number;>;)"
            "Ljava/util/List<*>;")
        self.assertEqual(params, ["ArrayList<X>", "Map<T, ? extends Number>"])
        self.assertEqual(ret, "List<?>")

    def test_inner_class(self):
        params, ret = ej.parse_method_types("(Lzombie/A$B;)Lzombie/A<TT;>.C;")
        self.assertEqual(params, ["B"])
        self.assertEqual(ret, "C")


@unittest.skipUnless(ej.find_tool("javac") and ej.find_tool("javap"), "JDK (javac/javap) não encontrado")
class FixtureExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="pz_api_test_"))
        cls.game_dir = _build_fixture_jar(cls.tmp)
        cls.cache = cls.tmp / "cache"
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.executescript(ej.SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.counts = ej.extract(cls.conn, cls.game_dir, use_cache=False, cache_dir=cls.cache)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def rows(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def test_exposed_classes_found(self):
        names = {r[0] for r in self.rows("SELECT java_class FROM symbols WHERE kind='class'")}
        self.assertIn("fix.Animal", names)
        self.assertIn("fix.Dog", names)
        self.assertIn("fix.helper.Extra", names)  # via helper estático
        self.assertNotIn("fix.NotExposed", names)
        self.assertNotIn("fix.DebugOnly", names)  # só em Core.debug

    def test_all_rows_are_java_origin(self):
        self.assertEqual(self.rows("SELECT DISTINCT origin FROM symbols"), [("java",)])

    def test_name_collision_keeps_both_classes_apart(self):
        rows = dict(self.rows("SELECT java_class, name FROM symbols WHERE kind='class' AND name LIKE '%Animal'"))
        self.assertEqual(rows["fix.Animal"], "Animal")
        self.assertEqual(rows["fix.other.Animal"], "fix.other.Animal")  # a segunda vira o FQN
        # os métodos de cada uma não se misturam
        speak = self.rows("SELECT owner, java_class FROM symbols WHERE name='speak'")
        self.assertEqual(speak, [("fix.other.Animal", "fix.other.Animal")])

    def test_methods_and_signatures(self):
        sig = self.rows("SELECT signature, returns, is_static FROM symbols WHERE kind='method' AND owner='Animal' AND name='tags'")
        self.assertEqual(sig, [("ArrayList<String> tags(String...)", "ArrayList<String>", 0)])
        make = self.rows("SELECT signature, is_static FROM symbols WHERE owner='Animal' AND name='make'")
        self.assertEqual(make, [("Animal make(String)", 1)])

    def test_hidden_protected_private_excluded(self):
        names = {r[0] for r in self.rows("SELECT name FROM symbols WHERE owner='Animal'")}
        self.assertNotIn("secret", names)
        self.assertNotIn("prot", names)
        self.assertNotIn("priv", names)
        self.assertNotIn("hiddenStatic", names)
        self.assertNotIn("instanceField", names)  # campo de instância não vira constante

    def test_constructors_become_new(self):
        sigs = {r[0] for r in self.rows("SELECT signature FROM symbols WHERE owner='Animal' AND name='new'")}
        self.assertEqual(sigs, {"Animal new()", "Animal new(String, int)"})
        self.assertEqual(self.rows("SELECT * FROM symbols WHERE owner='Shape' AND name='new'"), [])  # abstrata
        self.assertTrue(all(r[0] == 1 for r in self.rows("SELECT is_static FROM symbols WHERE name='new'")))

    def test_inherited_members(self):
        inh = self.rows("SELECT file FROM symbols WHERE owner='Dog' AND name='getName'")
        self.assertEqual(inh, [("fix.Animal",)])
        bark = self.rows("SELECT file FROM symbols WHERE owner='Dog' AND name='bark'")
        self.assertEqual(bark, [("fix.Barker",)])
        own = self.rows("SELECT file, signature FROM symbols WHERE owner='Dog' AND name='fetch'")
        self.assertEqual(own, [(None, "String fetch(Animal, long, double[])")])
        self.assertEqual(self.rows("SELECT 1 FROM symbols WHERE owner='Dog' AND name IN ('equals','hashCode','wait')"), [])

    def test_static_fields_with_constants(self):
        f = dict((r[0], r[1]) for r in self.rows("SELECT name, signature FROM symbols WHERE kind='field' AND owner='Animal'"))
        self.assertEqual(f["MAX"], "int MAX = 5")
        self.assertEqual(f["NAME"], 'String NAME = "animal"')
        self.assertEqual(f["counter"], "int counter")
        dog = {r[0]: r[1] for r in self.rows("SELECT name, file FROM symbols WHERE kind='field' AND owner='Dog'")}
        self.assertEqual(dog["LOUD"], "fix.Barker")  # constante herdada de interface
        self.assertEqual(self.rows("SELECT signature FROM symbols WHERE name='BIG'"), [("long BIG = 1099511627776",)])

    def test_global_functions_use_lua_name(self):
        g = {r[0] for r in self.rows("SELECT name FROM symbols WHERE kind='global_function'")}
        self.assertEqual(g, {"getAnimal", "isReady", "getText"})  # sem notGlobal/plain
        self.assertEqual(self.rows("SELECT signature, returns FROM symbols WHERE name='getAnimal'"),
                         [("Animal getAnimal(String)", "Animal")])
        self.assertEqual(self.rows("SELECT is_static FROM symbols WHERE name='isReady'"), [(0,)])
        texts = {r[0] for r in self.rows("SELECT signature FROM symbols WHERE name='getText'")}
        self.assertEqual(texts, {"String getText(String, Object...)", "String getText(String)"})

    def test_special_keyboard_constants(self):
        k = {r[0] for r in self.rows("SELECT name FROM symbols WHERE kind='field' AND owner='Keyboard'")}
        self.assertIn("KEY_A", k)
        self.assertNotIn("KEY_LWIN", k)   # termina em WIN: filtrado como no jogo
        self.assertNotIn("OTHER", k)

    def test_counts_and_rerun_and_cache(self):
        for key in ("classes", "methods", "fields", "global_functions"):
            self.assertGreater(self.counts[key], 0, key)
        total = self.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        again = ej.extract(self.conn, self.game_dir, use_cache=True, cache_dir=self.cache)  # grava cache
        again2 = ej.extract(self.conn, self.game_dir, use_cache=True, cache_dir=self.cache)  # lê cache
        self.assertEqual(again, again2)
        self.assertEqual(again, self.counts)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0], total)  # idempotente


if __name__ == "__main__":
    unittest.main()
