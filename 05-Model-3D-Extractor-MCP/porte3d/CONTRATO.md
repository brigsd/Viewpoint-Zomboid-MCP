# Contrato da biblioteca `porte3d`

Este arquivo fixa o que cada parte da biblioteca entrega para a outra. Quem mexe numa parte não muda o contrato sem atualizar este arquivo e os testes.

## Convenções

- **Unidade:** metro. 1 tile do jogo = 1 m. O arquivo `tileGeometry.txt` do jogo usa 1/10000 de tile, e a conversão é dividir por 10000.
- **Eixos da receita** (os mesmos do Blender):
  - `x` = leste, igual ao X do jogo;
  - `y` = norte, igual a −Z do jogo (o Z do jogo aponta para o sul);
  - `z` = cima, igual ao Y do jogo.
  
  A origem é o centro do tile, no chão.
- **Conversão** de um ponto do jogo `(X, Y, Z)` em 1/10000 de tile para a receita: `(X/1e4, −Z/1e4, Y/1e4)`.
- **Rotação do jogo** (`rotate = AxBxC` em 1/10000 de grau): `R = Rx(A)·Ry(B)·Rz(C)` nos eixos do jogo, regra da mão direita (medido em 715 sprites com caixa girada; ver `acervo.formas`). Como a troca de eixos jogo → receita é uma rotação própria, um giro `B` em torno do Y do jogo vira `+B` em torno do `z` da receita. Atenção: o `rot_y` do `experimentos3d/harness.py` usa o sentido contrário.
- **`rot` da receita:** `[rx, ry, rz]` em graus, Euler XYZ do Blender (`R = Rz·Ry·Rx`), em torno do centro da peça.
- **Direções:** a receita descreve o objeto virado para **S** (a vista de frente do desenho). O giro de cada direção em torno de `z`, em graus, é `S = 0`, `E = +90`, `N = 180`, `W = −90`. É o `ANGLE` do harness com o sinal trocado, porque o eixo `y` da receita é o −Z do jogo.
- **Câmera do jogo:** ortográfica, olhando do sudeste para o noroeste, 30° acima do horizonte. No quadro 2x de 128×256 px:

  ```text
  sx = 64 + 64·(x + y)
  sy = 224 + 32·(x − y) − 78,38·z
  ```

  Um objeto girado `a` graus em torno de `z` é projetado com o ponto já girado.
- **Desenho de trás:** o jogo posiciona o objeto virado para N por conta própria, a alguns centímetros do objeto S girado 180°. `preparar.py` mede esse deslocamento pela geometria do jogo (`acervo.deslocamento_tras`) e grava `deslocamento_tras` = [dx, dy] na receita expandida. A textura de trás, a prévia e a vista de 180° usam o mesmo deslocamento.

## Receita (`receitas/<id>.json`)

O esquema completo está em `receita.schema.json`, e `receita.py` valida a receita e expande os espelhamentos. Os campos:

| campo | o que é |
|---|---|
| `versao` | sempre `1` |
| `id` | nome do modelo (`[a-z0-9_]+`), usado nos arquivos de saída |
| `sprites` | `{direção: nome do sprite}` das direções conhecidas; `S` é obrigatória |
| `tras` | `"N"` (usa o desenho de trás) ou `"simetrico"` (usa o de frente girado 180°) |
| `material` | material padrão das peças no nível realista |
| `cores` | opcional, `{material: [r,g,b]}` em sRGB 0–255; sem isso, a cor vem da arte |
| `pecas` | lista de peças (abaixo) |
| `arte` | `{"modo": "adesivo"}` ou `{"modo": "kit", "recortes": {...}, "faces": {...}}` |
| `realista` | opcional, `{"materiais": {nome: {"tipo": madeira\|metal\|tecido\|liso, "desgaste": 0..1}}}`; `desgaste` põe sujeira, tinta lascada e ferrugem |

### Peças

Campos comuns a todas as formas:

- `nome`: único na receita; as cópias espelhadas ganham sufixo `.x`, `.y` ou `.xy`.
- `material`: opcional; se faltar, usa o `material` da receita.
- `espelhar`: lista com `"x"` e/ou `"y"`. Cria cópias espelhadas no plano `x = 0` e/ou `y = 0`.
- `rot`: opcional, `[rx, ry, rz]` em graus, Euler XYZ do Blender, girando em torno do centro da peça.
- `chanfro`: raio do arredondamento das arestas, em metros, padrão 0.
- `veio`: opcional, `"x" | "y" | "z"`, direção do comprimento da madeira. Se faltar, é o maior lado da peça.
- `tabuas`: opcional, número de tábuas lado a lado na face maior.
- `arte_cor`: opcional. Se `true`, no nível arte a peça fica com a cor lisa do seu material, tirada de `cores`, em vez de receber o desenho. Serve para vidro e partes transparentes, em que o desenho mostra o que está atrás.

As formas:

- `caixa`: `min`, `max`, mais o opcional `afinar` = `{"quanto": m, "lados": ["+x","-x","+y","-y"]}`. Os lados listados entram `quanto` metros na base (z mínimo), como um pé que afina para baixo.
- `prisma`: `perfil` = lista de pontos `[a, z]` no plano vertical, `eixo` = `"x"` ou `"y"` (direção da extrusão), e `de` e `ate` (o intervalo nesse eixo). O `a` é a coordenada horizontal que sobra, ou seja, `x` quando o eixo é `y` e `y` quando o eixo é `x`.
- `cilindro`: `centro` `[x,y,z]` (centro da base), `raio`, `altura`, `eixo` (`"x" | "y" | "z"`, padrão `"z"`), `raio_topo` opcional (para tronco de cone) e `segmentos` (padrão 24).

### Arte em modo kit

- `recortes`: `{nome: {"peca": nome, "face": "+x|-x|+y|-y|+z|-z", "recorte": [u0,v0,u1,v1], "limpar_transparente": bool}}`. É um pedaço de uma face de uma peça, desentortado do desenho de frente; `u,v` são frações da face.
- `faces`: `{peça (sem sufixo de espelho): {"+z": recorte, "lados": recorte, "-z": recorte, ...}}`. A chave `lados` vale para as 4 faces verticais.
- `repetir`: opcional, `{recorte: metros}`. O recorte se repete a cada tantos metros ao longo da face.

## Pasta de trabalho de um objeto (`<saida>/<id>/`)

| arquivo | quem escreve | o que é |
|---|---|---|
| `entrada/frente.png`, `entrada/tras.png` | `preparar.py` | quadros 128×256 do jogo (frente S; trás N ou S), já com `bleed` |
| `entrada/frente_original.png`, `entrada/tras_original.png` | `preparar.py` | quadros sem `bleed`, para comparação nas folhas; `tras_original` é sempre o desenho N do jogo quando ele existe, mesmo com `tras = simetrico` |
| `entrada/receita.json` | `preparar.py` | receita expandida (espelhos já aplicados), com cores resolvidas |
| `buffers/*.npy` | Blender, etapa 1 | por texel do atlas: `posicao` (H,W,3), `normal` (H,W,3), `peca` (H,W) com índice da peça ou −1, `vis_0` e `vis_180` (H,W) com a luz direta crua de um sol na direção da câmera do jogo em 0° e 180° (0 = não vê; `texturas.py` normaliza as duas pela mesma escala), `ao` (H,W), `albedo` (H,W,3) linear do realista |
| `malha.obj`, `cena.blend` | Blender, etapa 1 | malha juntada com UV (um `usemtl` por peça) e a cena para a etapa 2 |
| `pecas.json` | Blender, etapa 1 | `[{"indice", "nome", "cor_fio": [r,g,b]}]` |
| `arte.png`, `realista.png` | `texturas.py` | texturas finais do atlas, sRGB |
| `<id>_arte.obj/.mtl`, `<id>_realista.obj/.mtl` | `texturas.py` | modelos finais, uma malha só, `map_Kd` para a textura |
| `vistas/<nivel>_<ang>.png` | Blender, etapa 2 | 128·E × 256·E px, fundo transparente, câmera do jogo; `nivel` ∈ `arte` (cor pura da textura, sem luz), `realista` (com luz), `fio`, `fio_sobre_arte`; `ang` com 3 dígitos (000, 045, …, 315); o objeto gira `+ang` em `z` |
| `folhas/*.png`, `folhas/giro_<nivel>.gif` | `folhas.py` | folhas para o crítico (ver `folhas.py`) |
| `medidas.json` | `folhas.py` | `{"contorno_0": IoU, "cor_0": diferença média}` em 0° |
