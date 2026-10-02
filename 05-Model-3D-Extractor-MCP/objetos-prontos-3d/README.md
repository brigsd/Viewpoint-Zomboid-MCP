# 🎨 Objetos Prontos 3D (Zomboid 3D Essentials Pack)

Esta pasta reúne a biblioteca de **modelos 3D poligonais prontos para uso** (`.obj` + `.mtl`), organizados por categoria e já amarrados aos sprites 2D correspondentes do Project Zomboid através do arquivo **`pack.manifest`**.

---

## 📂 Categorias e Modelos Inclusos

### 1. `Moveis-e-Caixas/`
* **`wooden_crate_3d.obj`**: Caixote de madeira rústica com tábuas e ripas reforçadas.
  * *Substitui:* `furniture_storage_01_16`, `furniture_storage_01_17` (caixotes de madeira).
* **`wooden_table_3d.obj`**: Mesa de madeira com quatro pernas e tampo chanfrado.
  * *Substitui:* `furniture_tables_high_01_0` (mesas altas de sala/jantar).
* **`office_chair_3d.obj`**: Cadeira com encosto e base de suporte.
  * *Substitui:* `furniture_seating_indoor_01_16` (cadeiras de escritório).

### 2. `Eletrodomesticos/`
* **`kitchen_stove_3d.obj`**: Fogão de cozinha tradicional com quatro bocas, grade superior e porta de forno com visor.
  * *Substitui:* `appliances_cooking_01_0` (fogão de cozinha).
* **`microwave_oven_3d.obj`**: Forno micro-ondas com painel digital frontal.
  * *Substitui:* `appliances_cooking_01_8` (micro-ondas).
* **`refrigerator_3d.obj`**: Geladeira vertical com portas de freezer e refrigerador.
  * *Substitui:* `appliances_refrigeration_01_0` (geladeira).

### 3. `Itens-de-Chao-Loot/`
* **`military_ammo_can_3d.obj`**: Caixa metálica de munição estilo militar (ammo can) com travas e alça.
  * *Substitui:* caixas de cartucho de escopeta (`Item_ShotgunShellsBox`) e caixas de 9mm (`Item_Bullets9mmBox`).
* **`medical_firstaid_kit_3d.obj`**: Maleta rígida de primeiros socorros com relevo de cruz médica.
  * *Substitui:* Kit de Primeiros Socorros largado no chão (`Item_FirstAidKit`).

---

## ⚙️ Como Ativar no seu Jogo

O arquivo [`pack.manifest`](./pack.manifest) contém todos os bindings registrados. Para enviar esta biblioteca completa diretamente para o Viewpoint, você pode:

1. **Via MCP Server:**
   Pedir para o Antigravity executar:
   `deploy_pack("zomboid-3d-essentials")`
2. **Manualmente:**
   Copiar o conteúdo desta pasta `objetos-prontos-3d` para:
   `C:\Program Files (x86)\Steam\steamapps\workshop\content\108600\3809306528\mods\Viewpoint\42\media\modelpacks\zomboid-3d-essentials\`

---

## 🛠️ Como Adicionar um Novo Modelo 3D nesta Pasta:

1. Exporte ou salve seu modelo em formato **Wavefront `.obj`** dentro da subpasta apropriada.
2. Abra o arquivo [`pack.manifest`](./pack.manifest) e adicione duas linhas:
   ```ini
   # 1. Registra o arquivo
   model.meu_novo_objeto = <Subpasta>/meu_novo_objeto.obj
   
   # 2. Amarra ao sprite 2D do Zomboid:
   # bind.<nome_do_sprite> = <id_modelo> <graus_rotacao> <offset_x> <offset_y> <offset_z> <escala>
   bind.furniture_decor_01_0 = meu_novo_objeto 0.0 0.00 0.00 0.00 1.00
   ```
3. O Viewpoint carregará o modelo automaticamente no próximo boot ou hot-reload!
