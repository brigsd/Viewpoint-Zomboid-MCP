package pzlab;

import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import me.zed_0xff.zombie_buddy.Agent;
import me.zed_0xff.zombie_buddy.Logger;
import me.zed_0xff.zombie_buddy.patches.experimental.HttpServer;

/**
 * Agente auxiliar do PZ-Lab (carregado via patches_jar=pzlab-agent.jar:pzlab).
 *
 * Por que existe: o PreMain experimental do ZombieBuddy (v2.3.x) chama JavaStateDumper.init(),
 * que registra o sinal "INFO" (inexistente no Windows) e lanca IllegalArgumentException ANTES de
 * subir o servidor HTTP. Aqui reproduzimos so a parte util:
 *   1) sobe o HttpServer do ZombieBuddy (/status, /lua, /log, /version);
 *   2) corrige o endpoint /log: o original le <cachedir>/console.txt (inexistente no servidor
 *      dedicado, resulta em HTTP 500); aqui ele devolve o fim do log capturado pelo pzlab
 *      (-Dpzlab.log=...), aceitando ?lines=N (padrao 100);
 *   3) cria uma "caixa de entrada" de comandos do console do servidor: o pzlab.py escreve linhas
 *      em lab_cmd.txt (dentro do cachedir) e este agente as injeta na fila de comandos do
 *      GameServer (equivalente a digitar no console). Usado pelo `stop` gracioso ("quit").
 */
public class PreMain {
    public static void premain(String[] args) {
        startHttp();
        fixLogEndpoint();
        startInbox();
    }

    private static void startHttp() {
        String host = Agent.arguments.get("lua_server_host");
        String port = Agent.arguments.get("lua_server_port");
        String timeout = Agent.arguments.get("lua_task_timeout");
        if (port == null || port.isBlank()) {
            Logger.info("[pzlab] lua_server_port ausente; HTTP nao sera iniciado");
            return;
        }
        try {
            if (timeout != null && !timeout.isBlank()) {
                HttpServer.luaTaskTimeoutMs = Long.parseLong(timeout.trim());
            }
            HttpServer s = new HttpServer(host == null || host.isBlank() ? "127.0.0.1" : host,
                    Integer.parseInt(port.trim()), false);
            s.start();
        } catch (Throwable t) {
            Logger.error("[pzlab] falha ao iniciar HTTP: " + t);
        }
    }

    private static void fixLogEndpoint() {
        final String logProp = System.getProperty("pzlab.log");
        HttpServer inst = HttpServer.getInstance();
        if (logProp == null || logProp.isBlank() || inst == null) {
            return;
        }
        try {
            Field f = HttpServer.class.getDeclaredField("server");
            f.setAccessible(true);
            com.sun.net.httpserver.HttpServer raw = (com.sun.net.httpserver.HttpServer) f.get(inst);
            raw.removeContext("/log");
            raw.createContext("/log", ex -> {
                try {
                    int lines = HttpServer.parseIntParam(ex.getRequestURI().getQuery(), "lines", 100);
                    String body = tail(Path.of(logProp), Math.max(1, lines));
                    HttpServer.sendResponse(ex, 200, body);
                } catch (Throwable e) {
                    HttpServer.sendResponse(ex, 500, "Error reading log: " + e + "\n");
                }
            });
        } catch (Throwable t) {
            Logger.error("[pzlab] falha ao substituir /log: " + t);
        }
    }

    private static String tail(Path p, int lines) throws java.io.IOException {
        try (java.io.RandomAccessFile raf = new java.io.RandomAccessFile(p.toFile(), "r")) {
            long len = raf.length();
            long start = Math.max(0, len - 2_000_000L);
            raf.seek(start);
            byte[] buf = new byte[(int) (len - start)];
            raf.readFully(buf);
            String[] all = new String(buf, StandardCharsets.UTF_8).split("\r?\n");
            int from = Math.max(0, all.length - lines);
            return String.join("\n", java.util.Arrays.copyOfRange(all, from, all.length)) + "\n";
        }
    }

    @SuppressWarnings("unchecked")
    private static void startInbox() {
        final String cacheProp = System.getProperty("pzlab.inbox");
        if (cacheProp == null || cacheProp.isBlank()) {
            return;
        }
        final Path inbox = Path.of(cacheProp);
        Thread t = new Thread(() -> {
            ArrayList<String> queue = null;
            while (true) {
                try {
                    Thread.sleep(300);
                    if (!Files.isRegularFile(inbox)) continue;
                    if (queue == null) {
                        Class<?> gs = Class.forName("zombie.network.GameServer");
                        Field f = gs.getDeclaredField("consoleCommands");
                        f.setAccessible(true);
                        queue = (ArrayList<String>) f.get(null);
                    }
                    if (queue == null) continue;
                    List<String> lines = Files.readAllLines(inbox, StandardCharsets.UTF_8);
                    Files.deleteIfExists(inbox);
                    for (String line : lines) {
                        line = line.trim();
                        if (line.isEmpty()) continue;
                        Logger.info("[pzlab] console> " + line);
                        synchronized (queue) {
                            queue.add(line);
                        }
                    }
                } catch (InterruptedException e) {
                    return;
                } catch (Throwable e) {
                    // GameServer ainda nao carregado ou arquivo em escrita: tenta de novo.
                    queue = null;
                }
            }
        }, "pzlab-inbox");
        t.setDaemon(true);
        t.start();
    }
}
