# 🗺️ Planos da Suíte

## Estado

**Plano ativo:** [Esteira de porte 3D](2026-10-12-esteira-de-porte-3d.md).

Agentes que portam os objetos do jogo para 3D (portador), um crítico visual que só olha as imagens (inclusive o wireframe) e aprovação do usuário numa galeria, em dois níveis gráficos (arte e realista), publicados num mod próprio que o Viewpoint carrega. Começa com a prova de 1 objeto no jogo e termina com um piloto de 10.

Candidatos esperando decisão estão no [`BACKLOG.md`](BACKLOG.md).

| Pasta | O que guarda |
| :--- | :--- |
| raiz (`planos/`) | planos em `rascunho`, `pronto` ou `ativo` |
| [`concluidos/`](concluidos/) | planos `concluído` ou `cancelado`, com o fechamento preenchido |
| [`congelados/`](congelados/) | planos `congelado`: pausados de propósito, com o motivo e o que destrava |

### Concluídos

| Data | Plano | Resultado |
| :--- | :--- | :--- |
| 2026-10-11 | [Acervo de objetos do jogo com textura](concluidos/2026-10-11-acervo-de-objetos.md) | 42.544 objetos com imagem, propriedades, geometria 3D e profundidade, com alinhamento comprovado |
| 2026-10-11 | [Base de conhecimento da API 42.21 (camada 2)](concluidos/2026-10-11-base-de-conhecimento-api.md) | Índice da API real consultado pelo `pz-live` + skill `pz-modding`; 23/23 no índice e no jogo vivo |
| 2026-10-11 | [Laboratório headless (camada 1)](concluidos/2026-10-11-laboratorio-headless.md) | Servidor dedicado sem janela + MCP `pz-live`; mod de prova passa 29/31, 0 falhas |

### Congelados

Nenhum.

## Contrato de plano

Todo plano parte do [`MODELO.md`](MODELO.md) e declara:

1. um resultado verificável, numa frase;
2. o problema observado que justifica o trabalho;
3. o que está incluído e o que está fora;
4. o gate de saída, com as evidências esperadas;
5. as fatias de execução;
6. o risco que obriga parar;
7. o fechamento, preenchido ao concluir ou cancelar.

Os arquivos de plano se chamam `AAAA-MM-DD-nome-curto.md`, com a data de abertura.

Estados aceitos: `rascunho`, `pronto`, `ativo`, `concluído`, `cancelado` e `congelado`.

* Só existe **um plano `ativo` por vez**.
* Um item do backlog não autoriza implementação. Ele vira plano primeiro.
* Ao concluir, cancelar ou congelar, o plano sai da raiz para a pasta certa e entra na tabela acima.

## O que o gate verifica

```bash
python planos/check.py
```

O script lê todos os `.md` de `planos/` e das subpastas, exceto `README.md`, `MODELO.md` e `BACKLOG.md`, e falha quando:

* um plano não declara `**Estado:**` ou usa um estado fora da lista;
* um plano passa de 300 linhas;
* existe mais de um plano `ativo`;
* um plano está na pasta errada para o seu estado;
* a linha `**Plano ativo:**` deste índice não bate com o plano que está de fato `ativo`. Ela deve linkar o arquivo do plano entre parênteses, ou dizer `nenhum.`.
