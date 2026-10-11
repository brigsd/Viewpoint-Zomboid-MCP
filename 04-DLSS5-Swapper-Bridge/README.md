# 🧠 Módulo 04: DLSS 5 Swapper Bridge

Módulo **só de documentação**. Explica o que o **DLSS 5 Swapper** faz, por que ele não funciona bem com o *Project Zomboid Build 42* e qual é a alternativa segura dentro desta suíte.

📖 **Documento principal:** [DLSS5_MANUAL_E_DIAGNOSTICO.md](./DLSS5_MANUAL_E_DIAGNOSTICO.md)

---

## ⚡ Resumo Rápido

| Pergunta | Resposta curta |
| :--- | :--- |
| **O que é o DLSS 5 Swapper?** | Um injetor que instala ReShade 6.8 + DLSS Feeder + NVIDIA Streamline para forçar DLSS em jogos sem suporte nativo. |
| **O DLSS deixa o jogo mais realista?** | Não muda luz, sombra nem cor. Ele estabiliza a imagem (sem cintilação), deixa mais nítido e aumenta o FPS. |
| **Funciona no Project Zomboid?** | Não de forma confiável. O Zomboid roda OpenGL via Java (LWJGL), e o Swapper espera DirectX ou Vulkan. Pode fechar o jogo sem aviso. |
| **Qual a alternativa?** | O shaderpack [`ultra-performance`](../03-Shaders-Customizados/ultra-performance/) do Módulo 03: TAA nativo do Viewpoint + nitidez em GLSL + pipeline leve. |

---

## 📑 O que o Manual Cobre

1. Onde o utilitário fica instalado no sistema.
2. Componentes do Swapper: ReShade, DLSS Feeder, RenoDX e as DLLs da NVIDIA (Super Resolution, Frame Generation, Ray Reconstruction).
3. O que o DLSS faz e o que ele não faz.
4. Comparação entre jogos com DirectX/Vulkan e o Zomboid (OpenGL + JVM).
5. Por que o `ultra-performance` entrega benefícios parecidos sem risco.
6. Passo a passo para injetar e desinjetar (restaurar) um jogo pelo Swapper.

---

## ⚠️ Veja Também

* [GOTCHAS.md §7](../GOTCHAS.md): Incompatibilidade do DLSS 5 Swapper com Java OpenGL
* [Módulo 03](../03-Shaders-Customizados/): Shaders customizados
