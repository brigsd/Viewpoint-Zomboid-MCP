# Calibração do crítico 3D, 2026-10-12

## Como foi feita

Foram 5 casos gerados pela própria biblioteca, no formato das folhas. As pastas tinham nomes neutros (`caso_1` a `caso_5`), para o nome não entregar o defeito. Cada caso foi avaliado por um crítico Sonnet independente, que seguia `.claude/agents/critico-3d.md`. As peças prometidas estão em `pecas_prometidas.json`.

## Resultado

| caso | o que era | esperado | arte | realista | ok? |
|---|---|---|---|---|---|
| 1 | geladeira boa (`receitas/geladeira_branca_n3.json`) | aprovar | 8 | 7 → 8 | sim, depois de 1 retrabalho |
| 2 | mesa sem os pés de trás (`calib_mesa_sem_pes_tras`) | reprovar | 4 | 4 | sim: pé `ausente`, grave, visto no giro e no fio |
| 3 | geladeira com a traseira errada (`calib_geladeira_tras_errada`) | reprovar a arte | 4 | 8 | sim: traseira com a textura da frente, grave, em 180° |
| 4 | mesa boa (`receitas/mesa_fancy_dark.json`) | aprovar | 8 | 8 | sim |
| 5 | mesa com o pé chapado (`calib_mesa_pe_chapado`) | reprovar | 6 | 6 | sim: `chapado`, grave, no giro 315° e no fio |

**Caso 1:** na primeira passada, o realista levou 7. O crítico apontou a serpentina preta (no jogo é cinza-azulada) e a pintura limpa demais. Eu também tinha anotado essas duas coisas ao olhar as folhas. Corrigi a cor da serpentina e pus um desgaste leve (0,35), e na rodada 2 ele deu 8 e 8. Foi o primeiro retrabalho do laço, feito à mão.

**Defeitos leves que o crítico achou e que existem de verdade:**
- a franja serrilhada na saia da mesa, que é a borda em degraus do pixel art;
- a quebra na linha da tampa da geladeira;
- o deslocamento de 1 a 2 px do pé da frente;
- o veio vertical do metal pintado, que lembra madeira de perto.

## Ajustes feitos por causa da calibração

- A folha agora mostra sempre o desenho de trás **verdadeiro** do jogo (`tras_original`), mesmo quando a receita usa `simetrico`. Sem isso, a traseira errada não podia ser vista.
- O agente crítico agora lista os valores de `gravidade` (`grave`, `media` e `leve`). Um crítico tinha escrito `medio`, que o validador recusaria.

## Calibração do inspetor

Foram 3 casos, cada um com um inspetor Sonnet independente (`.claude/agents/inspetor-3d.md`), sobre as medições de `porte3d/inspecao.py`. As fichas estão em `ficha_insp_*.json`, e as 3 são válidas no esquema.

| caso | esperado | o que o inspetor fez | ok? |
|---|---|---|---|
| mesa (`furniture_tables_high_01_16`) | apontar o pé faltando | `pe_tras` com origem `simetria` (o jogo descreve só 3 pés). Também apontou a saia como peça `nova` e o tampo de 18 cm grosso demais para o desenho | sim. Faltaram as cantoneiras pequenas, que é detalhe |
| geladeira (`appliances_refrigeration_01_0`) | apontar o espelhamento | `direcoes_espelhadas = true` e `tras = N` (a traseira tem desenho próprio). Pediu portas, puxadores, rodapé, serpentina, nicho e compressor como peças novas | sim |
| luminária de parede (`lighting_indoor_01_17`) | "não portar" | `nao_portar`: objeto de parede, pequeno, e as caixas do jogo não casam com o desenho (contorno de 0,25) | sim |
