# pz-live — servidor MCP do laboratório headless de Project Zomboid

Servidor MCP (FastMCP, Python 3.12) que deixa o Claude **testar mods de PZ Build 42 sem abrir o jogo**:
sobe um servidor dedicado com ZombieBuddy (via `../lab/pzlab.py`), executa Lua nele pela API HTTP
experimental do ZombieBuddy, lê o log, recarrega arquivos Lua e roda testes.

```
Claude  --stdio/MCP-->  mcp/server.py (pz-live)  --HTTP 127.0.0.1-->  PZ dedicated server + ZombieBuddy
                              |                                        (/lua  /log  /status  /version)
                              +--> lab/pzlab.py (start / stop / status / log_path)
```

## Instalação

```powershell
python -m pip install -r requirements.txt     # mcp + httpx
```

## Registro no Claude Code (`.mcp.json` do projeto)

Cole em `C:\Users\micro\Desktop\ProjectZomboid-FirstPerson-Suite\.mcp.json` (ou use `claude mcp add`):

```json
{
  "mcpServers": {
    "pz-live": {
      "command": "C:\\Users\\micro\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
      "args": [
        "C:\\Users\\micro\\Desktop\\ProjectZomboid-FirstPerson-Suite\\06-PZ-Lab-Headless\\mcp\\server.py"
      ]
    }
  }
}
```

Equivalente via CLI:

```powershell
claude mcp add pz-live --scope project -- "C:\Users\micro\AppData\Local\Programs\Python\Python312\python.exe" "C:\Users\micro\Desktop\ProjectZomboid-FirstPerson-Suite\06-PZ-Lab-Headless\mcp\server.py"
```

> `lab_start` pode levar minutos (boot do servidor + carga do mundo). Se o Claude Code cortar a chamada por
> tempo, defina `MCP_TOOL_TIMEOUT` (ms, ex. `600000`) no ambiente em que o `claude` é iniciado. O
> `timeout_s` do `lab_start` controla só a espera do boot.

## Ferramentas

| Ferramenta | O que faz |
|---|---|
| `lab_start(mods=None, timeout_s=300)` | Sobe o servidor dedicado headless com os mods de `mods/` (ou só os listados) e espera ficar pronto. |
| `lab_stop(timeout_s=60)` | Para o servidor. |
| `lab_restart(mods=None, timeout_s=300)` | Reinicia (necessário para mudanças em `media/scripts`, traduções, Java). |
| `lab_status()` | Processo vivo, porta, `http_ok`, uptime, arquivo de log. |
| `lua_exec(code, timeout_ms=None, depth=5, sandbox=True, auto_return=True, ...)` | Executa Lua no servidor; devolve o `return` em JSON ou erro estruturado. |
| `lua_inspect(expr, include_private=False, filter=None, max_items=200)` | Inspeciona objeto Java (zbinspect), tabela Lua ou função. |
| `log_tail(lines=100, grep=None, source="auto")` | Últimas linhas do log (arquivo do launcher; cai para `/log`). |
| `lua_errors(since_start=True, ...)` | Erros Lua/script/Java do log, deduplicados e agrupados, com arquivo:linha e mod. |
| `reload_lua(path, method="auto")` | Hot-reload de um `.lua` (`reloadLuaFile`; fallback: reexecuta o arquivo com `sandbox=false`) e relatório de erros novos no log. |
| `run_lua_test(path, timeout_ms=60000, depth=6, sandbox=True)` | Roda um teste `.lua` do disco e devolve resultado + `summary`/`report`/`failed_checks`. |
| `list_dev_mods()` | Lista `mods/*` com id, nome, versionMin (de `common/mod.info`). |
| `scaffold_mod(mod_id, name, description="")` | Cria o esqueleto de um mod B42 (recusa sobrescrever). |
| `api_search(query, kind=None, limit=20)` | Busca FTS5 na API real 42.21 (globais, classes, métodos, campos, eventos). Devolve assinatura e forma de chamada (`Owner.metodo` / `obj:metodo` / `nome()`); nome exato primeiro; cai para LIKE. |
| `api_class(name, filter=None, limit=200)` | Classe Java exposta ao Lua (nome curto ou FQN): `java_class`, métodos e campos, estáticos e de instância separados. Sugestões se não existir. |
| `api_event(name)` | O evento existe? Até 10 usos vanilla (arquivo:linha + trecho) e o padrão de argumentos do callback quando inferível. |
| `script_fields(block_type=None, field=None)` | Campos válidos de blocos de script (`item`, `craftRecipe`, ...) com contagem e exemplo real; `field='inputs.item'` mostra a forma real da linha. Sem argumentos lista os tipos de bloco. |
| `vanilla_examples(symbol, limit=10)` | Usos reais do símbolo no Lua vanilla (arquivo:linha + trecho). |
| `api_exists(name, owner=None)` | Sim/não rápido (`Languages.instance` existe?) com as linhas encontradas, sugestões e aviso de maiúsculas. |

Todas devolvem um dict com `ok`. Em falha: `error` (mensagem), `error_kind`
(`server_down | config | lua | compile | java | timeout | usage | exists | test_failed | http | lab | index_missing | index_error`) e,
quando útil, `hint` (ex.: *"servidor parado — chame lab_start"*) e `detail` (stack, arquivo, linha).

### `lua_exec` — o que saber

* O valor do primeiro `return` volta em `result`. Uma expressão de uma linha
  (`getGameTime():getWorldAgeHours()`) ganha `return` automaticamente; blocos multi-linha precisam de
  `return` explícito.
* **`depth`** (padrão 5): o `/lua` do ZombieBuddy usa `depth=1` por padrão e troca qualquer tabela
  aninhada por `"[table]"`; este MCP sempre envia `depth` explícito.
* **`sandbox`** (padrão `True`, igual ao ZombieBuddy): o chunk roda em um ambiente cujo `__index` é o
  global do jogo — você **lê** globais do mod normalmente, mas globais que **criar** não persistem.
  `sandbox=False` grava no ambiente real.
* Roda no contexto do **servidor** dedicado (sem jogador/UI). A fila de tarefas só é drenada no tick do
  servidor: durante o boot as chamadas dão `error_kind: timeout`.
* `print()` vai para o **log** do servidor (use `log_tail`), não para a resposta; só o 1º `return` volta
  (nenhum valor → `null`).
* O `GET /status` responde `ok` assim que o agente carrega, **antes** de o mundo estar pronto — quem espera
  o boot completo é o `lab_start`. Chamadas Lua durante o boot dão `timeout`.
* Limite do lado do servidor: `lua_task_timeout` (30000 ms no lab; o timeout HTTP do cliente é 35 s) (em `lab/lab.json` → `zombiebuddy.lua_task_timeout_ms`).
  `timeout_ms` da ferramenta é só a espera HTTP do cliente.
* Múltiplos arquivos num mesmo POST com marcadores `---FILE:nome.lua---` (todos menos o último rodam antes).

### `reload_lua` — limitações

* Só `.lua`. Mudou `media/scripts/*.txt`, traduções ou Java → **sempre** `lab_restart` (scripts só são lidos
  no boot). O Lua de mods também só é lido no boot pelo carregador normal; se o reload não bastar,
  `lab_restart` (~45 s).
* `method="auto"`: tenta `reloadLuaFile` (achando o arquivo em `getLoadedLua`); se a função não existir ou
  falhar e o arquivo existe no disco, **reexecuta o conteúdo local** como chunk `sandbox=false`
  (`method: "rerun_content"` no retorno). `method="engine"` / `"rerun"` força um dos dois.
* Reexecuta o arquivo inteiro: `Events.X.Add(fn)` no topo registra **listener duplicado**. Use guardas
  ou `Events.X.Remove` antes de `Add`; para validação limpa prefira `lab_restart`.
* Closures/objetos já criados mantêm o comportamento antigo.
* O arquivo é localizado entre os Lua carregados (`getLoadedLua`) por sufixo do caminho; se ambíguo,
  devolve `status: "ambiguous"` com as candidatas.

### `run_lua_test` — convenção de retorno

O teste termina com `return { ok=bool, test=, total=, passed=, failed=, softFailed=, summary=, report=,
checks={ {name, ok, soft, detail}, ... } }` (ver `../tests/README.md`). O MCP devolve `test_passed`,
`summary`, `report` (texto multi-linha), `failed_checks` (checks `ok=false` e `soft=false`) e `warnings`
(checks `soft=true` que falharam — **não** reprovam). Também aceita `ok`/`passed`/`failed`/`failures`
ou `return true|false`. Com `check_log=True` anexa `new_errors` (erros que surgiram no log durante o teste).

### `lua_errors` — o que é detectado

Blocos `ERROR:` e quaisquer blocos com `STACK TRACE`, `attempted index`, `tried to call nil`,
`Exception`, `ScriptManager/ScriptParser`, falha de `require`, linhas `[ZB] [!]`. Categorias:
`lua | script | java | other`. Ruído vanilla conhecido (ex.: *Sanitizing container name*, NPE do
`NetChecksum` no boot dedicado) é descartado por padrão e contado em `ignored_noise`
(`default_noise_filter=False` mostra tudo; `ignore=[regex,...]` adiciona filtros seus).
`since_start=True` = só o log da execução atual (o launcher grava um arquivo por start).

### Consulta à API do jogo (`api_*`, `script_fields`, `vanilla_examples`)

Essas seis ferramentas **não precisam do laboratório**: leem o índice SQLite gerado por
`07-PZ-API-Knowledge/build_index.py` (`07-PZ-API-Knowledge/data/pz_api.sqlite`, esquema em
`07-PZ-API-Knowledge/schema.sql`), sempre em modo **somente leitura**. Lógica em `api_index.py`.
Use-as **antes** de escrever Lua: elas respondem "esta função/evento/campo existe na 42.21?" sem chute.

* Sem o banco: `ok: false`, `error_kind: "index_missing"`, `hint: "rode python 07-PZ-API-Knowledge/build_index.py"`.
  Banco ilegível/esquema velho: `error_kind: "index_error"`.
* Toda resposta de sucesso traz `meta.game_version` e `meta.built_at` (índice velho fica visível).
* **"Não encontrado" não é falha**: `ok: true` com `found`/`exists: false`, `suggestions` (nomes parecidos) e
  um `hint` lembrando de não inventar a API; confirme ao vivo com `lua_exec`/`lua_inspect` se precisar.
* Forma de chamada (`call`): `Owner.metodo` (estático), `obj:metodo` (instância), `nome()` (global),
  `Events.Nome` (evento). O Lua diferencia maiúsculas: `api_exists` avisa em `case_mismatch`.
* `api_event`: `callback.args` vem dos nomes de parâmetros em `Events.X.Add(function(a, b)` numa só linha
  do vanilla; `null` quando nenhum uso permite inferir.

## Variáveis de ambiente (opcionais)

| Variável | Efeito |
|---|---|
| `PZ_LIVE_HTTP_BASE` | URL base da API HTTP (ignora `pzlab.http_base()`). |
| `PZ_LIVE_LOG_FILE` | Arquivo de log a ler (ignora `pzlab.log_path()`). |
| `PZ_LIVE_MODS_DIR` | Pasta de mods de dev (ignora `pzlab.MODS_DIR`). |
| `PZ_LIVE_HTTP_TIMEOUT` | Timeout HTTP padrão em segundos (padrão 35). |
| `PZ_API_DB` | Caminho do índice SQLite da API (padrão `07-PZ-API-Knowledge/data/pz_api.sqlite`). |
| `PZ_LIVE_START_TIMEOUT` | `timeout_s` padrão de `lab_start`/`lab_restart` (padrão 300). |

Se `lab/pzlab.py` não existir ou falhar ao importar, o servidor MCP **sobe mesmo assim**: `lab_*` devolvem
`error_kind: "config"` com o motivo, e as ferramentas de Lua/log funcionam se a API HTTP responder.

## API HTTP do ZombieBuddy usada

| Chamada | Detalhe |
|---|---|
| `POST /lua?chunkname=&depth=&sandbox=` | corpo = Lua (UTF-8, `text/plain`); header opcional `X-ZombieBuddy-Error-Globals: g1,g2`. 200 → JSON do 1º `return`; 500 → `{"err_code":1,"luaReturn":{errorString,luaStackTrace,errorObject,javaException,kahluaErrors}}` (1 = erro Lua; sem `luaStackTrace` = erro de compilação) ou `{"err_code":2\|3,"javaException":{...},"kahluaErrors":[...]}` (3 = timeout na fila); 400 corpo vazio; 405 não-POST. |
| `GET /log?lines=N` | texto puro, últimas N linhas do `server-console.txt`. |
| `GET /status`, `GET /version` | `ok` / versão do ZombieBuddy. |

## Testes

```powershell
cd 06-PZ-Lab-Headless\mcp
python -m unittest discover -s tests -v
```

Usam `tests/fake_zb_server.py` (imita os endpoints; não executa Lua) e um log de exemplo — não precisam do
jogo. Se `lupa` estiver instalado (`pip install lupa`), os snippets Lua gerados (`lua_inspect`,
`reload_lua`) também são executados em um Lua real com APIs do PZ simuladas. O fake pode ser iniciado
à mão: `python tests/fake_zb_server.py 8642` (cuidado para não colidir com o servidor real).
