# [Nome do plano] — resultado curto

**Estado:** rascunho

**Módulos:** quais pastas da suíte o plano toca (ex.: `06-PZ-Lab-Headless/mcp/`)

## Problema observado

A evidência reproduzível e a consequência. Aponte para o log, teste ou commit; não copie relatórios inteiros.

## Resultado

Uma frase verificável dizendo o que passa a ser possível.

## Incluído

- a mudança estritamente necessária;
- a prova no laboratório (`06-PZ-Lab-Headless`) quando o resultado envolver o jogo.

## Excluído

- melhorias próximas que não bloqueiam o resultado (devolva ao `BACKLOG.md`);
- refatorações sem relação com o gate.

## Gate de saída

1. comportamento mensurável (teste Lua no lab, teste Python, comando com saída esperada);
2. nada gravado na pasta do jogo nem em `C:\Users\micro\Zomboid` sem que o plano diga isso;
3. documentação do módulo atualizada;
4. `python planos/check.py` passando.

## Fatias

1. caso que falha ou linha de base;
2. menor implementação completa;
3. prova e documentação;
4. fechamento.

## Riscos e parada

O risco que obriga parar, congelar ou redesenhar antes de ampliar o escopo.

## Fechamento

Preencher somente ao concluir, cancelar ou congelar: estado final, commit, evidências do gate, resultado observado e o que voltou para o backlog.
