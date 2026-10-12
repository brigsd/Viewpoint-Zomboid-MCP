# Esteira de porte 3D — agentes que portam objetos para 3D, crítico visual e aprovação humana

**Estado:** ativo

**Módulos:** `05-Model-3D-Extractor-MCP/porte3d/` (novo), `.claude/agents/` (portador e crítico), `.claude/skills/porte-3d/` (o laço), mod próprio de modelos para o Viewpoint (novo)

## Problema observado

Os testes de 2026-10-12 (`05-Model-3D-Extractor-MCP/experimentos3d/`) mostraram três coisas:

- **Funciona.** Caixa do jogo + imagem original colada pixel a pixel ("adesivo") gera um 3D nítido e reconhecível em geladeira e mesa. No ângulo 0° bate com o desenho (contorno 94–98%, cor idêntica).
- **Nota automática engana.** A abordagem "profundidade" tirou a melhor nota (0,59) e mesmo assim estava borrada e deslocada. Só olhando dá para saber.
- **Cada objeto pede ajuste.** Pé escondido que o jogo não descreve (resolvido por simetria), medidas do tampo (ajuste de contorno), textura com ornamento ou brilho fora do lugar (resolvido com o "kit" de recortes), linha preta e pé que parece 2D (recorte com borda transparente).

Fazer isso à mão, objeto por objeto, não escala. Aceitar o automático sem olhar também não serve.

## Resultado

Uma esteira em que um agente **portador** monta o 3D de cada objeto e um agente **crítico** olha as imagens e aponta defeitos, com até 3 rodadas de retrabalho. O usuário aprova o que passou. Os aprovados viram um pack que o Viewpoint carrega no jogo, em **dois níveis gráficos**:

- **arte**: textura tirada do desenho do jogo, fiel ao estilo pixel;
- **realista**: textura de material em alta resolução gerada por código (veio de madeira, metal, tecido...), nas cores da arte, com sombra de contato pintada. O material vem da propriedade `Material` do jogo.

A mesma geometria serve aos dois níveis; só a textura muda. O Viewpoint só aceita uma textura de cor (`map_Kd`), então todo o volume do realista é pintado na textura ou modelado na geometria (teste de 2026-10-12: `experimentos3d/teste_realista_mesa.py`).

## Como funciona

```text
acervo (42.544 objetos)
   │  triagem (script): prioridade + caminho (caixa com geometria | sem geometria | fica 2D)
   ▼
fila  ──►  PORTADOR (Sonnet)  ──►  folhas de imagem  ──►  CRÍTICO (Sonnet, só olha)
              ▲  receita do objeto                            │ nota 0–10 + defeitos (JSON)
              └──────── retrabalho (máx. 3 rodadas) ◄─────────┘
                                   │ nota ≥ 8                 │ 3 rodadas sem passar
                                   ▼                          ▼
                       APROVAÇÃO HUMANA (galeria)      fila "precisa de humano"
                                   │ aprovado
                                   ▼
                       PACK (mod próprio) ──► jogo (Viewpoint)
```

- **Receita por objeto** (`porte3d/receitas/<objeto>.json`, versionada; é dado nosso). Contém as caixas e cilindros com medidas, a simetria, o modo de textura do nível arte (adesivo ou kit), os recortes do kit, o material e os parâmetros do nível realista, e as correções. O portador edita a receita, e um script determinístico gera tudo a partir dela. O agente não desenha nada direto.
- **Ferramentas do portador** (scripts em `porte3d/`, consolidando os experimentos):
  - ajuste automático das medidas pelo contorno;
  - completar por simetria;
  - textura adesivo ou kit;
  - exportar OBJ + MTL + PNG com UV;
  - gerar as folhas para o crítico.
- **Folhas para o crítico:**
  - jogo × modelo em 0° e 180°;
  - modelo girando de 45° em 45°;
  - **wireframe**, nos mesmos ângulos: só as arestas, e as arestas por cima da textura. Cada peça tem uma cor e o nome dela vai na legenda;
  - sobreposição de contorno em 0°;
  - zoom nas partes finas (pés, alças).
- **Crítico** (`.claude/agents/critico-3d.md`, no formato do crítico do Mecanifica). Só recebe imagens, sem contexto nem código. Responde a perguntas fixas:
  1. Em 0° está igual ao jogo?
  2. Em 180° está igual ao desenho de trás?
  3. Ao girar, falta alguma parte?
  4. Alguma parte parece chapada (2D)?
  5. Alguma textura aparece fora do lugar, ou há buraco ou emenda?
  6. A proporção está certa?
  7. **Pelo wireframe:** cada peça prometida existe e está no lugar? Há peça flutuando, enterrada ou atravessando outra? A estrutura faz sentido para o objeto (4 pés numa mesa, portas na frente de uma geladeira)? Há peça que deveria ser sólida e é só um plano?
  
  Fecha com JSON: `nota` e `defeitos[{parte, tipo: ausencia|chapado|textura_deslocada|buraco|emenda|proporcao|sobra|estrutura, angulo, vista: textura|wireframe|sobreposicao, onde, evidencia}]`.
- **Estado de cada objeto** (`porte3d/fila.sqlite`). Estados: `fila`, `em_porte`, `em_critica`, `retrabalho`, `precisa_humano`, `aguardando_aprovacao`, `aprovado`, `rejeitado`, `publicado`. Guarda as notas e o histórico das rodadas.
- **Galeria de aprovação.** Página local com a animação girando, a folha e o veredito do crítico. Botões aprovar e refazer, com comentário.
- **Pack** (mod próprio, ex. `PZ3DObjects`), com uma opção para escolher o nível gráfico (dois packs registrados, um por nível; só o escolhido fica ativo):
  - `pack.manifest` com valores **separados por vírgula**;
  - Lua de cliente que chama `Viewpoint.ModelPacks.register("PZ3DObjects", "media/.../pack.manifest")`;
  - uma ligação por sprite de cada direção.
  
  Nada é gravado na pasta do Viewpoint da Workshop.

## Regras do despacho em massa

Valem desde o piloto, para a esteira escalar sem perder controle:

1. **Orquestração por script, não por agente.** Um script (`porte3d/fila.py`) faz as transições de estado e distribui os objetos. Os agentes só recebem um objeto, trabalham nos arquivos daquele objeto e devolvem. Nenhum agente edita arquivo compartilhado.
2. **Contratos validados.** A receita tem esquema JSON. O veredito do crítico também, e veredito fora do esquema é recusado e refeito. As folhas têm nome e layout fixos.
3. **Crítico independente.** Ele não vê a receita nem a justificativa do portador, só as imagens. Recalibra com os casos conhecidos a cada mudança nas perguntas.
4. **Amostragem humana e minha.** Em cada lote, confiro visualmente uma amostra dos aprovados pelo crítico antes de mandar para a galeria (regra de não aceitar nota sem olhar). Medimos a concordância crítico × usuário; com concordância alta e estável, a galeria passa a mostrar só os casos duvidosos.
5. **Lotes pequenos e limites.** Lotes de 10 a 20 objetos, no máximo 3 a 4 agentes ao mesmo tempo (já vimos agentes disputando CPU), tempo máximo por objeto e por agente, e no máximo 3 rodadas de retrabalho.
6. **Freio automático.** Se mais da metade de um lote cair em "precisa de humano", a esteira para e o problema vira ajuste da ferramenta, não mais rodadas.
7. **Variantes primeiro.** Objetos com a mesma forma e cores diferentes (mesmo tileset/GroupName) reaproveitam a geometria e só trocam a textura. Um modelo aprovado vira vários.
8. **Prioridade.** Primeiro o que aparece em toda casa: cozinha, eletrodomésticos e móveis com geometria, ordenados por número de variantes. O usuário pode furar a fila a qualquer momento com o que mais incomoda no jogo.
9. **Git por lote.** As receitas, os vereditos e o histórico são commitados ao fim de cada lote. As imagens e texturas derivadas do jogo ficam fora do git.
10. **Despacho em massa só depois do gate.** Lotes além do piloto só rodam depois que o gate deste plano passar, como plano próprio. Para isso o usuário precisa pedir explicitamente um workflow ("use um workflow"), porque são dezenas de agentes.

## Incluído

- Biblioteca `porte3d` (receita → modelo → OBJ/MTL/PNG + folhas), com testes.
- Mod próprio mínimo e **prova no jogo com 1 objeto antes de escalar**.
- Agentes portador e crítico, mais a skill do laço.
- Calibração do crítico com casos conhecidos, antes de confiar nele. Ele precisa reprovar:
  - a geladeira borrada da "profundidade";
  - a mesa sem o pé de trás, que **o wireframe** tem que denunciar;
  - o pé com linha preta.
  
  E precisa aprovar a geladeira "adesivo".
- Fila, estados e galeria de aprovação.
- Piloto com 10 objetos de caixa com geometria: geladeiras, fogões, máquinas, balcões, armários, mesas e caixotes, nos dois níveis.
- Geradores de material do nível realista: madeira (feito no teste), metal e tecido no piloto; os demais entram conforme a fila pedir.
- Limpeza do que o Módulo 05 antigo gravou na pasta da Workshop.

## Excluído

- Objetos sem geometria, finos ou vazados (luminárias, cortinas, plantas, cadeiras de perninha). Vão para um plano seguinte.
- Móveis de 2 ou mais tiles (`SpriteGridPos`). Também vão para um plano seguinte.
- Automação do cliente para print no jogo. A conferência no jogo é do usuário, por enquanto.
- Publicar o mod na Workshop. Ver o risco de arte do jogo abaixo.

## Gate de saída

1. O objeto de prova aparece em 3D no jogo. O log do Viewpoint mostra modelos de pack na GPU (`model packs N models`, N > 0) e o usuário confirma visualmente com um print (F9).
2. Na calibração, o crítico reprova os 3 casos ruins e aprova o caso bom.
3. O piloto passa 10 objetos pela esteira nos dois níveis. Pelo menos 7 são aprovados pelo usuário na galeria em cada nível, e todos os aprovados aparecem no jogo, com a troca de nível funcionando.
4. Cada aprovado tem receita versionada, histórico de rodadas e veredito do crítico registrados.
5. Nada é gravado na pasta do jogo nem na do Viewpoint da Workshop, e a arte extraída do jogo fica fora do git.
6. `python planos/check.py` passa.

## Fatias

1. **Biblioteca `porte3d`:** receita, modelo, export OBJ/MTL/PNG e folhas, consolidando `teste_adesivo*`, `teste_manual_mesa*` e o ajuste de contorno.
2. **Prova no jogo com a geladeira:** mod próprio, pack.manifest e register. O usuário confere. Aqui se descobre a escala, os eixos, a orientação do UV e como o Viewpoint ilumina o modelo. Se falhar, nada mais adianta.
3. **Crítico:** a definição do agente e a calibração com os 4 casos conhecidos.
4. **Portador, laço e fila:** a skill `porte-3d` e os estados.
5. **Galeria e piloto de 10 objetos.**
6. **Fechamento.**

## Riscos e parada

- **O Viewpoint não carrega ou desenha errado o OBJ na fatia 2** (escala, eixos, textura). Parar e investigar o formato no `Viewpoint.jar` (`viewpoint.packs.*`) antes de seguir.
- **O crítico não separa bom de ruim na calibração.** Ajustar as perguntas. Se ainda assim falhar, a aprovação fica toda com o usuário e o crítico vira só uma triagem.
- **Arte do jogo dentro do mod.** As texturas são derivadas da arte da The Indie Stone. Para uso pessoal tudo bem; publicar na Workshop exige decidir antes, porque muitos mods fazem isso, mas é uma decisão do usuário.
- **Direções espelhadas** (E/W são espelho de S/N). Ligar o mesmo modelo girado pode mostrar o objeto "ao contrário" do desenho 2D. Conferir na prova da fatia 2.

## Fechamento

Preencher somente ao concluir, cancelar ou congelar.
