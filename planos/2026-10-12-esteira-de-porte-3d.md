# Esteira de porte 3D — agentes que portam objetos para 3D, crítico visual e aprovação humana

**Estado:** ativo

**Módulos:** `05-Model-3D-Extractor-MCP/porte3d/` (novo), `.claude/agents/` (inspetor, modelador e crítico), `.claude/skills/porte-3d/` (o laço), mod próprio de modelos para o Viewpoint (novo)

## Problema observado

Os testes de 2026-10-12 (`05-Model-3D-Extractor-MCP/experimentos3d/`) mostraram três coisas:

- **Funciona.** Caixa do jogo + imagem original colada pixel a pixel ("adesivo") gera um 3D nítido e reconhecível em geladeira e mesa. No ângulo 0° bate com o desenho (contorno 94–98%, cor idêntica).
- **Nota automática engana.** A abordagem "profundidade" tirou a melhor nota (0,59) e mesmo assim estava borrada e deslocada. Só olhando dá para saber.
- **Cada objeto pede ajuste.** Pé escondido que o jogo não descreve (resolvido por simetria), medidas do tampo (ajuste de contorno), textura com ornamento ou brilho fora do lugar (resolvido com o "kit" de recortes), linha preta e pé que parece 2D (recorte com borda transparente).

Fazer isso à mão, objeto por objeto, não escala. Aceitar o automático sem olhar também não serve.

## Resultado

Uma esteira em que um agente **modelador** monta o 3D de cada objeto e um agente **crítico** olha as imagens e aponta defeitos, com até 3 rodadas de retrabalho. O usuário aprova o que passou. Antes de modelar, um agente **inspetor** levanta o que precisa ser feito numa ficha de serviço; os objetos que não passam em 3 rodadas viram uma lista curta com o motivo. Os aprovados viram um pack que o Viewpoint carrega no jogo, em **dois níveis gráficos**:

- **arte**: textura tirada do desenho do jogo, fiel ao estilo pixel;
- **realista** (o "nível 3", adotado em 2026-10-12 depois do teste da mesa): geometria com detalhe (chanfro nas bordas, pés afinando, saia, cantoneiras, puxadores) e textura de material gerada no Blender sem janela (madeira com anéis e tábuas diferentes entre si, metal, tecido), nas cores da arte, com a oclusão de ambiente assada na textura. O material vem da propriedade `Material` do jogo.

A mesma malha serve aos dois níveis; só a textura muda. O Viewpoint só aceita uma textura de cor (`map_Kd`), então todo o volume do realista é modelado na geometria ou assado na textura (testes de 2026-10-12: `experimentos3d/teste_realista_mesa.py` e `experimentos3d/blender_mesa_nivel3.py`). Ferramenta: Blender 5.2 (instalado pela Steam), rodando sem janela.

## Como funciona

```text
acervo (42.544 objetos)
   │  prioridade (script)
   ▼
INSPETOR  = medições (script) + perguntas visuais (agente Sonnet)
   │  ficha de serviço: peças prometidas, caminho, problemas previstos, material, simetria
   ├──► "não portar" (fica 2D / outra fila) ──► lista de não portados
   ▼
MODELADOR (Sonnet) ── receita ──► folhas (textura + wireframe + sobreposição + zoom)
   ▲                                              │
   │                                              ▼
   └── retrabalho com os defeitos ◄──── CRÍTICO (Sonnet, só olha; confere a ficha peça por peça)
       (máx. 3 rodadas, nota < 8)                 │ nota ≥ 8
                                                  ▼
                              conferência por amostra (eu) ──► GALERIA (usuário aprova)
                                                  │ aprovado
                                                  ▼
                              PACK (mod próprio, nível arte e realista) ──► jogo (Viewpoint)

3 rodadas sem nota 8 ──► LISTA FINAL DE REPROVADOS (gerada por script): objeto · última nota · motivo em 1 linha
```

- **Inspetor** (`.claude/agents/inspetor-3d.md` + `porte3d/inspecao.py`). Entra antes de modelar e levanta o que precisa ser feito.
  - **Medições por script** (exatas, sem IA): tem blocos ou não; quantas direções; se E/W são espelho de S/N; se o bloco é maior que o desenho (contorno em 0°); peças só de um lado (sinal de peça escondida, como o pé de trás da mesa); ocupa mais de um tile (`SpriteGridPos`); mapa de profundidade bate com a imagem; material (`Material`).
  - **Perguntas visuais do agente** (só o que precisa de olho): que objeto é; quais peças tem e a forma de cada uma; se é simétrico (e em que eixo); se tem partes finas, vazadas ou transparentes; o que está escondido no desenho e precisa ser completado; se vale portar ou fica 2D.
  - **Saída: ficha de serviço** (`porte3d/fichas/<objeto>.json`, esquema validado): peças prometidas (nome, forma, origem: bloco do jogo, simetria ou nova), caminho de textura (adesivo ou kit), material do nível realista, problemas previstos e decisão portar/não portar com o motivo.
  - Calibração: com os casos conhecidos, o inspetor precisa apontar o pé faltando na mesa, o espelhamento da geladeira e mandar a luminária de parede para "não portar".
- **Receita por objeto** (`porte3d/receitas/<objeto>.json`, versionada; é dado nosso). Contém as caixas e cilindros com medidas, a simetria, o modo de textura do nível arte (adesivo ou kit), os recortes do kit, o material e os parâmetros do nível realista, e as correções. O modelador parte da ficha do inspetor, edita a receita, e um script determinístico gera tudo a partir dela. O agente não desenha nada direto.
- **Ferramentas do modelador** (scripts em `porte3d/`, consolidando os experimentos; o Blender monta a malha, faz o UV, assa e renderiza, e o Python compõe as texturas e as folhas):
  - medida do contorno em 0° (o ajuste automático das medidas fica para a fatia 4, se o modelador precisar);
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
- **Crítico** (`.claude/agents/critico-3d.md`, no formato do crítico do Mecanifica). Recebe as imagens e a **lista de peças prometidas da ficha** (nomes e formas, sem a justificativa do modelador). Não lê código nem receita. Responde a perguntas fixas, citando a peça da ficha em cada defeito:
  1. Em 0° está igual ao jogo?
  2. Em 180° está igual ao desenho de trás?
  3. Ao girar, falta alguma parte?
  4. Alguma parte parece chapada (2D)?
  5. Alguma textura aparece fora do lugar, ou há buraco ou emenda?
  6. A proporção está certa?
  7. **Pelo wireframe:** cada peça prometida existe e está no lugar? Há peça flutuando, enterrada ou atravessando outra? A estrutura faz sentido para o objeto (4 pés numa mesa, portas na frente de uma geladeira)? Há peça que deveria ser sólida e é só um plano?
  
  Fecha com JSON: `nota` e `defeitos[{parte, tipo: ausencia|chapado|textura_deslocada|buraco|emenda|proporcao|sobra|estrutura, angulo, vista: textura|wireframe|sobreposicao, onde, evidencia}]`.
- **Estado de cada objeto** (`porte3d/fila.sqlite`). Estados: `fila`, `em_inspecao`, `nao_portar`, `em_modelagem`, `em_critica`, `retrabalho`, `reprovado`, `aguardando_aprovacao`, `aprovado`, `rejeitado`, `publicado`. Guarda a ficha, as notas e o histórico das rodadas.
- **Lista final de reprovados e não portados** (`porte3d/relatorio.py`). Gerada por script a partir dos vereditos, não escrita por agente. Uma linha por objeto: objeto, última nota, motivo principal (o defeito mais grave da última rodada, ou o motivo do inspetor).
- **Galeria de aprovação.** Página local com a animação girando, a folha e o veredito do crítico. Botões aprovar e refazer, com comentário.
- **Variantes e qualidade** (decidido em 2026-10-12, depois da amostra da geladeira em 3 cores × 3 estados). Os objetos se organizam em:
  1. **família** (ex.: geladeira);
  2. **forma**: uma receita de geometria por forma (comum, mini, grande, industrial...). É feita uma vez só, e as variantes reaproveitam a malha;
  3. **cor**: ligada aos sprites que o jogo já tem (`GroupName`: White, Blue, Green, Red, Steel...);
  4. **estado**: os presets `desgaste` e `ferrugem` dos materiais. No pack do jogo entram só **usada** e **enferrujada**. A **nova** fica fora e reservada para um mod futuro. O estado é uma opção do pack inteiro, já que o jogo não tem sprite por estado; sortear por objeto exigiria mudar o Viewpoint;
  5. **nível gráfico** (arte, realista);
  6. **qualidade**, que é a resolução da textura: baixa 512, média 1024 (padrão) ou alta 2048. Escolhida no pack, porque o Viewpoint carrega todos os modelos na placa de vídeo.

- **Pack** (mod próprio, ex. `PZ3DObjects`), com uma opção para escolher o nível gráfico (dois packs registrados, um por nível; só o escolhido fica ativo):
  - `pack.manifest` com valores **separados por vírgula**;
  - Lua de cliente que chama `Viewpoint.ModelPacks.register("PZ3DObjects", "media/.../pack.manifest")`;
  - uma ligação por sprite de cada direção.
  
  Nada é gravado na pasta do Viewpoint da Workshop.

## Regras do despacho em massa

Valem desde o piloto, para a esteira escalar sem perder controle:

1. **Orquestração por script, não por agente.** Um script (`porte3d/fila.py`) faz as transições de estado e distribui os objetos. Os agentes só recebem um objeto, trabalham nos arquivos daquele objeto e devolvem. Nenhum agente edita arquivo compartilhado.
2. **Contratos validados.** A receita tem esquema JSON. O veredito do crítico também, e veredito fora do esquema é recusado e refeito. As folhas têm nome e layout fixos.
3. **Crítico independente.** Ele não vê a receita nem a justificativa do modelador; vê as imagens e a lista de peças prometidas da ficha. Recalibra com os casos conhecidos a cada mudança nas perguntas.
4. **Amostragem humana e minha.** Em cada lote, confiro visualmente uma amostra dos aprovados pelo crítico antes de mandar para a galeria (regra de não aceitar nota sem olhar). Medimos a concordância crítico × usuário; com concordância alta e estável, a galeria passa a mostrar só os casos duvidosos.
5. **Lotes pequenos e limites.** Lotes de 10 a 20 objetos, no máximo 3 a 4 agentes ao mesmo tempo (já vimos agentes disputando CPU), tempo máximo por objeto e por agente, e no máximo 3 rodadas de retrabalho.
6. **Freio automático.** Se mais da metade de um lote cair em "precisa de humano", a esteira para e o problema vira ajuste da ferramenta, não mais rodadas.
7. **Variantes primeiro.** Objetos com a mesma forma e cores diferentes (mesmo tileset/GroupName) reaproveitam a geometria e só trocam a textura. Um modelo aprovado vira vários.
8. **Prioridade.** Primeiro o que aparece em toda casa: cozinha, eletrodomésticos e móveis com geometria, ordenados por número de variantes. O usuário pode furar a fila a qualquer momento com o que mais incomoda no jogo.
9. **Git por lote.** As receitas, os vereditos e o histórico são commitados ao fim de cada lote. As imagens e texturas derivadas do jogo ficam fora do git.
10. **Despacho em massa só depois do piloto aprovado.** Os lotes de produção (fatia 6) só rodam depois que a calibração e o piloto passarem. O usuário precisa pedir explicitamente um workflow ("use um workflow"), porque são dezenas de agentes.

## Incluído

- Biblioteca `porte3d` (receita → modelo → OBJ/MTL/PNG + folhas), com testes.
- Mod próprio mínimo e prova no jogo. Foi adiada a pedido do usuário em 2026-10-12, porque tudo é regerado da receita. Recomendação: conferir 1 objeto no jogo antes do primeiro lote grande.
- Produção em lotes nas categorias de casa (móveis, eletrodomésticos, cozinha, banheiro e caixas). São cerca de 1.188 sprites, 290 objetos e 120 formas. Começa por cozinha e eletrodomésticos, e pelas 12 formas de geladeira.
- Agentes inspetor, modelador e crítico, mais a skill do laço.
- Calibração do crítico com casos conhecidos, gerados pela própria biblioteca no formato das folhas (`porte3d/calibracao/`), antes de confiar nele. Ele precisa reprovar:
  - a mesa sem os pés de trás, que **o wireframe** tem que denunciar;
  - a mesa com um pé chapado (um plano em vez de um bloco);
  - a geladeira com a traseira errada (a frente repetida atrás).
  
  E precisa aprovar a mesa e a geladeira boas.
- Fila, estados e galeria de aprovação.
- Piloto com 10 objetos de caixa com geometria: geladeiras, fogões, máquinas, balcões, armários, mesas e caixotes, nos dois níveis.
- Geradores de material do nível realista no Blender: madeira (feito no teste), metal e tecido no piloto; os demais entram conforme a fila pedir.
- Limpeza do que o Módulo 05 antigo gravou na pasta da Workshop.

## Excluído

- Objetos sem geometria, finos ou vazados (luminárias, cortinas, plantas, cadeiras de perninha). Vão para um plano seguinte.
- Móveis de 2 ou mais tiles (`SpriteGridPos`). Também vão para um plano seguinte.
- Automação do cliente para print no jogo. A conferência no jogo é do usuário, por enquanto.
- Publicar o mod na Workshop. Ver o risco de arte do jogo abaixo.

## Gate de saída

1. (Fatia 7) O objeto de prova aparece em 3D no jogo. O log do Viewpoint mostra modelos de pack na GPU (`model packs N models`, N > 0) e o usuário confirma visualmente com um print (F9).
2. Na calibração, o inspetor aponta os problemas conhecidos (pé faltando, espelhamento, luminária "não portar"), e o crítico reprova os 3 casos ruins e aprova os 2 casos bons.
3. O piloto passa 10 objetos pela esteira nos dois níveis. Pelo menos 7 são aprovados pelo usuário na galeria em cada nível.
4. Cada objeto tem ficha do inspetor, receita versionada, histórico de rodadas e veredito do crítico registrados, e a lista final de reprovados e não portados é gerada por script.
5. Nada é gravado na pasta do jogo nem na do Viewpoint da Workshop, e a arte extraída do jogo fica fora do git.
6. `python planos/check.py` passa.
7. Os lotes de produção rodaram nas categorias de casa, e todos os aprovados aparecem no jogo (fatia 7), com a troca de nível funcionando.

## Fatias

1. **Biblioteca `porte3d`:** receita, malha no Blender, textura dos dois níveis, export OBJ/MTL/PNG e folhas, consolidando `teste_adesivo*`, `teste_manual_mesa*` e `blender_mesa_nivel3.py`. Prova: a mesa e a geladeira saem pela biblioteca, nos dois níveis.
2. **Inspetor e crítico:** as definições dos agentes, o vocabulário comum (peças prometidas, tipos de defeito) e a calibração dos dois com os casos conhecidos.
3. **Modelador, laço, fila e relatório:** a skill `porte-3d`, os estados e a lista final de reprovados.
4. **Galeria e piloto de 10 objetos.**
5. **Variantes:** cor e estado reaproveitando a malha da forma, e a qualidade (512, 1024 ou 2048).
6. **Produção em lotes** nas categorias de casa, por workflow pedido pelo usuário.
7. **Prova no jogo e pack:** mod próprio, pack.manifest e register. O usuário confere. Aqui se descobre a escala, os eixos, a orientação do UV e como o Viewpoint ilumina o modelo. Adiada a pedido do usuário em 2026-10-12; se der errado, tudo é regerado das receitas.
8. **Fechamento.**

## Riscos e parada

- **O Viewpoint não carrega ou desenha errado o OBJ na fatia 7** (escala, eixos, textura). Parar e investigar o formato no `Viewpoint.jar` (`viewpoint.packs.*`). Como a prova ficou para o fim, o risco é regerar tudo: custa tempo de máquina, mas não o trabalho dos agentes, porque as receitas continuam valendo.
- **O crítico não separa bom de ruim na calibração.** Ajustar as perguntas. Se ainda assim falhar, a aprovação fica toda com o usuário e o crítico vira só uma triagem.
- **Arte do jogo dentro do mod.** As texturas são derivadas da arte da The Indie Stone. Para uso pessoal tudo bem; publicar na Workshop exige decidir antes, porque muitos mods fazem isso, mas é uma decisão do usuário.
- **Direções espelhadas** (E/W são espelho de S/N). Ligar o mesmo modelo girado pode mostrar o objeto "ao contrário" do desenho 2D. Conferir na prova da fatia 7.

## Fechamento

Preencher somente ao concluir, cancelar ou congelar.
