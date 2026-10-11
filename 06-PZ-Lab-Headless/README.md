# 🧪 Módulo 06: PZ Lab Headless

Laboratório para criar e testar mods do *Project Zomboid Build 42.21* **sem abrir o jogo**. Um servidor dedicado roda em background, sem janela, com o ZombieBuddy injetado e um servidor HTTP local que executa Lua dentro do jogo. O Claude controla tudo pelo MCP `pz-live`.

```text
Claude ──MCP pz-live──► pzlab.py ──► Servidor dedicado PZ 42.21 (headless)
                                        + ZombieBuddy + HTTP em 127.0.0.1:8642
                                        + mods de mods/ (ligados por junction)
                                        + dados isolados em runtime/ (-cachedir)
```

| Pasta | Conteúdo |
| :--- | :--- |
| [`lab/`](./lab/) | `pzlab.py`: liga, desliga e reinicia o servidor, roda Lua e lê o log. Inclui um mini-agente Java que contorna dois bugs do ZombieBuddy 2.3.2 no Windows. |
| [`mcp/`](./mcp/) | Servidor MCP `pz-live` (registrado em `.mcp.json` na raiz da suíte), com testes. |
| [`mods/`](./mods/) | Mods em desenvolvimento. Todos são carregados no servidor ao iniciar. |
| [`tests/`](./tests/) | Testes em Lua que rodam no servidor e o padrão para escrever novos testes. |
| `runtime/` | Mundo de teste, logs e config do ZombieBuddy (ignorado pelo git). |

## Uso rápido

```bash
python lab/pzlab.py start
```

```bash
python lab/pzlab.py lua "return getCore():getVersion()"
```

```bash
python lab/pzlab.py stop
```

## Estado atual

* Boot em ~45–50 s, ~2,5 GB de RAM, parada graciosa em ~8 s.
* O mod de prova `ZBLabTest` (item + receita) passa no `tests/smoke_zblabtest.lua`: 29/31 verificações, 0 falhas, 2 avisos de tradução que são esperados no servidor dedicado.
* Nada é gravado na pasta do jogo nem em `C:\Users\micro\Zomboid`.

## Limitações

* Não há jogador: interface, renderização, Viewpoint, shaders e eventos de jogador não rodam aqui.
* Scripts (`media/scripts`), traduções e Java exigem `restart`. Arquivos Lua podem ser recarregados com `reload_lua`.
* Veja os detalhes em [`lab/README.md`](./lab/README.md) e [`tests/README.md`](./tests/README.md).
