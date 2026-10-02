# ⚠️ GOTCHAS: Pegadinhas, Armadilhas Técnicas e Soluções

Este documento reúne todas as **armadilhas não óbvias, particularidades de engine, problemas de compatibilidade e soluções técnicas** encontradas durante a integração do ecossistema de Primeira Pessoa (Viewpoint), ZombieBuddy, Shaders, DLSS 5 e a nova **Esteira de Inspeção Visual e Modelagem 3D** no *Project Zomboid Build 42*.

Consulte este guia sempre que algo parecer não funcionar como esperado.

---

## 📑 Sumário dos Gotchas

1. [A Pegadinha das Teclas (`O` vs `DELETE`)](#1-a-pegadinha-das-teclas-o-vs-delete)
2. [Mismatch de Assinatura de Bytecode no Build 42.21 (`ArrayList` vs `List`)](#2-mismatch-de-assinatura-de-bytecode-no-build-4221-arraylist-vs-list)
3. [Trava de Assinatura Criptográfica da JVM (`SecurityException: SHA-256 digest error`)](#3-trava-de-assinatura-criptográfica-da-jvm-securityexception-sha-256-digest-error)
4. [Carregamento Steam (`ProjectZomboid64.json`) vs Atalho `.bat`](#4-carregamento-steam-projectzomboid64json-vs-atalho-bat)
5. [Injeção Antecipada (`PREMAIN`) vs Carregamento Dinâmico (`MAIN`)](#5-injeção-antecipada-premain-vs-carregamento-dinâmico-main)
6. [Sistema de Aprovação e Whitelist de JARs (`mod_approvals.json`)](#6-sistema-de-aprovação-e-whitelist-de-jars-mod_approvalsjson)
7. [Incompatibilidade do DLSS 5 Swapper com Java OpenGL](#7-incompatibilidade-do-dlss-5-swapper-com-java-opengl)
8. [Hot-Reload e Estrutura dos Shaderpacks](#8-hot-reload-e-estrutura-dos-shaderpacks)
9. [Dependência de Ordem e Ativação dos Mods no Menu](#9-dependência-de-ordem-e-ativação-dos-mods-no-menu)
10. [O Efeito Billboard / "Papel de Parede" dos Sprites 2D no Viewpoint](#10-o-efeito-billboard--papel-de-parede-dos-sprites-2d-no-viewpoint)
11. [Risco de Pular a Esteira de Inspeção Visual (`inspecoes/`)](#11-risco-de-pular-a-esteira-de-inspeção-visual-inspecoes)
12. [Armadilha da Escala Métrica: 1 Tile = 1 Metro (cm vs m)](#12-armadilha-da-escala-métrica-1-tile--1-metro-cm-vs-m)
13. [Pivô Geométrico e o Bug dos Objetos Flutuando ou Enterrados (`Y=0.00`)](#13-pivô-geométrico-e-o-bug-dos-objetos-flutuando-ou-enterrados-y000)
14. [Inversão de Normais e Backface Culling no OpenGL](#14-inversão-de-normais-e-backface-culling-no-opengl)

---

## 1. A Pegadinha das Teclas (`O` vs `DELETE`)

* **O Sintoma:** O jogador entra no mundo, pressiona `DELETE` repetidamente e nada acontece; a câmera continua estática em perspectiva isométrica clássica.
* **A Armadilha:**
  * No mod Viewpoint, a tecla **`DELETE` NÃO liga a primeira pessoa**. O `DELETE` serve apenas para abrir a janela de opções e configurações (menu de seleção de shaders, FOV e câmera).
  * Se o motor Java do Viewpoint ainda não tiver interceptado a renderização, a janela do `DELETE` sequer responde.
* **A Solução:**
  * **`O` (letra Ó):** É a tecla mestre que **liga/desliga** a visão em Primeira Pessoa.
  * **`SHIFT + O`:** Alterna entre Primeira Pessoa e Terceira Pessoa (câmera no ombro).
  * **`DELETE`:** Abre o painel de configurações (use após ativar a câmera).
  * **`INSERT + O`:** Ativa o modo Câmera Livre (Freecam).

---

## 2. Mismatch de Assinatura de Bytecode no Build 42.21 (`ArrayList` vs `List`)

* **O Sintoma:** O jogo abre normalmente, o ZombieBuddy avisa que foi carregado no console, mas o Viewpoint é completamente ignorado. Nenhum erro fatal aparece no `console.txt`.
* **A Causa Raiz:**
  * No código original do Zomboid (Build 41 e início da 42), o método de carregar mods era:
    `zombie.ZomboidFileSystem.loadMods(ArrayList<String> mods)`
  * Na **Build 42.21.0**, a The Indie Stone refatorou a assinatura interna para:
    `zombie.ZomboidFileSystem.loadMods(List<String> mods)`
  * O `ZombieBuddy.jar` v2.3.2 utilizava um descritor estrito do ByteBuddy procurando por `(Ljava/util/ArrayList;)V`.
  * Como a assinatura mudou para `(Ljava/util/List;)V`, o hook nunca era acionado. Consequentemente, `Loader.loadMods()` nunca rodava e o `Viewpoint.jar` nunca era anexado ao ClassLoader.
* **A Solução Aplicada:**
  * Recompilamos a classe interna `Patch_ZomboidFileSystem$Patch_loadMods2.class` com suporte nativo a `java.util.List<String>`.
  * Adicionamos o argumento `-agentlib:zbNative=patches_jar=Viewpoint.jar:viewpoint` para carregar o mod logo no início da JVM (`PREMAIN`), garantindo dupla redundância.

---

## 3. Trava de Assinatura Criptográfica da JVM (`SecurityException: SHA-256 digest error`)

* **O Sintoma:** Ao modificar qualquer arquivo `.class` dentro do `ZombieBuddy.jar`, o jogo recusa carregar o patch e emite o erro:
  `java.lang.SecurityException: SHA-256 digest error for me/zed_0xff/zombie_buddy/patches/...`
* **A Causa Raiz:**
  * O `ZombieBuddy.jar` distribuído na Workshop é assinado digitalmente pelo criador (`META-INF/ME_ZED_0.SF` e `META-INF/ME_ZED_0.RSA`).
  * O verificador interno da máquina Java (`JarVerifier`) compara o hash SHA-256 de cada entrada com o manifesto assinado. Se houver 1 byte de diferença, a JVM bloqueia o carregamento por violação de segurança.
* **A Solução Aplicada:**
  * O JAR foi desassinado (*unsigned*): removemos os arquivos `.SF` e `.RSA` e limpamos as seções de hash do `META-INF/MANIFEST.MF`, mantendo apenas os cabeçalhos essenciais de agente (`Premain-Class`, `Can-Retransform-Classes`). Dessa forma a JVM carrega o código livremente.

---

## 4. Carregamento Steam (`ProjectZomboid64.json`) vs Atalho `.bat`

* **O Sintoma:** O mod funciona quando você executa um script customizado, mas falha quando o jogo é iniciado pelo botão "Jogar" da Steam (ou vice-versa).
* **A Causa Raiz:**
  * O executável oficial da Steam (`ProjectZomboid64.exe`) é um wrapper C++ que lê exclusivamente o arquivo de configuração **`ProjectZomboid64.json`** para instanciar a JVM via JNI. Ele ignora variáveis de ambiente locais do seu shell.
  * Por outro lado, quem inicia o jogo via terminal ou arquivo de lote utiliza o **`ProjectZomboid64.bat`**.
* **A Solução Aplicada:**
  * Ambos os pontos de entrada foram sincronizados com as mesmas flags:
    * `ProjectZomboid64.json`: `vmArgs` contendo `"-agentlib:zbNative=patches_jar=Viewpoint.jar:viewpoint"` e `classpath` contendo `"Viewpoint.jar"`.
    * `ProjectZomboid64.bat`: `_JAVA_OPTIONS` contendo `-agentlib:zbNative=patches_jar=Viewpoint.jar:viewpoint` e `PZ_CLASSPATH` contendo `Viewpoint.jar`.

---

## 5. Injeção Antecipada (`PREMAIN`) vs Carregamento Dinâmico (`MAIN`)

* **A Armadilha:**
  * O Viewpoint não é um mod comum: ele substitui renderização de chão, paredes, entidades e câmera modificando classes centrais como `zombie.iso.IsoCell`, `IsoPlayer`, `SpriteRenderer` e `IsoWorld`.
  * Se o mod tentar aplicar patches de bytecode após essas classes já terem sido carregadas pelo motor do jogo, o ByteBuddy pode falhar em retransformar os métodos em tempo de execução.
* **A Solução:**
  * Ao usar o parâmetro `patches_jar=Viewpoint.jar:viewpoint`, o ZombieBuddy injeta os mais de 70 patches do Viewpoint na fase **`PREMAIN`**, antes que o Zomboid carregue a primeira classe gráfica. Quando o jogo inicia, todas as classes já estão modificadas nativamente.

---

## 6. Sistema de Aprovação e Whitelist de JARs (`mod_approvals.json`)

* **A Armadilha:**
  * O ZombieBuddy possui uma barreira interna de segurança para impedir a execução de JARs maliciosos baixados da Workshop.
  * Dependendo do modo gráfico e de tela cheia, a caixa de diálogo de aprovação de JARs pode ficar escondida atrás da janela do jogo, fazendo o processo congelar na tela preta inicial esperando um clique invisível.
* **A Solução:**
  * Pré-registramos o hash SHA-256 oficial do `Viewpoint.jar` no arquivo de políticas do usuário:
    `C:\Users\<usuario>\.zombie_buddy\mod_approvals.json`
  * Com isso, o ZombieBuddy valida o mod instantaneamente como confiável sem exigir nenhuma intervenção na tela.

---

## 7. Incompatibilidade do DLSS 5 Swapper com Java OpenGL

* **A Armadilha:**
  * O aplicativo *DLSS 5 Swapper* foi projetado para injetar hooks DirectX (DXGI / Direct3D 11 / Direct3D 12) ou Vulkan através do ReShade 6.8 e Streamline DLSS Feeder.
  * O Project Zomboid roda sobre a JVM usando **LWJGL (OpenGL puro)**.
  * Tentar forçar o DLSS 5 Swapper sobre o Zomboid pode causar travamento imediato da JVM (`EXCEPTION_ACCESS_VIOLATION` em drivers gráficos) porque o jogo não possui pipeline DirectX nativa nem buffer de vetores de movimento que o DLSS consome.
* **A Solução:**
  * Para obter o ganho de FPS e a nitidez estilo DLSS de forma segura, use o shaderpack nativo **`ultra-performance`** (localizado no Módulo 03).
  * Ele roda diretamente no pipeline OpenGL do Viewpoint, suprime sombras volumétricas caras e aplica TAA com contraste inteligente (*CAS sharpening*), entregando o mesmo resultado visual sem riscos de crash.

---

## 8. Hot-Reload e Estrutura dos Shaderpacks

* **A Armadilha:**
  * Colocar arquivos de shader soltos ou com nomes incorretos fará o Viewpoint cair de volta no shader `default` (sem avisar de erro explícito na tela).
* **Regras Obrigatórias para Shaders:**
  1. O diretório raiz deve ser: `%USERPROFILE%\Zomboid\viewpoint-shaderpacks\<nome-do-pack>\`.
  2. O arquivo de manifesto obrigatório é o `pack.properties`.
  3. O código GLSL pós-processamento deve estar em `shaders/post.frag`.
* **Superpoder do Viewpoint:**
  * O mod possui um observador de arquivos em tempo real (**`ShaderWatch`**). Você pode editar qualquer arquivo `.frag` com o jogo aberto e salvar no Bloco de Notas: a imagem atualizará no mesmo segundo sem reiniciar o Zomboid!

---

## 9. Dependência de Ordem e Ativação dos Mods no Menu

* **A Armadilha:**
  * Se você ativar o `Viewpoint` em um save sem que o `ZombieBuddy` esteja ativo, o jogo continuará em modo isométrico ou desativará o mod automaticamente ao carregar.
* **Regra:**
  * No menu principal -> **MODS**:
    * O **ZombieBuddy** deve estar ativado (com visto verde).
    * O **Viewpoint** deve estar ativado (com visto verde).
  * Se for um save existente, vá em **Carregar** -> clique no seu Save -> **Mais...** -> **Escolher Mods...** e certifique-se de que ambos estão na lista de mods ativos do save.

---

## 10. O Efeito Billboard / "Papel de Parede" dos Sprites 2D no Viewpoint

* **A Armadilha:**
  * Sprites 2D tradicionais do Zomboid foram desenhados sob uma projeção ortográfica isométrica a 45 graus.
  * Quando você entra em Primeira Pessoa, esses sprites funcionam como **"billboards" achatados ou papéis de parede**:
    1. Se o mod renderizar o sprite como um plano voltado para a câmera (billboard), o objeto gira loucamente conforme o jogador movimenta a cabeça.
    2. Se o sprite for renderizado fixo no plano do tile, ele se parece com uma folha de papel sem espessura quando visto de perfil ou por cima.
    3. Nenhum sprite 2D possui normais de superfície tridimensionais (`vn`), o que impede os shaders PBR do Viewpoint de calcularem sombreamento direcional, luz refletida e oclusão de ambiente (SSAO).
* **A Solução Definitiva:**
  * Substituição direta do sprite pelo seu modelo poligonal físico (`.obj` + `.mtl`) através do Módulo 05.
  * O modelo 3D possui 6 ou mais faces físicas com coordenadas de mundo reais, projetando e recebendo sombras corretas independentemente do movimento da cabeça do jogador.

---

## 11. Risco de Pular a Esteira de Inspeção Visual (`inspecoes/`)

* **A Armadilha:**
  * Tentar injetar um modelo `.obj` diretamente no jogo sem passar pela renderização headless do [Agente Inspetor Visual](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/inspetor-visual.md) pode causar travamentos gráficos, anomalias invisíveis ou obrigar o desenvolvedor a reiniciar o Zomboid repetidamente para testar.
* **A Solução:**
  * Seguir estritamente a [Skill Esteira de Inspeção 3D](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/skills/esteira-inspecao-3d/SKILL.md).
  * O Inspetor Visual gera automaticamente as 4 fotos canônicas em `05-Model-3D-Extractor-MCP/objetos-extraidos-vanilla/inspecoes/<objeto>/`.
  * O [Auditor Humano](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/auditor-humano.md) valida as imagens em 10 segundos antes do comando `deploy_pack`.

---

## 12. Armadilha da Escala Métrica: 1 Tile = 1 Metro (cm vs m)

* **A Armadilha:**
  * Vários softwares de modelagem 3D (Blender, 3ds Max) exportam em centímetros por padrão (onde 1 unidade = 0.01m).
  * No motor do Viewpoint (Project Zomboid B42), a unidade espacial primária de geometria Wavefront é **1.0 unidade = 1.0 metro (largura exata de 1 tile de piso)**.
  * Se um modelo de caixa de 80cm for exportado com valor numérico `80.0`, ele aparecerá no mundo como uma aberração gigantesca de 80 metros de largura, bloqueando a visão de um quarteirão inteiro.
* **A Solução:**
  * Exporte sempre em metros: uma caixa de 85cm deve ter largura `0.85`, altura `0.85` e profundidade `0.85`.
  * Verifique a `vista_topo.png` na pasta de inspeção: o objeto nunca deve estourar a grade de 1.0m x 1.0m, a menos que seja um objeto multi-tile documentado (como uma cama ou balcão duplo).

---

## 13. Pivô Geométrico e o Bug dos Objetos Flutuando ou Enterrados (`Y=0.00`)

* **A Armadilha:**
  * Muitos modelos 3D baixados da internet ou modelados no Blender têm o pivô (ponto de origem `0, 0, 0`) centralizado no centro da massa volumétrica (onde `Y = 0` fica na metade da altura do objeto).
  * No Viewpoint, o piso é a coordenada de contato `Y = 0.00m`.
  * Se o modelo tiver vértices negativos (`Y = -0.40`), a metade inferior da caixa afundará no piso de madeira ou concreto do jogo. Se o modelo tiver origem abaixo do chão (`Y = +0.30`), ele flutuará no ar como se estivesse sob gravidade zero.
* **A Solução:**
  * Todos os vértices de base inferior do `.obj` devem satisfazer `Y_min == 0.0000`.
  * O Agente Extrator 3D calcula os vértices sempre a partir de `Y = 0.0` até `Y = height`.

---

## 14. Inversão de Normais e Backface Culling no OpenGL

* **A Armadilha:**
  * A pipeline de renderização em OpenGL do Viewpoint aplica **Backface Culling** (`GL_CULL_FACE`) por padrão para otimização de performance: faces cujas normais não apontam para o lado da câmera são descartadas da rasterização.
  * Se um modelo tiver os vértices de uma face declarados em ordem horária ao invés de anti-horária (winding order incorreto), o vetor normal (`vn`) apontará para o interior do objeto.
  * Resultado: o objeto parece transparente, furado ou com faces pretas sólidas quando iluminado pelas lanternas ou postes.
* **A Solução:**
  * Inspecione a `vista_isometrica.png` gerada pelo Inspetor Visual na pasta de inspeções.
  * Se houver faces pretas ou vazadas, use o comando de Bancada 3D interativa Three.js (`ativar_bancada`) para rotacionar o modelo e ativar a visualização de normais antes do deploy.
