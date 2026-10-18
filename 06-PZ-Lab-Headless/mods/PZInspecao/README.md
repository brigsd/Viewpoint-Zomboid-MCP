# PZInspecao (ferramenta de dev)

Identifica objetos do mundo para reportar problemas de posição ou modelagem.

## Uso (cliente, modo dev)

- **F6**: descreve os objetos do quadrado onde o jogador está e escreve no log, no formato:
  `[PZInspecao] <sprite>|<x>,<y>,<z>|<índice> id=<ID próprio>`.
- O ID próprio é gravado em `getModData()` do objeto na primeira vez e reaproveitado depois.

## Limitações

- Ainda não usa a mira: a Lua não recebe o objeto apontado pelo Viewpoint. Por isso o F6 olha o quadrado do jogador.
- O índice pode mudar se outro objeto do mesmo quadrado sair. O ID próprio é a referência estável.
- `math.random` não existe no Lua do PZ. O ID usa `getTimestampMs` e `ZombRand`.

## Testes

```bash
python lab/pzlab.py lua --file tests/smoke_pzinspecao.lua --depth 4
```

Cobre as funções puras (`keyOf`, `describe`, `ensureId`) com objetos falsos. O F6 e a mira só podem ser verificados no cliente.
