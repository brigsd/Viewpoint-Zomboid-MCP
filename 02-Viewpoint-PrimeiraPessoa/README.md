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
├── Viewpoint.jar                         # Cópia avulsa do JAR (idêntica à de dentro do mod)
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
4. O pós-processamento visual vem dos shaderpacks em `%USERPROFILE%\Zomboid\viewpoint-shaderpacks\` (veja o [Módulo 03](../03-Shaders-Customizados/)).

---

## 🎮 Atalhos Padrão

| Tecla | Ação |
| :--- | :--- |
| **`O`** | Liga/desliga a Primeira Pessoa |
| **`SHIFT + O`** | Alterna entre Primeira e Terceira Pessoa |
| **`DELETE`** | Abre/fecha a janela de configurações (shaders, FOV, iluminação) |
| **`INSERT + O`** | Câmera Livre (Freecam) |
| **`F`** | Interagir / pegar o item mirado |
| **`R`** | Pegar tudo do container mirado |
| **`F9`** | Captura de tela (salva em `Zomboid/viewpoint-shots/`) |

> [!NOTE]
> As teclas podem ser remapeadas em **Opções → Mods → Viewpoint**.
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
