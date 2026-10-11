# 🎮 Project Zomboid - 3D First Person & Shaders Suite

Bem-vindo à central de arquivos e módulos do ecossistema de Primeira Pessoa e Shaders customizados para o **Project Zomboid Build 42**.

---

> [!IMPORTANT]
> ### 📖 LEIA PRIMEIRO O ARQUIVO `INDEX.md`!
>
> Antes de explorar as pastas, abra e leia o documento **[INDEX.md](./INDEX.md)**.
> 
> **O que é o `INDEX.md`?**
> O `INDEX.md` é o **Guia Mestre de Arquitetura Modular** deste projeto. Nele você encontrará:
> * A explicação detalhada do que é e para que serve cada uma das pastas desta suíte (`01-ZombieBuddy-Loader`, `02-Viewpoint-PrimeiraPessoa`, `03-Shaders-Customizados`, `04-DLSS5-Swapper-Bridge` e `05-Model-3D-Extractor-MCP`).
> * Como os módulos se conectam para viabilizar a câmera 3D, os gráficos na engine do Zomboid e o upscaling neural.
> * A documentação dos sub-pacotes de shaders (`Bleak Horror`, `Photorealism` e `Ultra Performance`).
> * O manual e diagnóstico sobre o **DLSS 5 Swapper** e compatibilidade com OpenGL/Java.
> * O funcionamento da **Esteira de Inspeção Visual e Auditoria 3D** (MCP + Mecanifica Headless + Bancada 3D).
> * Instruções de restauração e backup caso você precise reinstalar o jogo ou mover arquivos.

---

## 📂 Visão Rápida dos Módulos

| Módulo | Nome da Pasta | Papel no Jogo |
| :--- | :--- | :--- |
| **01** | [`01-ZombieBuddy-Loader`](./01-ZombieBuddy-Loader/) | Injetor Java de baixo nível que permite mods nativos rodarem no PZ. |
| **02** | [`02-Viewpoint-PrimeiraPessoa`](./02-Viewpoint-PrimeiraPessoa/) | O mod que converte o jogo isométrico em 3D livre (1ª e 3ª Pessoa). |
| **03** | [`03-Shaders-Customizados`](./03-Shaders-Customizados/) | Pacotes de shaders criados sob medida (Terror, Realismo e Performance). |
| **04** | [`04-DLSS5-Swapper-Bridge`](./04-DLSS5-Swapper-Bridge/) | Manual e ponte sobre o DLSS 5 Swapper, upscaling por IA e OpenGL. |
| **05** | [`05-Model-3D-Extractor-MCP`](./05-Model-3D-Extractor-MCP/) | Servidor FastMCP para IA extrair sprites, gerar modelos 3D (.obj) e esteira de inspeção visual. |
| **06** | [`06-PZ-Lab-Headless`](./06-PZ-Lab-Headless/) | Servidor dedicado headless + MCP `pz-live` para a IA criar e testar mods sem abrir o jogo. |

---

## 🧊 Por que a Substituição de Sprites por Modelos 3D é Fundamental no Viewpoint?

No Project Zomboid clássico, a perspectiva é isométrica fixa a 45 graus. Para esse ângulo fixo, desenhar objetos como **sprites 2D planos** era eficiente. No entanto, quando você ativa a visão em **Primeira Pessoa (Viewpoint)**, a limitação bidimensional quebra a experiência:

1. **O Efeito "Papel de Parede" / Billboard Achatado:**
   * Sprites 2D são folhas sem espessura. Quando você caminha ao redor de uma mesa, caixa ou cadeira em primeira pessoa, o objeto parece uma cartolina fina cortada ou deforma bizarramente acompanhando o giro da sua mira.
2. **Ausência de Sombras e Oclusão de Luz:**
   * Os shaders modernos da suíte (`bleak-horror`, `photorealism`) contam com oclusão de ambiente e projeção de penumbras em tempo real. Sprites 2D não possuem faces orientadas no espaço 3D nem vetores normais (`vn`), gerando artefatos luminosos planos.
3. **Imersão Tátil em Combate e Loot:**
   * Com modelos 3D poligonais (`.obj`), recipientes, móveis e itens largados no chão ganham presença física, cantos definidos, texturas mapeadas e profundidade real no campo visual do jogador.

---

## 🔬 Nova Esteira de Inspeção Visual e Governança 3D

Para garantir que os modelos 3D injetados no jogo tenham proporções perfeitas, materiais alinhados e escala métrica exata (1 tile = 1m), a suíte agora conta com uma **esteira de inspeção em paralelo**:

```text
[Agente Extrator 3D] ──► [Agente Inspetor Visual] ──► [Auditor Humano] ──► [Deploy no Jogo]
  (MCP pz-extractor)      (Render Headless Mecanifica)    (QA das 4 Vistas)      (Viewpoint Mod)
                                 │                               ▲
                                 └─► Bancada 3D Interativa ──────┘
                                     (Three.js via Mecanifica)
```

* 🤖 **[Agente Extrator 3D](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/extrator-3d.md):** Extração de metadados do jogo, cálculo métrico e síntese da geometria `.obj`.
* 🔍 **[Agente Inspetor Visual](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/inspetor-visual.md):** Renderização headless automatizada (sem abrir janelas de software) gerando 4 vistas canônicas (isométrica, topo, frontal e lateral).
* 👤 **[Protocolo de Auditoria Humana](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/auditor-humano.md):** Checklist de 5 critérios para o operador avaliar as fotos e aprovar ou solicitar a Bancada 3D Three.js interativa.
* 🚀 **[Skill: Esteira de Inspeção 3D](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/skills/esteira-inspecao-3d/SKILL.md):** Manual completo de operação do pipeline.
* 📸 **[Pasta de Inspeções Headless](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/05-Model-3D-Extractor-MCP/objetos-extraidos-vanilla/inspecoes/):** Onde as fotos de cada objeto inspecionado são organizadas com seus laudos técnicos.

---

---

## 🌐 Repositório GitHub, Distribuição Leve & Releases

* **Repositório Oficial:** [github.com/brigsd/Viewpoint-Zomboid-MCP](https://github.com/brigsd/Viewpoint-Zomboid-MCP)

### 📦 Princípio "Zero Bloat" (Sem Binários Pesados no Git)
Para manter o repositório extremamente leve, rápido para clonar e 100% em conformidade com as diretrizes de direitos autorais da The Indie Stone, **o Git versiona exclusivamente código-fonte, manifestos, scripts e documentação**. Renders fotográficos temporários, imagens de inspeção (`*.png`) e binários proprietários extraídos do jogo são ignorados pelo `.gitignore`.

### 🚀 Como Obter os Modelos 3D e Texturas:

Existem 3 formas simples e flexíveis de carregar todos os assets na sua máquina:

#### Método 1: Setup Automatizado em 1 Clique (Recomendado)
Qualquer pessoa que clonar o repositório pode sintetizar todos os modelos e texturas localmente em menos de 5 segundos executando:
```powershell
python setup_assets.py
```
O script verifica dependências (Pillow), sintetiza as malhas 3D (`.obj`), os materiais (`.mtl`), gera as texturas e implanta automaticamente o pacote ativo no mod Viewpoint.

#### Método 2: Download do Pacote Pré-Compilado via GitHub Releases
Para quem prefere não executar scripts de compilação:
1. Acesse a aba de **[Releases no GitHub](https://github.com/brigsd/Viewpoint-Zomboid-MCP/releases)**.
2. Baixe o arquivo compactado `zomboid-3d-essentials.zip`.
3. Extraia o conteúdo diretamente no diretório de modelpacks do Viewpoint:
   ```text
   ...\Steam\steamapps\workshop\content\108600\3809306528\mods\Viewpoint\42\media\modelpacks\zomboid-3d-essentials\
   ```

#### Método 3: Extração de Modelos Vanilla do seu Jogo Local
Como você já possui o Project Zomboid Build 42 instalado na Steam, você pode extrair mais de 952 modelos 3D originais e 2.250 texturas oficiais da sua própria máquina:
```powershell
python 05-Model-3D-Extractor-MCP/scripts/extrair_modelos_vanilla.py
```

---

## ⚡ Atalhos e Controles no Jogo

* **`O`**: **Ativar / Desativar a Primeira Pessoa** (liga/desliga a câmera 3D).
* **`SHIFT + O`**: Alternar entre **Primeira Pessoa e Terceira Pessoa** (sobre o ombro).
* **`DELETE`**: Abre a janela de configurações do Viewpoint e seleção de **Shader Packs** dentro da partida.
* **`INSERT + O`**: Modo **Câmera Livre** (Freecam).
* **`F` / `R`**: Pegar item / Pegar tudo pelo menu dinâmico de mira.
* **`F9`**: Captura de tela pelo motor do Viewpoint (salva em `Zomboid/viewpoint-shots/`).
* **Menu de Mods (no menu principal)**: Certifique-se de que os mods **ZombieBuddy** e **Viewpoint** estejam ativados com o visto verde.

---
* *Para a visão geral da arquitetura e detalhes de cada módulo, consulte o **[INDEX.md](./INDEX.md)**.*
* *Para soluções de problemas, armadilhas técnicas e comportamentos não óbvios, consulte o **[GOTCHAS.md](./GOTCHAS.md)**.*

