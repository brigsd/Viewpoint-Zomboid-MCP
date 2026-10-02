# 📦 Módulo 05: Project Zomboid 3D Model Extractor & Inspection Pipeline (MCP Server)

Este módulo implementa o ecossistema automatizado de **extração, modelagem paramétrica, renderização headless e injeção de modelos 3D** para o *Project Zomboid Build 42* rodando sob o motor *Viewpoint*. Ele combina um **servidor MCP (Model Context Protocol)** em Python utilizando o framework **FastMCP** com o motor de renderização analítica do **Mecanifica**.

---

## 🎯 Por que Substituir Sprites 2D por Modelos 3D no Viewpoint?

No Project Zomboid tradicional (isométrico fixo a 45°), objetos desenhados como sprites 2D planos são perfeitamente aceitáveis. No entanto, quando você ativa a visão em **Primeira Pessoa (Viewpoint)**:

1. **O Efeito "Papel de Parede" / Billboard Achatado:**
   * Sprites 2D funcionam como lâminas ou cartolinas finas. Ao caminhar ao redor de uma mesa ou caixa, o objeto parece uma folha achatada sem profundidade ou deforma acompanhando a visão de forma distorcida.
2. **Ausência de Sombras e Oclusão de Luz:**
   * Os shaders customizados da suíte (`bleak-horror`, `photorealism`, `ultra-performance`) utilizam renderização PBR (Physically Based Rendering) com oclusão de ambiente e penumbras dinâmicas. Como sprites 2D não possuem geometria vetorial nem normais de superfície (`vn`), eles não recebem nem projetam luz física.
3. **Imersão Tátil em Combate e Loot:**
   * Modelos poligonais 3D (`.obj` + `.mtl`) conferem **massa volumétrica real**, cantos sólidos e colisão visual tangível, transformando o Zomboid em uma experiência legítima de FPS de sobrevivência.

---

## 🏗️ Arquitetura da Esteira em Duas Trilhas Paralelas

```text
               ┌─────────────────────────────────────────────────────────────┐
               │            ESTEIRA TÉCNICA DE MODELAGEM 3D                 │
               │         (Agente Extrator / MCP pz-model-extractor)          │
               └──────────────────────────────┬──────────────────────────────┘
                                              │
                    1. search_sprites() / catálogo vanilla
                    2. generate_box_model() / generate_custom_obj()
                    3. Gravação em packs/<pack_id>/models/<obj>.obj
                                              │
                                              ▼
               ┌─────────────────────────────────────────────────────────────┐
               │         ESTEIRA DE INSPEÇÃO VISUAL E AUDITORIA             │
               │   (Agente Inspetor / Mecanifica Headless + Auditor Humano)  │
               └──────────────────────────────┬──────────────────────────────┘
                                              │
                    4. mecanifica:renderizar_vistas(peca)
                       └── Sem UI: Grava 4 Vistas em inspecoes/<objeto>/
                           ├── vista_isometrica.png
                           ├── vista_topo.png
                           ├── vista_frontal.png
                           └── vista_lateral.png
                    5. Emissão de auditoria.json e relatorio_inspecao.md
                                              │
                        ┌─────────────────────┴─────────────────────┐
                        ▼                                           ▼
                 [Dúvida Geométrica]                         [Tudo Conforme]
                        │                                           │
             mecanifica:ativar_bancada                              │
             (Three.js Orbital no Navegador)                        │
                        │                                           │
                        └─────────────────────┬─────────────────────┘
                                              │
                                              ▼
                    6. Homologação do Auditor Humano (Aprovado!)
                                              │
                                              ▼
               ┌─────────────────────────────────────────────────────────────┐
               │             DEPLOY E ATIVAÇÃO NO VIEWPOINT                  │
               └──────────────────────────────┬──────────────────────────────┘
                                              │
                    7. bind_sprite_to_3d() no pack.manifest
                    8. deploy_pack() ──► Viewpoint Mod / AutoRegister Lua
                                              │
                                              ▼
                             [Objeto 3D Físico no Jogo!]
```

---

## 👥 Agentes e Documentos de Governança

A esteira conta com perfis especializados documentados em diretórios dedicados:

* 🤖 **[Agente Extrator 3D](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/extrator-3d.md):** Especialista em extração de sprites, catalogação vanilla, cálculo de proporções em metros e geração de malhas `.obj`.
* 🔍 **[Agente Inspetor Visual](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/inspetor-visual.md):** Responsável pela renderização headless em modo auditoria (sem interface) gerando as 4 fotos canônicas e o laudo de geometria.
* 👤 **[Protocolo de Auditoria Humana](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/auditor-humano.md):** Manual com o checklist das 5 dimensões de qualidade (volumetria, escala métrica, normais, textura UV e linha de solo Y=0).
* 🚀 **[Skill: Esteira de Inspeção 3D](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/skills/esteira-inspecao-3d/SKILL.md):** Runbook operacional detalhado de ponta a ponta.

---

## 📁 Estrutura de Pastas do Módulo

* **[`objetos-extraidos-vanilla/`](./objetos-extraidos-vanilla/):**
  * Modelos 3D originais extraídos do Zomboid (`.glb`, `.fbx`, `.x`), como caixas de munição, despertador, remédios, carpintaria e portas.
  * Catálogo de metadados de sprites vanilla ([`sprites_vanilla_catalog.json`](./objetos-extraidos-vanilla/sprites_vanilla_catalog.json)).
* 📸 **[`objetos-extraidos-vanilla/inspecoes/`](./objetos-extraidos-vanilla/inspecoes/):**
  * **Nova pasta central de auditoria visual.**
  * Cada objeto possui sua subpasta contendo as 4 imagens oficiais (`vista_isometrica.png`, `vista_topo.png`, `vista_frontal.png`, `vista_lateral.png`), o relatório técnico `relatorio_inspecao.md` e o descritor `auditoria.json`.
* **[`objetos-prontos-3d/`](./objetos-prontos-3d/):**
  * Biblioteca pronta e homologada de modelos poligonais 3D (`.obj` + `.mtl`) dividida em:
    * `Moveis-e-Caixas/` (caixotes, prateleiras, poltronas)
    * `Eletrodomesticos/` (fogões, fornos, geladeiras)
    * `Itens-de-Chao-Loot/` (garrafas, caixas de balas, relógios)
  * Manifesto mestre pronto para ativação imediata ([`pack.manifest`](./objetos-prontos-3d/pack.manifest)).
* **`packs/`:** Diretório de staging onde o servidor MCP gera novos pacotes customizados antes do deploy.
* **`server.py`:** Servidor FastMCP principal em Python.

---

## 🛠️ Catálogo Completo de Ferramentas MCP

### Servidor `pz-model-extractor`:

| Ferramenta | Descrição | Parâmetros Principais |
| :--- | :--- | :--- |
| **`get_diagnostics`** | Verifica caminhos do Zomboid, instalação do Viewpoint e packs ativos. | *(Nenhum)* |
| **`list_sprite_categories`** | Retorna o catálogo estruturado com categorias de objetos do jogo. | *(Nenhum)* |
| **`search_sprites`** | Pesquisa sprites/tiles no banco de dados do Zomboid por palavra-chave. | `query`, `max_results` |
| **`list_vanilla_extracted`** | Lista arquivos de referência 3D vanilla originais do jogo. | *(Nenhum)* |
| **`list_ready_models`** | Lista todos os modelos 3D prontos na pasta `objetos-prontos-3d/`. | *(Nenhum)* |
| **`create_model_pack`** | Cria a estrutura de pastas e o `pack.manifest` para um novo pacote. | `pack_id`, `pack_name` |
| **`generate_box_model`** | Gera um sólido 3D (.obj + .mtl) paramétrico com dimensões reais em metros. | `pack_id`, `model_name`, `width`, `height`, `depth`, `texture_name` |
| **`generate_custom_obj`** | Salva malhas 3D complexas personalizadas em formato Wavefront .obj. | `pack_id`, `model_name`, `obj_content` |
| **`bind_sprite_to_3d`** | Amarra o sprite 2D ao modelo 3D com rotação, offsets e escala no manifesto. | `pack_id`, `sprite_name`, `model_name`, `rotation_degrees`, `offset_x`, `offset_y`, `offset_z`, `scale` |
| **`list_pack_manifest`** | Exibe o conteúdo completo do manifesto de substituição de um pack. | `pack_id` |
| **`deploy_pack`** | Copia o pack de staging para o mod Viewpoint e injeta o auto-carregador Lua. | `pack_id` |
| **`deploy_ready_pack`** | Faz o deploy imediato de toda a pasta `objetos-prontos-3d/` para o Viewpoint. | *(Nenhum)* |

### Servidor Integrado `mecanifica`:

| Ferramenta | Descrição | Aplicação na Esteira |
| :--- | :--- | :--- |
| **`renderizar_vistas`** | Produz as 4 vistas oficiais de inspeção sem abrir janelas. | Geração das fotos na pasta `inspecoes/<objeto>/`. |
| **`descrever_peca`** | Extrai ficha volumétrica, Bounding Box e cálculo de faces/normais. | Preenchimento automático do `auditoria.json`. |
| **`ativar_bancada`** | Sobe a bancada 3D interativa Three.js na porta indicada (ex: `8080`). | Inspeção orbital 360° em tempo real pelo operador humano. |

---

## ⚙️ Configuração e Execução do MCP

O servidor MCP já está configurado no arquivo global do seu ambiente:
`C:\Users\micro\.gemini\config\mcp_config.json`

```json
{
  "mcpServers": {
    "pz-model-extractor": {
      "command": "C:/Users/micro/AppData/Local/Programs/Python/Python312/python.exe",
      "args": [
        "c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/05-Model-3D-Extractor-MCP/server.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### Para testar manualmente via terminal:
```powershell
python "c:\Users\micro\Desktop\ProjectZomboid-FirstPerson-Suite\05-Model-3D-Extractor-MCP\server.py"
```

---

## 📐 Anatomia de um Model Pack do Viewpoint

Cada pacote de modelos criado na subpasta `packs/<pack_id>/` contém:

```text
packs/meu-pack-3d/
├── pack.manifest           <-- Mapeamentos (model.* e bind.*)
├── models/
│   ├── meu_objeto.obj      <-- Malha 3D poligonal Wavefront
│   └── meu_objeto.mtl      <-- Definição de material
└── textures/
    └── diffuse.png         <-- Textura mapeada
```

### Formato do `pack.manifest`:
```ini
id = meu-pack-3d
name = Meu Pacote 3D

# Registra o arquivo 3D
model.caixa_madeira = models/caixa_madeira.obj

# Amarra o sprite 2D do Zomboid ao modelo 3D:
# bind.<sprite_2d> = <id_modelo> <graus_rotacao> <offset_x> <offset_y> <offset_z> <escala>
bind.furniture_storage_01_16 = caixa_madeira 0.0 0.00 0.00 0.00 1.00
```
