# 🗃️ Acervo de objetos do jogo

Catálogo local de todos os objetos do mundo do *Project Zomboid Build 42.21*: imagem, propriedades, categoria, geometria 3D e mapa de profundidade. É a base para trocar os sprites que viram "papel de parede" na câmera 3D do Viewpoint por modelos 3D fiéis e em escala.

## Montar

```bash
python 05-Model-3D-Extractor-MCP/acervo/build_acervo.py
```

Leva ~17 s e grava tudo em `acervo/data/` (~550 MB). Essa pasta fica fora do git, porque é conteúdo extraído do jogo. A pasta do jogo é só lida.

```bash
python 05-Model-3D-Extractor-MCP/acervo/viewer.py
```

Gera `data/viewer/index.html`, uma página para navegar no acervo: miniaturas, filtro por categoria e tileset, busca e um painel com a geometria desenhada por cima da imagem. Ela carrega arquivos vizinhos; se o navegador bloquear em `file://`, sirva a pasta com `python -m http.server` dentro de `data/viewer`.

## O que tem (42.21)

| Dado | De onde vem | Quantidade |
| :--- | :--- | ---: |
| Objetos (tiles) | `media/*.tiles` e `*.tiles.txt` | 42.544 |
| Imagens (PNG, 2x quando existe) | `media/texturepacks/*.pack` | 40.233 |
| Formas da geometria 3D (caixa, cilindro, polígono) | `media/tileGeometry.txt` | 11.793, em 5.158 objetos |
| Mapas de profundidade por objeto | `media/depthmaps/DEPTH_*.png` | 5.260 próprios; 36.853 objetos com profundidade contando as atribuições |

| Categoria | Objetos | Com imagem | Com geometria |
| :--- | ---: | ---: | ---: |
| móveis | 2.161 | 2.047 | 1.257 |
| eletrodomésticos | 880 | 705 | 345 |
| containers | 612 | 604 | 361 |
| cozinha | 547 | 547 | 129 |
| banheiro | 58 | 55 | 45 |
| iluminação | 1.607 | 1.529 | 269 |
| construção, decoração, vegetação, portas/janelas e outros | 36.679 | 33.152 | 2.752 |

Os objetos sem imagem não têm imagem em nenhum arquivo do jogo (variantes "acesas" `_on`, `crafted_03`, índices além do que o pack traz). O motivo de cada um está em `data/report_missing.md`.

## Como os dados se encaixam

Tudo verificado em `align_check.py` (resultados em `data/align/`):

- **Imagem:** o quadro completo tem 128x256 (2x). O recorte fica em `offset_x/y` dentro dele. O centro do tile no chão está em (64, 224).
- **Geometria:** unidades de 1/10000 de tile. X e Z vão de -5000 a 5000, com o centro do tile em 0; Y é altura (0 = chão). X aponta para a direita-baixo da tela (leste) e Z para a esquerda-baixo (sul).
- **Projeção para a tela (2x):** `sx = 64 + 0.0064·(X − Z)` e `sy = 224 + 0.0032·(X + Z) − 0.007838·Y`.
- **Profundidade:** quanto menor o cinza, mais perto da câmera. `cinza ≈ 190 − 0.0064·(X+Z) − 0.00523·Y`, o que dá ~104 níveis por tile.
- **Prova de alinhamento** (sobreposição da geometria com a imagem):

| Objeto | Geometria × imagem | Geometria × profundidade |
| :--- | ---: | ---: |
| cama | 0,88 | 0,98 |
| mesa | 0,73 | 0,98 |
| geladeira | 0,96 | 0,97 |
| prateleira | 0,88 | 0,95 |
| caixa | 0,86 | 0,88 |

Em vegetação e portas/janelas a geometria não representa o volume do objeto (~0,55 contra a profundidade). Para essas categorias, o volume deve vir do mapa de profundidade.

## Arquivos

| Arquivo | Papel |
| :--- | :--- |
| `schema.sql` | Estrutura do catálogo (`data/acervo.sqlite`) |
| `build_acervo.py` | Monta tudo (`--only tiles|textures|depth`) |
| `extract_textures.py` | Lê os `.pack` e extrai os PNGs |
| `extract_tiles.py`, `categorize.py` | Definições, propriedades, geometria e categorias |
| `extract_depth.py` | Recorta os mapas de profundidade por objeto |
| `align_check.py` | Prova de alinhamento entre geometria, imagem e profundidade |
| `viewer.py`, `report_missing.py` | Página de navegação e relatório dos objetos sem imagem |

```bash
python -m unittest discover -s 05-Model-3D-Extractor-MCP/acervo/tests
```

Roda os 49 testes, todos com dados sintéticos.
