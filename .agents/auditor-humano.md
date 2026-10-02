# 👤 Protocolo de Governança: Auditoria Humana (Human Quality Inspector & QA Lead)

Este documento estabelece o **protocolo oficial de auditoria humana** para aprovação, reprovação ou ajuste fino de malhas 3D destinadas à suíte *Project Zomboid Build 42 (Viewpoint 3D)*. O auditor humano atua como a autoridade máxima de controle de qualidade (QA) antes de qualquer modelo ser injetado no jogo ativo.

---

## 🎯 Por que a Auditoria Humana é Crucial no Viewpoint?

No Project Zomboid clássico (isométrico 2.5D), os objetos são sprites 2D estáticos pré-desenhados a 45 graus. Na câmera em Primeira Pessoa (*Viewpoint*), esses sprites originais se revelam como **"folhas de papel" ou papéis de parede achatados (billboards)**:
* Quando o jogador se aproxima ou olha de lado, o objeto não tem espessura nem profundidade.
* As sombras dinâmicas do motor PBR do Viewpoint não encontram faces poligonais para projetar penumbras reais.
* A imersão de um jogo de sobrevivência em primeira pessoa é imediatamente rompida.

A substituição por modelos 3D (`.obj`) resolve isso conferindo **volumetria real e oclusão de luz**. No entanto, modelos 3D mal calibrados (fora de escala, com normais invertidas ou texturas distorcidas) causam anomalias grotescas em primeira pessoa. O olho humano é insubstituível para validar o realismo e a escala.

---

## 🔍 Checklist das 5 Dimensões de Auditoria

Ao abrir a pasta de inspeção de um objeto (`05-Model-3D-Extractor-MCP/objetos-extraidos-vanilla/inspecoes/<objeto>/`), o operador humano deve avaliar as imagens geradas pelo [Agente Inspetor Visual](file:///c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/.agents/inspetor-visual.md) seguindo estes 5 critérios rigorosos:

### 1. Volumetria Tridimensional (Anti-Billboard)
* **Pergunta:** O modelo possui massa poligonal sólida quando observado em perspectiva axonométrica (`vista_isometrica.png`)?
* **O que reprovar:** Modelos que parecem placas finas sem laterais, caixas com fundos abertos visíveis pelo jogador agachado, ou geometrias vazias por dentro.

### 2. Escala e Proporções em Metros
* **Pergunta:** O objeto é compatível com a escala do sobrevivente humano (1 tile = 1.0m x 1.0m)?
* **Tolerâncias de Referência:**
  * Assento de cadeira: `0.40m` a `0.48m` de altura do solo.
  * Bancada de cozinha / balcão: `0.85m` a `0.95m` de altura.
  * Portas: `2.00m` a `2.10m` de altura por `0.85m` a `0.95m` de vão.
  * Itens pequenos de chão (munição, latas, chaves): entre `0.05m` e `0.20m`.
* **O que reprovar:** Caixas de munição do tamanho de mesas, cadeiras onde o topo do encosto passa de 1.50m, ou portas tão estreitas que parecem postes.

### 3. Orientação de Normais e Sombreamento
* **Pergunta:** As superfícies estão uniformemente iluminadas na `vista_isometrica.png` e `vista_frontal.png`?
* **O que reprovar:** Faces pretas sólidas (causadas por normais voltadas para dentro), iluminação invertida onde a luz vem de baixo, ou superfícies invisíveis por *backface culling*.

### 4. Mapeamento de Texturas (UV & Resolução)
* **Pergunta:** A textura diffuse está orientada de forma natural e sem esticamentos?
* **O que reprovar:** Fibras de madeira esticadas horizontalmente em pés verticais, logotipos espelhados ao contrário, botões de painel distorcidos, ou resolução tão esticada que fica completamente borrada em comparação com o resto da cena.

### 5. Ponto Pivot e Contato com o Solo
* **Pergunta:** Na `vista_frontal.png` e `vista_lateral.png`, o objeto assenta perfeitamente sobre a linha do solo (`Y = 0.00m`)?
* **O que reprovar:** Objetos que flutuam no ar (base em `Y > 0.05m`) ou que estão enterrados no chão (vértices inferiores com `Y < -0.05m`).

---

## 🚦 Workflow de Decisão do Auditor

```text
                     [Abrir inspecoes/<objeto>/]
                                 │
                                 ▼
                     [Verificar as 4 Vistas]
                                 │
             ┌───────────────────┴───────────────────┐
             ▼                                       ▼
      [Tudo Conforme?]                       [Anomalia Detectada]
             │                                       │
      ┌──────┴──────┐                         ┌──────┴──────┐
      ▼             ▼                         ▼             ▼
   [SIM]          [DÚVIDA]                 [Óbvia]      [Complexa]
     │              │                         │             │
     │              ▼                         │             ▼
     │    [Ativar Bancada 3D]                 │   [Ativar Bancada 3D]
     │    (inspeção orbital)                  │   (inspeção orbital)
     │              │                         │             │
     ▼              ▼                         ▼             ▼
[Status: APROVADO]  [Decisão Final]     [Notificar Extrator]
     │                                  (Reajustar Parâmetros)
     ▼
[Liberar para Deploy]
```

---

## 🕹️ Como Acionar a Bancada 3D Interativa (Three.js)

Se a inspeção estática pelas 4 imagens deixar qualquer dúvida sobre curvaturas, encaixes ou alinhamento de normais, o operador deve acionar a **Bancada 3D Interativa** via servidor MCP Mecanifica:

### Chamada MCP:
```json
{
  "ServerName": "mecanifica",
  "ToolName": "ativar_bancada",
  "Arguments": {
    "arquivo": "c:/Users/micro/Desktop/ProjectZomboid-FirstPerson-Suite/05-Model-3D-Extractor-MCP/packs/<pack_id>/models/<objeto>.obj",
    "modo": "isolar",
    "focar": "<objeto>",
    "porta": 8080
  }
}
```

### O que o Operador Humano faz no Navegador:
1. Acesse: `http://localhost:8080/`
2. **Botão Esquerdo do Mouse + Arrastar:** Rotação orbital em 360° para examinar todos os ângulos.
3. **Scroll do Mouse:** Zoom livre até escala milimétrica.
4. **Botão Direito do Mouse + Arrastar:** Pan da câmera (translação lateral e vertical).
5. **Alternar Wireframe:** Tecla de atalho da bancada para checar densidade de triângulos e faces coincidentes.

---

## 📝 Registro de Homologação

Para cada objeto inspecionado, o auditor deve anotar sua decisão no arquivo `relatorio_inspecao.md` da pasta correspondente:

```markdown
### 👤 Parecer da Auditoria Humana
* **Data:** 2026-10-01
* **Auditor:** Operador Técnico
* **Status:** [ ] APROVADO PARA DEPLOY  |  [ ] REPROVADO (NECESSITA REAJUSTE)
* **Observações:**
  - Volumetria: Conforme.
  - Escala métrica: Conforme (0.85m x 0.85m x 0.85m).
  - Ponto de solo: OK na linha Y=0.
  - Textura: Perfeita orientação das ripas de madeira.
* **Ação Autorizada:** Executar `deploy_pack` ou `deploy_ready_pack`.
```
