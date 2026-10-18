# Inspeção de objetos — tag no jogo e inspeção isolada na Bancada 3D

**Estado:** pronto

**Módulos:** `06-PZ-Lab-Headless/mods/PZInspecao/` (tag no jogo, novo), `05-Model-3D-Extractor-MCP/` (Bancada 3D Mecanifica, já existe)

## Problema observado

Quando um objeto 3D substituído aparece torto, flutuando ou enterrado, não há como dizer ao Claude qual instância é. Um objeto é identificado só pela posição e pelo sprite, e o índice na lista do quadrado pode mudar. A inspeção do modelo também só acontece fora do jogo, sem o contexto real.

## Resultado

- **Fase 1**: no jogo, em modo dev, uma tecla grava no log a identificação do objeto (sprite, coordenadas, índice e ID próprio).
- **Fase 2**: a Bancada 3D mostra o modelo isolado para inspeção, com o objeto identificado pela fase 1.

## Incluído

- Fase 1: funções de identificação, tecla F6 que grava no log, teste no lab.
- Fase 2: uso da Bancada 3D existente (`mecanifica:ativar_bancada`) com o objeto identificado. Nada novo no jogo.

## Excluído

- Isolamento dentro do jogo (esconder objetos do mundo).
- Girar, mover ou alterar o objeto no jogo.
- Alterações no JAR do Viewpoint, que é proprietário.

## Gate de saída

1. Teste no lab (`06-PZ-Lab-Headless`): as funções da fase 1 retornam o valor esperado, com saída registrada.
2. Nada gravado na pasta do jogo nem em `C:\Users\micro\Zomboid` sem o usuário pedir. A instalação no cliente é do usuário.
3. Verificação no cliente, feita pelo usuário: a tecla F6 grava a linha no log.
4. Fase 2 verificada pelo usuário na Bancada 3D com um objeto da fase 1.
5. Documentação atualizada.
6. `python planos/check.py` passando.

## Fatias

1. Linha de base na API (feita em 2026-10-18).
2. Fase 1: funções, F6 e teste no lab (feita em 2026-10-18, 9/9 no lab; a mira fica pendente).
3. Fase 2: Bancada 3D com o objeto identificado.
4. Prova no cliente pelo usuário, documentação e fechamento.

## Riscos e parada

- A mira depende do Viewpoint. Se não for possível ligá-la, a fase 1 segue com o quadrado do jogador.

## Fechamento

Preencher ao concluir, cancelar ou congelar.
