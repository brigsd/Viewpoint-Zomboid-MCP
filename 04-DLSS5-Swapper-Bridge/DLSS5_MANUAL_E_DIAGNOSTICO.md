# 🧠 MÓDULO 04: DLSS 5 Swapper, Upcaling Neural & Project Zomboid

Este documento detalha o funcionamento do **DLSS 5 Swapper**, a ciência por trás do DLSS e como ele se relaciona tecnicamente com o *Project Zomboid Build 42*.

---

## 📍 Localização do Utilitário no seu Sistema
O software responsável pelo gerenciamento e injeção do DLSS 5 está instalado em:
```text
C:\Users\micro\AppData\Local\Programs\DLSS 5 Swapper\
```
*(Executável principal: `DLSS 5 Swapper.exe`)*

---

## 🔬 O que é o DLSS 5 e como o Swapper funciona?

O programa **DLSS 5 Swapper** é uma ferramenta avançada de injeção que combina várias tecnologias de ponta:

1. **ReShade 6.8+ (Addon Support):** Intercepta as chamadas gráficas da aplicação.
2. **DLSS 5 Feeder (`dlss5-feed.addon64`):** Um add-on para ReShade que constrói um "contrato sintético" do NVIDIA DLSS para jogos que não possuem suporte nativo de fábrica. Ele extrai vetores de movimento (*motion vectors*) e dados do buffer de profundidade (*depth buffer*).
3. **Consumidor Neural (RenoDX / Deep Fried Chicken):** Módulo que envia os dados para as bibliotecas de inteligência artificial da NVIDIA.
4. **NVIDIA Streamline & Runtimes:**
   * `nvngx_dlss.dll`: O modelo de Super Resolution (reconstrução espacial/temporal por IA).
   * `nvngx_dlssg.dll`: Frame Generation (geração de quadros intermediários em GPUs RTX série 40).
   * `nvngx_dlssnr.dll`: Ray Reconstruction (desruído e reconstrução neural).

---

## ❓ O DLSS deixa o jogo mais realista?

### ❌ O que o DLSS NÃO faz:
* **Não muda iluminação, sombras ou cores:** O DLSS não é um filtro estético. Ele não adiciona clima sombrio, não muda a névoa nem cria luzes novas. Isso é papel exclusivo dos **Shaders** (Módulo 03).

### ✔️ O que o DLSS REALMENTE faz pelo realismo:
* **Elimina o "Shimmering" (Cintilação):** O maior vilão visual em jogos isométricos ou com folhagens (árvores, cercas de arame, grades) é o serrilhado que fica tremendo e piscando conforme a câmera anda. O algoritmo neural do DLSS/DLAA estabiliza completamente esses pixels, deixando o mundo sólido e limpo como um filme.
* **Nitidez Extrema sem Ruído (DLAA):** Rodando em 100% da resolução nativa, o DLSS funciona como o melhor anti-serrilhado da indústria.
* **Ganha muito FPS (Modos Performance/Quality):** Renderiza o jogo internamente em resolução menor (ex: 1080p) e reconstrói para 1440p ou 4K com inteligência artificial, liberando processamento da GPU para rodar shaders pesados sem perder fluidez.

---

## ⚠️ Análise de Compatibilidade com o Project Zomboid

O Project Zomboid tem uma particularidade crítica em relação à maioria dos jogos modernos:

| Característica | Jogos Padrão com DLSS | Project Zomboid Build 42 |
| :--- | :--- | :--- |
| **API Gráfica** | DirectX 11, DirectX 12 ou Vulkan | **OpenGL 3.3+ (via Java LWJGL)** |
| **Ambiente de Execução** | C++ Nativo (PE Executable direto) | **Máquina Virtual Java (OpenJDK 25)** |
| **Swapchain de Frames** | Encadeada no driver DirectX/Vulkan | Renderizada em FBOs internos do Java |

### Diagnóstico Técnico:
* O DLSS Feeder e o NVIDIA Streamline foram desenhados especificamente para **Direct3D (DirectX)** e **Vulkan**.
* Injetar o ReShade com hooks de DXGI no Project Zomboid muitas vezes não encontra o dispositivo de renderização (pois o jogo cria um contexto OpenGL puro via LWJGL).
* Forçar wrappers (como OpenGL32 do ReShade) pode disputar chamadas com a JVM e causar fechamentos inesperados (*silent crash*).

---

## 🛡️ A Solução Integrada na Nossa Suíte (Módulo 03)

Para entregar os **mesmos benefícios do DLSS** (estabilidade de imagem, ausência de cintilações e altíssimo FPS) sem colocar em risco a estabilidade do Java do Project Zomboid, criamos dentro do **Módulo 03** o perfil:

### ⚡ Shaderpack `ultra-performance` (DLAA-Style):
1. **Temporal Anti-Aliasing (TAA) Nativo:** O mod *Viewpoint* (Módulo 02) já possui sua própria implementação de TAA e vetores de movimento calculados diretamente na GPU em OpenGL, eliminando o serrilhado das árvores e cercas.
2. **Smart Sharpening Filter:** Filtro de nitidez inteligente de alta passagem (*high-pass filter*) programado em GLSL que restaura microdetalhes nas bordas sem gerar ruído.
3. **Pipeline Otimizada:** Reduz custos de luz volumétrica e sombra mantendo o jogo rodando a **100+ FPS cravados**, sem depender de DLLs externas injetadas.

---

## 🕹️ Como usar o DLSS 5 Swapper se quiser testar:

Caso você queira testar a injeção do DLSS 5 no Project Zomboid ou em qualquer outro jogo instalado na sua máquina:
1. Abra o aplicativo:
   ```text
   C:\Users\micro\AppData\Local\Programs\DLSS 5 Swapper\DLSS 5 Swapper.exe
   ```
2. Na lista de jogos detectados, localize o jogo desejado.
3. Clique em **Inject / Injetar DLSS 5**. O programa instalará o ReShade com os add-ons do Feeder na pasta do executável.
4. Para desfazer: abra o aplicativo novamente, selecione o jogo e clique em **Restore / Desinjetar**, retornando a pasta do jogo ao estado 100% original.
