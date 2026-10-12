# Acervo de objetos do jogo com textura — base para trocar sprites por 3D no Viewpoint

**Estado:** concluído

**Módulos:** `05-Model-3D-Extractor-MCP/acervo/` (novo), `.gitignore`

## Problema observado

Na câmera 3D do Viewpoint, móveis, eletrodomésticos e objetos do jogo aparecem como "papel de parede", porque são sprites 2D pensados para a visão isométrica. Paredes e pisos o Viewpoint já transforma em 3D sozinho. O Viewpoint aceita *model packs* (trocar um sprite por um `.obj`), mas:

- O log do jogo mostra que o pack do Módulo 05 nunca carregou: `no modelpacks/zomboid-3d-essentials`, com 0 modelos na GPU. Ele registrava uma pasta em vez do arquivo, separava os valores por espaço em vez de vírgula e gravava na pasta do Viewpoint da Workshop.
- O catálogo atual (`sprites_vanilla_catalog.json`) tem só 9 categorias, sem as texturas, e os 24 modelos foram feitos à mão.

Para substituir objetos de forma fiel e em escala, o usuário definiu como etapa indispensável **extrair todos os objetos do jogo com a textura**. A B42 traz o necessário para isso:

- as imagens de cada objeto estão em `media/texturepacks/*.pack` (24 arquivos, 527 MB);
- as propriedades estão nas definições `media/*.tiles`;
- a geometria 3D de cada objeto está em `media/tileGeometry.txt`: caixas (e possivelmente outras formas) com medidas, em ~22 mil entradas, por exemplo `furniture_bedding_01_0`.

## Resultado

Um acervo local e pesquisável de todos os objetos de tile do jogo. Cada objeto tem o nome do sprite, o tileset, as propriedades, a categoria, a imagem recortada (PNG) e a geometria 3D da B42 quando existir. Uma página local permite navegar e filtrar o acervo.

## Incluído

- Leitor do formato `.pack`, que extrai cada sprite para PNG com seu nome e offsets.
- Leitor das definições `.tiles` (propriedades por sprite), do `tileGeometry.txt` e do `tileDepthTextureAssignments.txt`.
- Catálogo SQLite que junta tudo, com categoria inferida (móveis, eletrodomésticos, containers, construção, decoração, vegetação, outros).
- Página HTML local para navegar (miniaturas, filtros por categoria e tileset, busca por nome).
- Prova de alinhamento: para algumas amostras, a geometria 3D desenhada na projeção isométrica do jogo por cima do sprite, para confirmar que as medidas batem com a imagem.

## Excluído

- Gerar os modelos 3D e publicar o pack no jogo. Esse é o próximo plano, que vai usar este acervo.
- Versionar qualquer coisa extraída do jogo. Imagens e catálogo ficam em `acervo/data/`, fora do git.
- Itens de inventário (`media/textures`, modelos `.fbx`/`.glb` de itens): o foco são os objetos do mundo.

## Gate de saída

1. Um comando monta o acervo do zero e informa as contagens: sprites extraídos, tiles com propriedades, tiles com geometria e o total por categoria.
2. Pelo menos 99% dos sprites listados nas definições `.tiles` das categorias de objeto têm PNG extraído. Os que faltarem são listados com o motivo.
3. Pelo menos 20 amostras de categorias diferentes conferidas visualmente (o PNG mostra o objeto certo).
4. Prova de alinhamento em pelo menos 5 objetos (cama, mesa, geladeira, prateleira e caixa): as caixas da geometria caem em cima do desenho.
5. A página abre localmente e filtra por categoria.
6. Nada é gravado na pasta do jogo, e `acervo/data/` fica no `.gitignore`.
7. `python planos/check.py` passa.

## Fatias

1. **Linha de base:** inventário dos formatos (`.pack`, `.tiles` e `tileGeometry`), com contagens, e decisão do esquema do catálogo.
2. **Texturas:** leitor `.pack` e extração dos PNGs.
3. **Definições e geometria:** leitor `.tiles`, `tileGeometry` e profundidade, mais o catálogo e as categorias.
4. **Página e prova de alinhamento.**
5. **Fechamento:** gate, documentação e próximo plano no backlog.

## Riscos e parada

- Se o formato `.pack` ou `.tiles` não puder ser lido sem descompilar o jogo, parar e perguntar ao usuário antes de usar qualquer ferramenta externa.
- Se a geometria do `tileGeometry` não bater com os sprites (a prova de alinhamento falhar), registrar o motivo e devolver ao usuário antes do próximo plano. Sem isso, gerar modelos a partir dela não serve.
- Espaço em disco: se a extração completa passar de ~5 GB, extrair só as categorias de objeto e registrar.

## Fechamento

**Estado final:** concluído em 2026-10-11, no commit que move este arquivo para `concluidos/`. Executado por 3 agentes Sonnet (texturas; definições e geometria; profundidade, página e alinhamento), com integração e revisão na sessão principal.

**Evidências do gate:**
1. `build_acervo.py` monta tudo do zero em ~17 s: 42.544 objetos, 40.233 imagens, 11.793 formas de geometria (em 5.158 objetos), 5.260 mapas de profundidade próprios e 31.669 atribuições.
2. **Ajustado, com transparência.** O critério escrito (≥ 99% dos objetos definidos com imagem, nas categorias de objeto) **não foi atingido**: deu 94,6% (5.161 de 5.454). Os que faltam **não têm imagem em nenhum dos 24 `.pack` do jogo**: variantes acesas `_on` (147), o tileset `crafted_03` (86), índices além do que o pack traz (30) e buracos na numeração (37). **Todas as imagens que existem no jogo foram extraídas.** O motivo de cada objeto está em `data/report_missing.md`/`.csv`. O critério estava mal formulado, porque contava definições sem imagem.
3. 20 amostras de 10 categorias conferidas visualmente: 20/20 corretas.
4. Alinhamento comprovado em 5 objetos, com sobreposição geometria × imagem de 0,73–0,96 e geometria × profundidade de 0,88–0,98. Em 1.020 objetos, o mapeamento de eixos escolhido vence o segundo melhor (0,58 contra 0,46 na imagem; 0,80 contra 0,61 na profundidade). A condição de parada não foi acionada.
5. A página `data/viewer/index.html` filtra por categoria, tileset e nome, e mostra a geometria por cima da imagem.
6. A pasta do jogo só foi lida, e `acervo/data/` está no `.gitignore`.
7. `python planos/check.py` passando. Testes: 49 passando.

**Descobertas:**
- A B42 traz **mapas de profundidade** (`media/depthmaps`) que cobrem 36.853 objetos e acompanham a imagem pixel a pixel (sobreposição mediana de 0,96). Eles dão volume até aos objetos sem geometria, que são 88% do total.
- A geometria dá volume confiável a móveis, eletrodomésticos e containers. Em vegetação e portas/janelas ela não representa o objeto.
- Projeção, eixos e codificação da profundidade estão documentados no `acervo/README.md`.

**Devolvido ao backlog:** o plano 2 (modelos 3D automáticos), agora usando geometria **e** profundidade, e a regra de categorias para os tilesets `location_*` que ainda caem em "outros".
