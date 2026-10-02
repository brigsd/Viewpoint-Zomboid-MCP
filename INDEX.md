# 🧭 ÍNDICE MODULAR: Project Zomboid 3D & Shaders Suite

Este documento é o **mapa técnico e conceitual** de todos os módulos reunidos nesta suíte centralizada. Cada pasta neste diretório representa um módulo independente e essencial que trabalha em conjunto para entregar a experiência em primeira pessoa e os novos shaders no *Project Zomboid Build 42*.

> [!TIP]
> **Encontrou algum problema ou comportamento inesperado?**  
> Consulte o nosso guia de resolução técnica e pegadinhas em **[GOTCHAS.md](./GOTCHAS.md)** (explica as teclas reais `O` vs `DELETE`, compatibilidade da Build 42.21, assinaturas criptográficas da JVM, comportamento do launcher Steam, regras do DLSS, efeito billboard 2D vs 3D, escala em metros e alinhamento de solo Y=0).

---

## 🏗️ Arquitetura dos Módulos e Esteiras

```text
[Jogo Base Project Zomboid (Java 25)]
         │
         ▼
[Módulo 01: ZombieBuddy]   ──► Injeta o ambiente de execução Java nativo (PREMAIN)
         │
         ▼
[Módulo 02: Viewpoint]     ──► Transforma a câmera isométrica em 3D (1ª e 3ª Pessoa)
         │
         ▼
[Módulo 03: Shaders]       ──► Pós-processamento visual (Horror, Realismo ou Alta Performance)
         │
         ▼
[Módulo 04: DLSS5 Bridge]  ──► Documentação e integração com DLSS 5 Swapper & Upscaling
         │
         ▼
[Módulo 05: 3D MCP Server] ──► Extrator e Injetor de Modelos 3D (.obj) via IA & FastMCP
         │
         ├───► [Esteira Técnica]: Síntese de Malhas (.obj), UVs e pack.manifest
         │
         └───► [Esteira de Inspeção Visual & Auditoria 3D]:
                  ├── Agente Extrator 3D (.agents/extrator-3d.md)
                  ├── Agente Inspetor Visual (.agents/inspetor-visual.md)
                  │      └── Renderização Headless sem UI via Mecanifica
                  │      └── Geração das 4 Vistas em inspecoes/<objeto>/
                  ├── Auditor Humano (.agents/auditor-humano.md)
                  │      └── Validação dos 5 Pilares de QA
                  └── Bancada 3D Interativa (Three.js Orbital via Mecanifica)
```

---

## 📦 Detalhamento dos Módulos

### 1. [`01-ZombieBuddy-Loader`](./01-ZombieBuddy-Loader/)
* **O que é:** O carregador e framework de injeção de bytecode Java para o Project Zomboid.
* **Por que existe:** Os mods convencionais do Zomboid rodam em *Lua*, que possui limitações rígidas de sandbox e não tem acesso direto aos ponteiros da placa de vídeo nem às matrizes de projeção do jogo. O ZombieBuddy adiciona suporte a mods em Java puro de baixo nível.
* **Componentes principais:**
  * `zbNative.dll`: Biblioteca nativa em C/C++ que atua como agente JVM (`-agentlib:zbNative`) para carregar código antes da inicialização do jogo.
  * `ZombieBuddy.jar`: O núcleo do framework responsável pelo runtime patching das classes do Zomboid.
  * Pasta `doc/`: Manuais completos de linha de comando, parâmetros de segurança e política de aprovação de JARs.
* **Local de instalação ativa no sistema:**
  * Arquivos nativos: `C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\`
  * Mod de conteúdo: `C:\Program Files (x86)\Steam\steamapps\workshop\content\108600\3619862853\`

---

### 2. [`02-Viewpoint-PrimeiraPessoa`](./02-Viewpoint-PrimeiraPessoa/)
* **O que é:** O mod principal de transformação da perspectiva do jogo.
* **Por que existe:** Converte a câmera 2.5D clássica em um motor 3D completo em OpenGL moderno, adicionando suporte a visão em **Primeira Pessoa (estilo FPS de terror)** e **Terceira Pessoa (sobre o ombro)**.
* **Recursos inclusos:**
  * Renderizador próprio em OpenGL 3.3 com pipeline PBR e iluminação dinâmica.
  * Mira e crosshair 3D adaptados para combate corporal e com armas de fogo.
  * Menu nativo de inventário/loot no ponto onde a mira aponta.
  * Sistema de carregamento dinâmico de shaders (*ShaderWatch* com hot-reload).
* **Atalhos e Controles no Jogo:**
  * **`O`**: **Ativar / Desativar a Primeira Pessoa** (Toggle ON/OFF principal).
  * **`SHIFT + O`**: Alternar entre **Primeira Pessoa e Terceira Pessoa** (sobre o ombro).
  * **`DELETE`**: Abrir/fechar a **Janela de Configurações do Viewpoint** (seleção de Shaders, FOV, iluminação e efeitos).
  * **`INSERT + O`**: Modo **Câmera Livre** (Free Camera).
  * **`F`**: Interagir / Pegar item onde a mira 3D aponta.
  * **`R`**: Pegar tudo do container mirado.
  * **`F9`**: Captura de tela pelo motor do Viewpoint (salva em `Zomboid/viewpoint-shots/`).
* **Local de instalação ativa no sistema:**
  * Mod de conteúdo: `C:\Program Files (x86)\Steam\steamapps\workshop\content\108600\3809306528\`

---

### 3. [`03-Shaders-Customizados`](./03-Shaders-Customizados/)
* **O que é:** O pacote de pós-processamento visual e estético criado especificamente para a pipeline do Viewpoint.
* **Por que existe:** Permite calibrar a atmosfera visual do apocalipse, aplicando curvas de tonemapping de cinema, correção de cor, efeitos de lente e perfis de otimização de quadros (FPS).
* **Sub-pacotes inclusos:**
  1. **`bleak-horror` (Terror Claustrofóbico):**
     * Dessaturação severa com sombras frias em tom ardósia (*cold slate*).
     * Pretos esmagados e profundos para transformar noites e casas escuras em breu total.
     * Vinheta periférica e granulação analógica de filme (*film grain*).
  2. **`photorealism` (Realismo Cinematográfico):**
     * Curva de tonemapping **ACES** (padrão de pós-produção de cinema).
     * Bloom natural, saturação dinâmica e dispersão ótica microscópica nas bordas da tela.
  3. **`ultra-performance` (Otimizado / Estilo DLSS):**
     * Desativa cálculos volumétricos pesados de iluminação.
     * Mantém o TAA suave ativo combinado com **Smart Sharpening** para manter texturas ultra-nítidas com ganho massivo de FPS.
* **Local de instalação ativa no sistema:**
  * Shaderpacks: `C:\Users\micro\Zomboid\viewpoint-shaderpacks\`

---

### 4. [`04-DLSS5-Swapper-Bridge`](./04-DLSS5-Swapper-Bridge/)
* **O que é:** Manual técnico, diagnóstico e ponte de compatibilidade com o software **DLSS 5 Swapper**.
* **Por que existe:** Documenta o funcionamento do aplicativo localizado em `C:\Users\micro\AppData\Local\Programs\DLSS 5 Swapper\`, que gerencia injeções de ReShade 6.8 + DLSS Feeder (Streamline / RenoDX) para forçar upscaling e reconstrução por IA.
* **Tópicos abordados no manual interno:**
  * O que o DLSS realmente faz (upscaling temporal e DLAA) e o que ele não faz (não altera shaders/luz).
  * Como a API OpenGL (LWJGL) e a JVM do Project Zomboid interagem com o injetor.
  * O papel do shaderpack `ultra-performance` (Módulo 03) como alternativa nativa e 100% segura para obter a nitidez e o ganho de quadros do DLSS sem riscos de instabilidade na JVM.
  * Passo a passo para Injetar ou Restaurar/Desinjetar jogos com o programa.
* **Documento principal:** [DLSS5_MANUAL_E_DIAGNOSTICO.md](./04-DLSS5-Swapper-Bridge/DLSS5_MANUAL_E_DIAGNOSTICO.md)

---

### 5. [`05-Model-3D-Extractor-MCP`](./05-Model-3D-Extractor-MCP/)
* **O que é:** Servidor **MCP (Model Context Protocol)** em Python utilizando o framework **FastMCP**, integrado à esteira de inspeção visual headless via **Mecanifica**.
* **Por que a substituição de 2D por 3D é fundamental no Viewpoint:**
  * Na perspectiva isométrica clássica do Zomboid, sprites 2D planos são suficientes.
  * Porém, em **Primeira Pessoa**, sprites 2D funcionam como meros **"papéis de parede" ou outdoors (billboards achatados)**: ao girar a cabeça ou se aproximar, o objeto não tem profundidade, deforma visualmente, não recebe oclusão de ambiente e revela sua natureza bidimensional de papel.
  * A injeção de **modelos poligonais 3D (`.obj`)** confere **volumetria física real**, vetores de normais consistentes para iluminação PBR dos shaders e colisão visual tangível em combate e saque.
* **Componentes principais:**
  * `server.py`: O servidor MCP em Python com 12 ferramentas para diagnóstico, busca de tiles, geração de malhas, inspeção e injeção de packs.
  * [`objetos-extraidos-vanilla/`](./05-Model-3D-Extractor-MCP/objetos-extraidos-vanilla/): Modelos 3D originais do Zomboid (`.glb`, `.fbx`, `.x`) e catálogo `sprites_vanilla_catalog.json`.
  * 📸 [`objetos-extraidos-vanilla/inspecoes/`](./05-Model-3D-Extractor-MCP/objetos-extraidos-vanilla/inspecoes/): **Nova pasta de inspeções visuais**, armazenando as 4 fotos canônicas de auditoria (`vista_isometrica.png`, `vista_topo.png`, `vista_frontal.png`, `vista_lateral.png`) e laudos técnicos (`auditoria.json`).
  * [`objetos-prontos-3d/`](./05-Model-3D-Extractor-MCP/objetos-prontos-3d/): Biblioteca de modelos poligonais prontos (`.obj` + `.mtl`) dividida em categorias, acompanhada do `pack.manifest` mestre.
  * Pasta `packs/`: Diretório de staging onde novos pacotes 3D são gerados e validados.
  * `README.md`: Manual com o catálogo das ferramentas, esquemas de dados e guia de conexão.
* **Governança da Esteira de Inspeção e Auditoria 3D:**
  * 🤖 **[Agente Extrator 3D](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/extrator-3d.md):** Extração, escala métrica e síntese geométrica.
  * 🔍 **[Agente Inspetor Visual](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/inspetor-visual.md):** Renderização headless sem UI via Mecanifica gerando as 4 vistas oficiais.
  * 👤 **[Protocolo de Auditoria Humana](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/auditor-humano.md):** Homologação dos 5 pilares de qualidade pelo operador humano.
  * 🚀 **[Skill: Esteira de Inspeção 3D](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/skills/esteira-inspecao-3d/SKILL.md):** Passo a passo operacional de ponta a ponta.
* **Local de instalação ativa no sistema:**
  * Servidor MCP: `c:\Users\micro\Desktop\ProjectZomboid-FirstPerson-Suite\05-Model-3D-Extractor-MCP\`
  * Configuração global: `C:\Users\micro\.gemini\config\mcp_config.json`

---

## 🛠️ Como Restaurar Qualquer Módulo

Se você formatar o computador ou precisar restaurar algum módulo:
1. **Para o ZombieBuddy:** Copie `zbNative.dll` e `ZombieBuddy.jar` da pasta `01-ZombieBuddy-Loader\mods\ZombieBuddy\libs\` para a pasta raiz do seu Project Zomboid.
2. **Para o Viewpoint:** Certifique-se de que a pasta `02-Viewpoint-PrimeiraPessoa` esteja vinculada na Workshop da Steam ou na pasta `Zomboid\mods`.
3. **Para os Shaders:** Copie as três pastas de `03-Shaders-Customizados\` diretamente para `%USERPROFILE%\Zomboid\viewpoint-shaderpacks\`.
4. **Para o MCP Server 3D:** Instale as dependências com `pip install mcp pillow numpy` e aponte o `mcp_config.json` para o `server.py`.
5. **Para a Esteira de Inspeção Visual:** Utilize o servidor Mecanifica já acoplado para renderização headless de vistas e bancada 3D Three.js orbital.
6. **Para os Modelos 3D e Texturas:** Execute `python setup_assets.py` na raiz da suíte (sintetiza todos os modelos e implanta no mod) ou baixe o pacote pronto via **[GitHub Releases](https://github.com/brigsd/Viewpoint-Zomboid-MCP/releases)**.
