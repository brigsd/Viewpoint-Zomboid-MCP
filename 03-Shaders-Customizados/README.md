# 🎨 Módulo 03: Shaders Customizados

Três shaderpacks de pós-processamento criados para a pipeline OpenGL do **Viewpoint** ([Módulo 02](../02-Viewpoint-PrimeiraPessoa/)). Cada pack herda do shader `default` do Viewpoint (`base=default`) e substitui o estágio final de cor (`post.frag`).

| Pack | Estilo | Destaques |
| :--- | :--- | :--- |
| [`bleak-horror`](./bleak-horror/) | Terror claustrofóbico | Dessaturação, sombras frias, contraste alto, vinheta forte, film grain |
| [`photorealism`](./photorealism/) | Realismo cinematográfico | Tonemapping ACES, vibrance, nitidez, bloom suave, dispersão de lente |
| [`ultra-performance`](./ultra-performance/) | Alto FPS | Desliga volumétricos, GI, bloom e nuvens; TAA + nitidez leve |

---

## 📂 Estrutura de um Pack

```text
<nome-do-pack>/
├── pack.properties     # Manifesto: nome, descrição, opções do menu e (opcional) flags de pipeline
└── shaders/
    └── post.frag       # Shader GLSL 330 de pós-processamento
```

O `post.frag` inclui bibliotecas do shader base (`lib/camera.glsl`, `lib/common.glsl`, `lib/fog.glsl`, `lib/fog_amount.glsl`) e recebe cada opção do menu como um `#define OPTION_<NOME>`.

---

## 🎛️ Opções de Cada Pack

Todas as opções aparecem na janela de configurações do Viewpoint (tecla **`DELETE`**).

### 🩸 `bleak-horror`

| Opção | Padrão | Faixa |
| :--- | :--- | :--- |
| Exposure | `0.9` | 0.5 – 1.5 |
| Contrast | `1.35` | 1.0 – 1.8 |
| Desaturation | `0.45` | 0.0 – 1.0 |
| Cold Slate Shadows | `0.4` | 0.0 – 1.0 |
| Vignette | ligado | — |
| Vignette strength | `0.85` | 0.2 – 1.5 |
| Film Grain | ligado | — |
| Grain amount | `0.04` | 0.01 – 0.15 |

### 🎬 `photorealism`

| Opção | Padrão | Faixa |
| :--- | :--- | :--- |
| Exposure | `1.0` | 0.5 – 2.0 |
| Contrast | `1.12` | 1.0 – 1.5 |
| Saturation | `1.06` | 0.5 – 1.6 |
| Vibrance | `0.2` | 0.0 – 0.8 |
| Smart Clarity (Sharpen) | `0.3` | 0.0 – 0.8 |
| Natural Bloom Haze | `0.4` | 0.1 – 1.0 |
| Lens Dispersion | `0.001` | 0.0 – 0.005 |

Os dois packs acima também expõem as opções de pipeline herdadas do `default` (sombras do sol, resolução de sombra, sombra da lanterna e das lâmpadas, volumétricos, god rays, poças, densidade de chuva e anti-aliasing).

### ⚡ `ultra-performance`

| Opção | Padrão | Valores |
| :--- | :--- | :--- |
| Exposure | `1.0` | 0.5 – 1.5 |
| Smart Sharpening (DLAA-style) | `0.4` | 0.0 – 0.8 |
| Sun shadows | ligado | — |
| Shadow resolution | `1024` | 1024 / 2048 |
| Anti-aliasing (TAA) | ligado | — |
| Rain density | `75` | 25 / 50 / 75 / 100 |

Este pack também fixa a pipeline em modo leve: 1 cascata de sombra, sem sombra da lanterna nem das lâmpadas, sem volumétricos, nuvens, iluminação indireta (GI) ou bloom. As poças e as lâmpadas distantes continuam ligadas.

---

## 🛠️ Instalação

Copie as três pastas para o diretório de shaderpacks do Viewpoint:

```text
%USERPROFILE%\Zomboid\viewpoint-shaderpacks\
├── bleak-horror\
├── photorealism\
└── ultra-performance\
```

Depois, no jogo, ative a primeira pessoa (`O`), abra as configurações (`DELETE`) e escolha o pack.

> [!TIP]
> O Viewpoint tem **hot-reload** (*ShaderWatch*). Edite e salve um `post.frag` com o jogo aberto e a imagem atualiza na hora, sem reiniciar.

> [!WARNING]
> Se o nome do arquivo ou a estrutura estiverem errados, o Viewpoint volta silenciosamente para o shader `default`. Veja [GOTCHAS.md §8](../GOTCHAS.md).

---

## 🔗 Relação com o DLSS

O `ultra-performance` é a alternativa nativa e segura ao DLSS 5 Swapper, que não é compatível com o OpenGL/JVM do Zomboid. Explicação completa no [Módulo 04](../04-DLSS5-Swapper-Bridge/).
