# Piloto da esteira de porte 3D, 2026-10-12

## Como foi feito

Foram 10 objetos de cozinha e eletrodomésticos, levados pela esteira completa:

1. medições do inspetor por script;
2. o agente inspetor (ficha);
3. o agente modelador (receita);
4. a geração no Blender;
5. o agente crítico, sem saber o nome do objeto, com até 3 rodadas.

Os textos são em Sonnet. Cada objeto usou cerca de 1 minuto de máquina por rodada.

## Resultado do crítico

| objeto | rodadas | arte / realista | estado |
|---|---|---|---|
| microwave_white | 1 | 9 / 8 | aguardando o usuário |
| freezer_chest | 1 | 8 / 8 | aguardando o usuário |
| oven_green | 2 | 8 / 8 | aguardando o usuário |
| washing_machine_white | 2 | 8 / 8 | aguardando o usuário |
| fridge_white | 3 | 9 / 8 | aguardando o usuário |
| fridge_blue | 3 | 8 / 8 | aguardando o usuário |
| dishwasher_metal | 3 | 9 / 8 | aguardando o usuário |
| television_antique | 3 | 8 / 8 | aguardando o usuário |
| oven_modern | 3 | 7 / 8 | reprovado: cunha na aba, que era defeito da ferramenta (já corrigido; regerado, a cunha sumiu) |
| counter_corner_a | 3 | 6 / 7 | reprovado: vidro translúcido, que o modelo sem transparência não reproduz |

**8 de 10 passaram no crítico.** A minha conferência por amostra (geladeira branca, TV e micro-ondas) concorda com ele.

## Ferramenta corrigida durante o piloto

Os defeitos apontados pelo crítico revelaram estes problemas:

- **Deslocamento do desenho de trás.** O jogo posiciona o objeto virado para N alguns centímetros fora do lugar em relação ao S girado. Agora isso é medido pela geometria (`deslocamento_tras`) e aplicado na textura, na prévia e na vista de 180°.
- **Escolha da vista por texel.** A escolha usava a normal suavizada (inclinada perto dos chanfros) e uma visibilidade com ruído de amostragem, o que gerava cunhas e manchas no topo. Agora a luz só diz se o texel é visto, e a pontuação vem da normal da face dominante, com a frente ganhando os empates.
- **Cor automática do realista.** Ela saía escura, pela mediana com as sombras. Agora usa a mediana dos 35% de pixels mais claros.
- **Faces coincidentes.** A prévia agora aponta peças com faces no mesmo plano.
- **`arte_cor` por peça.** Usa cor lisa no nível arte (vidro).
- **Pedido do crítico.** Vai numa pasta neutra, e o crítico grava a resposta num arquivo.

## Lições para os lotes

- Objetos com vidro ou transparência devem ir para "não portar" ou para um plano próprio. O Viewpoint só tem a textura de cor, sem transparência.
- Antes da produção, os aprovados do piloto foram regerados com a ferramenta corrigida (`portar` direto da receita).
- O realista leva 7 quase sempre pela cor ou pelo detalhe fino. Agora o modelador já recebe a orientação de cor e desgaste na definição.
