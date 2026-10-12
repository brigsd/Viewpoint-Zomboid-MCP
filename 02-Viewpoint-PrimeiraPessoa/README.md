# 🎥 Módulo 02: Viewpoint (Primeira e Terceira Pessoa)

O **Viewpoint** é o mod que converte a câmera isométrica do *Project Zomboid Build 42* em uma câmera 3D livre, com visão em **Primeira Pessoa** e **Terceira Pessoa** (sobre o ombro), renderizada dentro do próprio motor do jogo.

| Campo | Valor |
| :--- | :--- |
| **ID do mod** | `Viewpoint` |
| **Versão** | `0.1.5a-hotfix` |
| **Build suportada** | `42.21` (mínima e máxima) |
| **Dependência** | `ZombieBuddy` ≥ `2.3.0` ([Módulo 01](../01-ZombieBuddy-Loader/)) |
| **Workshop** | [3809306528](https://steamcommunity.com/sharedfiles/filedetails/?id=3809306528) |

---

## 📂 Estrutura da Pasta

```text
02-Viewpoint-PrimeiraPessoa/
├── Viewpoint.jar                         # Cópia do JAR que vai na pasta do jogo (idêntica à de dentro do mod)
└── mods/Viewpoint/
    ├── LICENSE                           # Licença proprietária dos autores do Viewpoint
    ├── common/
    │   ├── mod.info                      # Metadados, dependência do ZombieBuddy e JAR Java
    │   └── poster.png
    └── 42/media/
        ├── java/client/Viewpoint.jar     # Motor Java (pacote `viewpoint`), carregado pelo ZombieBuddy
        └── lua/client/
            ├── Viewpoint_Options.lua         # Painel de opções e remapeamento de teclas
            ├── Viewpoint_FrameCapOptions.lua # Limites de FPS (24 a 500)
            ├── Viewpoint_Interact.lua        # Interação com objetos pela mira 3D
            ├── Viewpoint_Loot.lua            # Saque de containers e chão pela mira
            └── Viewpoint_Mouse.lua           # Conversão de coordenadas do mouse em 3D
```

---

## ⚙️ Como Funciona

1. O **ZombieBuddy** (Módulo 01) lê o `mod.info`, encontra `javaJarFile=media/java/client/Viewpoint.jar` e injeta o pacote Java `viewpoint` no jogo.
2. O motor Java substitui a renderização isométrica por um renderizador próprio em OpenGL 3.3, com iluminação dinâmica, sombras, TAA e pós-processamento.
3. Os scripts Lua adaptam a interface vanilla (menu de contexto, inventário, mouse) para funcionar a partir do ponto onde a mira 3D aponta.
4. O pós-processamento visual vem dos shaderpacks. Três vêm dentro do JAR (`default`, `normal` e `vivid`), e os customizados ficam em `%USERPROFILE%\Zomboid\viewpoint-shaderpacks\` (veja o [Módulo 03](../03-Shaders-Customizados/), cujos packs herdam do `default`).

### Como está instalado nesta máquina

Além do mod da Workshop (`steamapps\workshop\content\108600\3809306528`), o jogo carrega o Viewpoint direto pela pasta de instalação:

* `Viewpoint.jar` copiado para a pasta do jogo (o arquivo da raiz deste módulo é essa cópia);
* `ProjectZomboid64.json` com `Viewpoint.jar` no `classpath` e `-agentlib:zbNative=patches_jar=Viewpoint.jar:viewpoint` nos `vmArgs`.

Ao atualizar o Viewpoint, troque o JAR nos dois lugares. Uma versão diferente na pasta do jogo e no mod pode dar conflito.

---

## 🎮 Atalhos Padrão

Lista tirada do próprio `Viewpoint.jar` (classe `viewpoint.platform.Keys`) da versão `0.1.5a-hotfix`.

| Tecla | Ação |
| :--- | :--- |
| **`O`** | Liga/desliga a Primeira Pessoa |
| **`SHIFT + O`** | Com a visão ligada: alterna entre Primeira e Terceira Pessoa (sobre o ombro) |
| **`DELETE`** | Abre/fecha a janela de configurações (shaders, FOV, iluminação) |
| **`F9`** | Captura de tela (salva em `Zomboid/viewpoint-shots/`) |
| **`'`** (apóstrofo) | Overlay de desempenho: completo, compacto, só o gráfico ou desligado |

**Menu de saque** (aparece ao mirar em um container ou item):

| Tecla | Ação |
| :--- | :--- |
| **`F`** | Pega o item ou faz a ação selecionada no menu (a roda do mouse escolhe). O "Interagir" do jogo continua sendo o do jogo. |
| **`R`** | Pega tudo o que o menu mostra |
| **`TAB`** | Abre a janela de saque do próprio jogo, com o cursor livre (de novo para fechar) |

**Câmera livre:**

| Tecla | Ação |
| :--- | :--- |
| **`INSERT + O`** | Liga/desliga a câmera livre (voa para qualquer lugar; o mundo continua em volta do jogador) |
| **`SHIFT + INSERT + O`** | Câmera livre "física": o mundo passa a ser centrado nela (desenho, detalhe e som acompanham) |
| **`W` `A` `S` `D`** | Frente, esquerda, trás, direita |
| **`ESPAÇO`** ou **`E`** / **`SHIFT ESQ.`** ou **`Q`** | Sobe / desce |
| **`ALT ESQ.`** (segurar) | Quatro vezes mais rápido |
| **`PAGE DOWN`** | Volta a câmera para os olhos do jogador |

> [!NOTE]
> As teclas podem ser remapeadas em **Opções → Mods → Viewpoint**. Há também teclas de depuração (`F8`, `F10`, `F11`, `END`), que ficam sem atalho nesta versão de release.
>
> O `DELETE` **não** liga a primeira pessoa, só abre o painel de configurações. Use `O` primeiro. Detalhes em [GOTCHAS.md §1](../GOTCHAS.md).

---

## 🛠️ Instalação

1. Instale e ative o **ZombieBuddy** primeiro (veja o [Módulo 01](../01-ZombieBuddy-Loader/)).
2. Inscreva-se no Viewpoint na Steam Workshop **ou** copie `mods/Viewpoint/` para `%USERPROFILE%\Zomboid\mods\`.
3. No menu principal, vá em **MODS** e ative **ZombieBuddy** e **Viewpoint**.
4. Em saves existentes: **Carregar → selecione o save → Mais... → Escolher Mods...** e confirme que os dois estão ativos.
5. Entre no mundo e aperte **`O`**.

---

## ⚠️ Problemas Comuns

Consulte o [GOTCHAS.md](../GOTCHAS.md), em especial:

* **§1** — Tecla `O` vs `DELETE`
* **§2** — Incompatibilidade de assinatura de bytecode fora da Build 42.21
* **§6** — Aprovação de JARs (`mod_approvals.json`)
* **§9** — Ordem e ativação dos mods no menu
* **§10** — Efeito "papel de parede" dos sprites 2D (resolvido pelo [Módulo 05](../05-Model-3D-Extractor-MCP/))

---

## 📜 Licença

O Viewpoint é software **proprietário** dos seus autores (veja [`mods/Viewpoint/LICENSE`](./mods/Viewpoint/LICENSE)). Esta pasta guarda uma cópia para backup e restauração local da suíte.
