# 🏺 Objetos Extraídos / Vanilla (Project Zomboid Build 42)

Esta pasta serve como o **Repositório Central de Dados Extraídos e Catálogo Exaustivo de Sprites e Modelos Vanilla** do Project Zomboid Build 42 para a First-Person Suite e o motor Viewpoint.

---

## 📊 Estatísticas Oficiais da Extração e Catalogação

| Categoria de Recurso | Origem no Jogo | Quantidade | Destino / Arquivo |
| :--- | :--- | :---: | :--- |
| **Modelos 3D Vanilla Originais** | `media/models_X/` | **952 modelos** | [`modelos-3d-originais/`](./modelos-3d-originais/) |
| ├── *IsoObject* | `models_X/IsoObject/` | 63 modelos | Portões, grades, portas duplas, escadas, rampas |
| ├── *WorldItems (Loot de Chão)* | `models_X/WorldItems/` + Raiz | 344 modelos | Latas, garrafas, kits médicos, munições, ferramentas |
| ├── *Armas (Weapons)* | `models_X/weapons/` | 243 modelos | Espingardas, rifles, pistolas, machados, bastões, facas |
| ├── *Veículos e Componentes* | `models_X/vehicles/` | 146 modelos | Carros completos, peças, rodas, portas, deformações |
| └── *Corpos, Animais e Vestimentas* | `models_X/Skinned/` + `Static/` | 156 modelos | Bovinos, galinhas, suínos, malhas de personagens e armaduras |
| **Catálogo Exaustivo de Sprites 2D** | `tiledefinitions` + `tileGeometry` | **1.742 sprites** | [`sprites_vanilla_catalog.json`](./sprites_vanilla_catalog.json) |
| ├── *Gôndolas e Prateleiras* | `furniture_shelving_01_*`, `location_shop_*` | 686 sprites | Prateleiras comerciais, gôndolas de mercado, expositores |
| ├── *Eletrodomésticos* | `appliances_cooking_*`, `appliances_refrigeration_*` | 131 sprites | Fogões, fornos, geladeiras residenciais/comerciais, freezers |
| ├── *Móveis e Contêineres* | `carpentry_*`, `furniture_storage_*`, `tables_*` | 580 sprites | Caixotes de madeira, mesas altas/baixas, balcões, cadeiras |
| ├── *Portas e Janelas* | `fixtures_doors_*`, `fixtures_doors_fences_*` | 298 sprites | Portas de madeira, portas de segurança, portões, batentes |
| └── *Loots e Comidas de Chão* | Scripts de Itens (`Base.*`) | 47 itens canônicos | Latas de feijão/carne, garrafas d'água, munição, farmácia |
| **Modelos 3D Prontos Sintetizados** | Motor de Geometria Paramétrica | **24 modelos** | [`../objetos-prontos-3d/`](../objetos-prontos-3d/) |

---

## 📂 Estrutura de Diretórios desta Pasta

```text
objetos-extraidos-vanilla/
├── modelos-3d-originais/                    # Repositório de modelos nativos extraídos
│   ├── IsoObject/                           # 63 modelos (.glb, .fbx) de objetos do mundo
│   ├── WorldItems/                          # 344 modelos (.fbx, .x) de itens de chão
│   ├── weapons/                             # 243 modelos (.x, .fbx) de armas
│   ├── vehicles/                            # 146 modelos (.fbx) de veículos
│   ├── corpos_e_personagens/                # 156 modelos (.x, .fbx) de animais e corpos
│   └── modelos_vanilla_manifest.json        # Índice mestre com metadados de cada arquivo
│
├── sprites_vanilla_catalog.json             # Catálogo estruturado de 1.742 sprites com dimensões métricas
├── README.md                                # Esta documentação técnica
└── inspecoes/                               # Laudos visuais e fotos 4-vistas geradas pelo Mecanifica
    ├── counter_sink_3d/
    ├── medical_box_3d/
    ├── microwave_oven_3d/
    ├── shotgun_ammo_box_3d/
    └── wooden_crate_3d/
```

---

## 🔍 Detalhes do Catálogo de Sprites (`sprites_vanilla_catalog.json`)

Cada entrada no catálogo foi extraída cruzando os arquivos canônicos `newtiledefinitions.tiles.txt`, `tileGeometry.txt` (bounding boxes 3D em unidades do motor convertidas para metros), os scripts de itens (`scripts/generated/items/*.txt`) e os arquivos de tradução (`Moveables.json` e `ItemName.json`):

```json
{
  "sprite_id": "furniture_shelving_01_0",
  "nome_legivel": "Hardwood Wall Shelves (S)",
  "categoria": "gondolas_e_prateleiras",
  "dimensoes_estimadas_m": {
    "largura": 0.85,
    "altura": 1.55,
    "profundidade": 0.45
  },
  "orientacao_tile": "S",
  "prioridade_substituicao": "Alta",
  "tipo_objeto": "IsoObject / Container (shelves)",
  "material": "Wood",
  "tags": [
    "gondolas_e_prateleiras",
    "wood",
    "S"
  ]
}
```

---

## 🎯 Modelos Prontos Sintetizados em `objetos-prontos-3d/`

Para atender à demanda de substituição visual imediata em Primeira Pessoa, a biblioteca de objetos prontos conta com **24 modelos 3D** calibrados volumetricamente:

### 1. Gôndolas, Prateleiras e Balcões de Loja (`Moveis-e-Caixas/`)
* `store_shelf_gondola_3d.obj`: Gôndola de supermercado de dupla face (0.90m L x 1.60m A x 0.80m P).
* `metal_store_shelf_3d.obj`: Estante comercial pesada de estoque (0.90m L x 1.85m A x 0.50m P).
* `shop_counter_wood_3d.obj`: Balcão de atendimento e caixa em madeira (0.90m L x 0.90m A x 0.65m P).
* `shop_counter_glass_3d.obj`: Balcão vitrine com visor de vidro (0.90m L x 0.90m A x 0.65m P).
* `wooden_door_interior_3d.obj`: Porta de madeira interior batente (0.85m L x 2.10m A x 0.08m P).
* Modelos pré-existentes: `wooden_crate_3d`, `wooden_table_3d`, `office_chair_3d`, `counter_sink_3d`, `store_shelves_3d`.

### 2. Freezers e Refrigeração (`Eletrodomesticos/`)
* `commercial_freezer_vertical_3d.obj`: Freezer vertical expositor de bebidas de supermercado (0.85m L x 1.85m A x 0.75m P).
* `ice_cooler_freezer_3d.obj`: Freezer horizontal expositor de gelo (1.00m L x 0.90m A x 0.65m P).
* Modelos pré-existentes: `refrigerator_3d`, `kitchen_stove_3d`, `kitchen_fridge_3d`, `microwave_oven_3d`.

### 3. Comidas Enlatadas e Loots de Chão (`Itens-de-Chao-Loot/`)
* `canned_food_can_3d.obj`: Lata de comida canônica padrão cilíndrica (0.085m diâmetro x 0.12m altura).
* `canned_beans_3d.obj`: Lata de feijão clássica (`Base.TinnedBeans`, `Base.OpenBeans`).
* `canned_sardines_3d.obj`: Lata retangular achatada de sardinha/pescado (0.11m x 0.04m x 0.065m).
* `water_bottle_3d.obj`: Garrafa d'água mineral de plástico (0.08m diâmetro x 0.24m altura).
* Modelos pré-existentes: `military_ammo_can_3d`, `shotgun_ammo_box_3d`, `medical_firstaid_kit_3d`, `medical_box_3d`.

---

## 🔗 Amarrações no `pack.manifest`

O arquivo `objetos-prontos-3d/pack.manifest` foi atualizado com todas as amarrações que vinculam automaticamente os IDs de sprites 2D (`furniture_shelving_01_*`, `location_shop_generic_01_*`, `appliances_refrigeration_01_*`, `Base.TinnedBeans`, `Base.WaterBottle`, etc.) aos respectivos modelos 3D volumétricos com rotação, offset e escala 1:1.
