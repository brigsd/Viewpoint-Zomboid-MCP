# Backlog aberto

Candidatos. Nenhum item autoriza implementação: para começar, ele vira um plano a partir do [`MODELO.md`](MODELO.md).

A camada 2 (base de conhecimento da API) saiu daqui em 2026-10-11 e foi [concluída](concluidos/2026-10-11-base-de-conhecimento-api.md) no mesmo dia. Os modelos 3D automáticos saíram em 2026-10-12 e viraram o plano ativo [Esteira de porte 3D](2026-10-12-esteira-de-porte-3d.md).

| Candidato | Origem | Próximo recorte |
| :--- | :--- | :--- |
| Linha de base de erros vanilla no `lua_errors` | Lab headless | Gravar os erros de um boot sem mods e subtrair, para mostrar só o que o mod causou. Hoje aparecem `require` de menus do cliente, ThumpSound, RoomDef e similares. |
| Senha de admin fora da linha de comando | Lab headless | A senha de teste vai em `-adminpassword` e fica visível para outros processos da máquina. Investigar se o servidor aceita a senha por arquivo ou entrada padrão depois do primeiro boot. |
| Modo cliente automatizado | Lab headless | Abrir o cliente apontando para o servidor do lab, entrar sozinho, testar UI/menus/Viewpoint, tirar screenshot e fechar. Cobre o que o headless não alcança (jogador, interface, renderização). |
| Reportar bugs do ZombieBuddy 2.3.2 no Windows | Lab headless | O premain experimental quebra no sinal `INFO`, que não existe no Windows, e o `/log` procura um `console.txt` que o servidor dedicado não gera. Montar um relato reproduzível para o autor (zed-0xff). |
| `Viewpoint.jar` proprietário no repositório | README do Módulo 02 | A licença do Viewpoint proíbe redistribuir e o repositório no GitHub contém dois `Viewpoint.jar`. Decidir: tirar do git e baixar da Workshop no setup, ou manter se o repositório for privado. |
| Nomes dos parâmetros nas assinaturas | Camada 2 | O jar tem `LocalVariableTable`; ler os nomes deixaria `getCraftRecipe(String name)` em vez de `getCraftRecipe(String)`. |
| Globais Lua dentro de blocos `if` | Camada 2 | O extrator só pega definições do nível de cima do arquivo; medir quantas ficam de fora (ex.: dentro de `if isClient() then`). |
| Conferência visual automática no cliente (Objetos 3D, plano 3) | Plano do acervo | O lab não tem tela, e o Viewpoint só roda no cliente. Abrir o cliente sozinho, ir até o objeto, tirar print com F9 e fechar. Até lá, a conferência visual é do usuário. |
| Categorias dos tilesets `location_*` | Plano do acervo | 1.840 objetos ainda caem em "outros" (teatro, igreja, posto, bancos…). Refinar as regras de `acervo/categorize.py` pelas propriedades. |
