# lab/ - Launcher do servidor headless (pzlab)

Sobe um **servidor dedicado de Project Zomboid (Build 42.21)** em background, com **ZombieBuddy**
injetado e o servidor HTTP experimental dele ligado, para que o Claude (ou voce) rode Lua dentro do
servidor e teste mods **sem abrir o jogo**.

Nada e escrito na pasta de instalacao do jogo nem em `C:\Users\<voce>\Zomboid\`. Tudo vive em
`06-PZ-Lab-Headless/runtime/` (usado como `-cachedir`).

## Uso rapido

```powershell
python lab\pzlab.py start                 # sobe com todos os mods de ..\mods (primeiro boot ~50 s)
python lab\pzlab.py start --mods ZBLabTest,OutroMod --timeout 300
python lab\pzlab.py status
python lab\pzlab.py lua "return getCore():getVersion()"
python lab\pzlab.py log --lines 40
python lab\pzlab.py restart               # stop + start (recarrega os mods)
python lab\pzlab.py stop                  # 'quit' gracioso (salva o mundo), depois mata a arvore se preciso
```

Todos os comandos imprimem JSON. Como modulo Python:

```python
import pzlab
pzlab.start(mods=None, timeout_s=300)   # {"pid","host","port","cachedir","log_file","started_at","mods", "boot_s"}
pzlab.lua("return isServer()")          # {"http":200,"ok":True,"result":True,"raw":"true"}
pzlab.console("players")                # injeta comando no console do servidor (saida vai pro log)
pzlab.tail_log(50)                      # ultimas linhas do log do servidor
pzlab.stop(); pzlab.restart(); pzlab.status(); pzlab.log_path(); pzlab.http_base()
```

## Arquivos

| Arquivo | Funcao |
|---|---|
| `pzlab.py` | modulo + CLI |
| `lab.json` | defaults sem segredo (porta, memoria, ini do servidor, sandbox) - versionado |
| `lab.local.json` | **gitignored**; contem `admin_password` gerada na primeira execucao (nunca impressa) |
| `agent/pzlab/PreMain.java` | agente auxiliar Java, compilado sob demanda para `runtime/pzlab-agent.jar` (precisa de um JDK/`javac`) |
| `../runtime/` | cachedir do PZ: `Server/pzlab.ini`, `Saves/`, `mods/` (junctions), `zombie_buddy/`, `lab_logs/`, `lab_state.json` |

## O que o `start` faz

1. Le config (defaults + `lab.json` + `lab.local.json`) e gera a senha admin se faltar.
2. Cria junctions (`mklink /J`, sem admin; copia se falhar) de cada `mods/<Pasta>` para `runtime/mods/<Pasta>`.
   O ID habilitado vem do `id=` do `mod.info` (`42/mod.info`, `common/mod.info` ou `mod.info`); `--mods` aceita pasta ou ID.
3. Ajusta `runtime/Server/pzlab.ini` (`Mods=`, portas, `PauseEmpty=false`, `DoLuaChecksum=false`, ...) e o
   `pzlab_SandboxVars.lua` (`Zombies=6` = sem zumbis, mundo barato).
4. Lanca `jre64\bin\java.exe` direto (cwd = pasta do jogo), **destacado** (`DETACHED_PROCESS`), stdout/stderr em
   `runtime/lab_logs/server-<timestamp>.log` (+ `latest.log`, hardlink ao vivo para o log atual):

   ```
   java ... -Dpzlab.inbox=... -Dpzlab.log=... -agentlib:zbNative=experimental,lua_server_host=127.0.0.1,
        lua_server_port=8642,lua_task_timeout=30000,policy=deny-new,frontend=console,verbosity=0,
        config_dir=<runtime>\zombie_buddy,patches_jar=<rel>\pzlab-agent.jar:pzlab
        -cp ./;projectzomboid.jar zombie.network.GameServer -nosteam -cachedir=<runtime>
        -servername pzlab -adminusername admin -adminpassword <oculta> -port 16261 -udpport 16262
   ```
   `policy=deny-new` + `frontend=console`: ZombieBuddy nunca abre dialogo nem le stdin (jars Java de mods nao
   aprovados sao ignorados silenciosamente). Aprovacoes ficam em `runtime/zombie_buddy/` (nao em `~/.zombie_buddy`).
5. Espera: processo vivo -> `GET /status` = `ok` -> marcador `*** SERVER STARTED ****` no log -> `POST /lua`
   `return 1` responde (o tick do servidor esta rodando). Em timeout/queda, mata o processo e levanta erro com o fim do log.

## API HTTP do ZombieBuddy (127.0.0.1:8642)

| Endpoint | Requisicao | Resposta |
|---|---|---|
| `GET /status` | - | `200 text/plain`, corpo `ok\n`. Responde assim que o agente sobe (antes do mundo carregar!). |
| `GET /version` | - | `200 text/plain`, ex.: `ZombieBuddy v2.3.2\n` |
| `POST /lua` | corpo = **codigo Lua cru** (`Content-Type: text/plain`, UTF-8). Query opcional: `depth=N` (niveis de tabela serializados, padrao 1), `chunkname=nome`, `sandbox=true\|false` (padrao `true`), `thread=true\|false` | ver abaixo |
| `GET /log?lines=N` | N padrao 100 | `200 text/plain`: ultimas N linhas do log do servidor (**endpoint corrigido pelo nosso agente**) |

**`/lua`** executa o chunk na thread Lua do servidor (fila consumida em `ServerMap.preupdate`, ~a cada 100 ms; o
tempo maximo de espera e `lua_task_timeout`, 30 s aqui). O **primeiro valor do `return`** volta serializado em JSON
(valores adicionais sao descartados; sem `return` -> `null`). `print()` vai para o log, nao para a resposta.

* Sucesso: `200 application/json`. Ex.: `return getCore():getVersion()` -> `"42.21.0 4a0e9546ec"`;
  `return {a=1,b={2,3}}` com `?depth=3` -> `{"a":1,"b":[2,3]}`; objetos Java viram descricao/tabela conforme a profundidade.
* Erro Lua: `500 application/json`
  `{"err_code":1,"luaReturn":{"errorString":"...","luaStackTrace":"at http_exec:1\n","errorObject":"...","javaException":{className,message,stackTrace[]}},"kahluaErrors":["..."]}`
* `err_code` 2 = excecao Java ao executar; 3 = timeout/erro ao enfileirar (`{"err_code":3,"javaException":{...}}`).
* Corpo vazio -> `400`; metodo diferente de POST -> `405`.
* `sandbox=true` (padrao): o chunk roda numa tabela de ambiente nova com `__index = _G`; globais que ele **atribui nao
  vazam** para o jogo. Use `sandbox=false` para definir globais persistentes (ex.: carregar funcoes de teste).
* Varios chunks no mesmo corpo: separe com linhas `---FILE:nome.lua---` (o ultimo chunk e o que retorna valor).
* Cabecalho opcional `X-ZombieBuddy-Error-Globals: a,b` inclui os globais `a`,`b` em `errorGlobals` quando ha erro.

## Desvios e detalhes importantes (por que o `agent/` existe)

* **Bug do ZombieBuddy 2.3.2 no Windows:** o `PreMain` experimental chama `JavaStateDumper.init()`, que registra
  o sinal `INFO` (nao existe no Windows) e estoura `IllegalArgumentException` *antes* de subir o HTTP
  (log: `error invoking premain(): InvocationTargetException`). Os patches experimentais (`ServerMap.preupdate` etc.)
  ainda sao aplicados, so o HTTP nao subia. O agente `pzlab` (carregado via `patches_jar`) sobe o mesmo
  `HttpServer` do ZombieBuddy sem esse trecho. O jar do ZombieBuddy na pasta do jogo nao e tocado.
* `/log` original le `<cachedir>/console.txt`, que nao existe em servidor dedicado (HTTP 500). O agente o substitui.
* `patches_jar` faz `split(":")`, por isso o caminho do jar e passado **relativo** a pasta do jogo (mesmo drive).
* Logs do lab ficam em `runtime/lab_logs/` e **nao** em `runtime/logs/`: o PZ arquiva tudo de `<cachedir>/Logs`
  (mesma pasta no Windows) em `logs_<data>/` a cada boot.
* `stop` gracioso: o agente le `runtime/lab_cmd.txt` e injeta cada linha na fila de comandos do console
  (`GameServer.consoleCommands`), como se digitada no terminal. `pzlab.console("quit")` salva e sai (~8 s).
  So se nao sair em `timeout_s` o `psutil` mata o processo e filhos (apenas o PID registrado, validado por nome e hora de criacao).
* A senha admin vai na linha de comando do java (visivel para outros processos da mesma maquina); servidor so escuta
  `127.0.0.1` no HTTP. O RakNet (UDP/TCP 16261) escuta em `0.0.0.0`; o Firewall do Windows pode perguntar na 1a vez - pode negar.

## Medidas (maquina de dev, 1o e demais boots)

* Boot ate "pronto": 44-49 s. Stop gracioso: ~8 s.
* RAM: ~2,5 GB de working set (`-Xmx2048m` + ZGC); CPU ociosa ~0,03 core.

## Limitacoes conhecidas

* Sem cliente: eventos que dependem de jogador (`OnPlayerUpdate`, UI, render) nao disparam. Teste logica de
  servidor/shared; para cliente use o jogo normal. Pode-se spawnar entidades/itens via Lua (`sandbox=false`).
* Mods Java (jar) de `mods/` so carregam se ja aprovados em `runtime/zombie_buddy/mod_approvals.json` (`policy=deny-new`).
* `python pzlab.py start` precisa de um JDK (`javac`) apenas na primeira vez / quando `agent/` muda.
* Editar mods em `mods/` e `restart` para recarregar (Lua de servidor so e lido no boot).
* Traducoes de mods nao aparecem no boot do servidor dedicado (o Translator carrega antes dos mods).
  `Translator.loadFiles()` via Lua recarrega e passa a incluir o mod. Coloque as traducoes em
  `common/media/lua/shared/Translate/<LANG>/*.json`.
* O lab forca `-Duser.language=en` para os testes serem deterministicos (o padrao seria o idioma do Windows).
* Um unico servidor por vez (porta fixa; configuravel em `lab.json`).
