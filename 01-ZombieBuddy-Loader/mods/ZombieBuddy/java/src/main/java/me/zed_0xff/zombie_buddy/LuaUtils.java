package me.zed_0xff.zombie_buddy;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import se.krka.kahlua.vm.KahluaTable;
import zombie.Lua.LuaManager;

public final class LuaUtils {
    private LuaUtils() {}

    /**
     * If {@code obj} is a kahlua-exposed Java invoker (MultiLuaJavaInvoker / LuaJavaInvoker),
     * fills {@code out.invokers} with per-overload metadata.
     */
    public static void addInvokersInfo(KahluaTable out, Object obj) {
        if (out == null || obj == null) return;
        try {
            Class<?> c = obj.getClass();
            List<?> list;
            if ("se.krka.kahlua.integration.expose.MultiLuaJavaInvoker".equals(c.getName())) {
                Object invokers = c.getMethod("getInvokers").invoke(obj);
                list = (invokers instanceof List<?> l && !l.isEmpty()) ? l : null;
            } else if ("se.krka.kahlua.integration.expose.LuaJavaInvoker".equals(c.getName())) {
                list = Collections.singletonList(obj);
            } else {
                list = null;
            }
            if (Utils.isBlank(list)) return;

            Class<?> invokerClass = list.get(0).getClass();
            if (!"se.krka.kahlua.integration.expose.LuaJavaInvoker".equals(invokerClass.getName())) return;

            Field clazzField = invokerClass.getDeclaredField("clazz");
            clazzField.setAccessible(true);
            Field nameField = invokerClass.getDeclaredField("name");
            nameField.setAccessible(true);
            Field callerField = invokerClass.getDeclaredField("caller");
            callerField.setAccessible(true);

            var invokersTbl = LuaManager.platform.newTable();
            for (int i = 0; i < list.size(); i++) {
                Object inv = list.get(i);
                var invTbl = LuaManager.platform.newTable();
                Class<?> targetClass = (Class<?>) clazzField.get(inv);
                String methodName = (String) nameField.get(inv);
                Object caller = callerField.get(inv);
                invTbl.rawset("targetClass", targetClass.getName());
                invTbl.rawset("targetSimpleClass", targetClass.getSimpleName());
                invTbl.rawset("methodName", methodName);
                if (caller != null && "se.krka.kahlua.integration.expose.caller.MethodCaller".equals(caller.getClass().getName())) {
                    Field methodField = caller.getClass().getDeclaredField("method");
                    methodField.setAccessible(true);
                    Method m = (Method) methodField.get(caller);
                    invTbl.rawset("declaringClass", m.getDeclaringClass().getName());
                }
                Object debugData = invokerClass.getMethod("getMethodDebugData").invoke(inv);
                invTbl.rawset("methodDebugData", debugData != null ? debugData.toString() : "");
                invokersTbl.rawset(Double.valueOf(i + 1), invTbl);
            }
            out.rawset("invokers", invokersTbl);
        } catch (Exception e) {
            out.rawset("unwrapError", e.getMessage());
        }
    }

    static KahluaTable mapToLuaTable(Map<?, ?> map) {
        if (map == null) return null;

        var tbl = LuaManager.platform.newTable();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            Object key = entry.getKey();
            Object value = entry.getValue();
            if (key != null) {
                tbl.rawset(key.toString(), value);
            }
        }
        return tbl;
    }
}
