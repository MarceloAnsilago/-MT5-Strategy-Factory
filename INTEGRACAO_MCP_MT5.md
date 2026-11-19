# MT5 Strategy Factory — integração MCP nativa

Pesquisa e revisão: 18/11/2026. Estado: preparação documental; integração **não validada por chamada de ferramenta MCP**.

## Estado consolidado após as verificações do projeto

Esta revisão atende à preparação documental e não instala software, altera configurações ativas ou executa ferramentas do MT5. O guia pode ser levado a um computador sem MT5. A premissa de ausência de MT5 não corresponde às verificações anteriores deste workspace: a instalação Rico já foi identificada no build 6230, tanto no Terminal quanto no MetaEditor. Não é necessário reinstalar ou atualizar apenas para atingir o piso 6060.

| Evidência já obtida nesta conversa | Alcance da conclusão |
|---|---|
| Executáveis Rico e versões de arquivo identificados | Compatibilidade pelo piso de versão; não prova o catálogo operacional |
| Pasta de dados associada pelo `origin.txt` | Associação persistida; workspace MCP ainda não confirmado |
| Três rodadas de conexão TCP por endpoint bem-sucedidas | Disponibilidade TCP naquele teste |
| Três GETs sem autenticação por endpoint retornaram HTTP 401 | HTTP acessível e requisição sem credenciais rejeitada; não valida autenticação nem protocolo MCP |
| Configuração local criada anteriormente mediante autorização, somente com `get_workspace_info` | Preparação do cliente; configuração global preservada |
| Ferramentas Rico ausentes no catálogo desta sessão | Nenhuma consulta real de workspace executada |

As consultas anteriores de listeners variaram; o teste de conexão posterior não demonstrou falha TCP. Não concluir defeito persistente apenas por ausência em uma fotografia de sockets. Nesta revisão não foram repetidos testes de rede. As evidências de transporte acima são históricas, não garantia de disponibilidade atual.

O arquivo ativo `.codex/config.toml`, criado em etapa posterior à pesquisa inicial, foi preservado nesta revisão. O template inativo continua separado. As instruções abaixo para ativação se destinam ao computador de destino e não devem ser aplicadas novamente sobre configurações existentes sem revisão e autorização.

## Contexto e evidências

`PESQUISA_ARQUITETURA.md` não foi encontrado na busca recursiva, incluindo arquivos ocultos, em `C:\estrategia`. Não foi possível conferir suas decisões; reconciliar este guia com ele antes de implementar a etapa seguinte.

Foram lidos `MT5StrategyFactoryPOC/RESULTADO.md` e `CONTINUACAO.md`. Esses registros descrevem uma POC anterior por executável/interface e um conflito de porta; não comprovam integração MCP. Apesar da premissa de computador sem MT5, existem esses artefatos no workspace. Nesta etapa nenhum executável MT5 foi iniciado, nenhuma instalação foi realizada e nenhum EA existente foi alterado.

Verificação local da preparação inicial: `codex.cmd --version` retornou `codex-cli 0.128.0`; a ajuda confirmou os subcomandos MCP e a opção HTTP com token por variável de ambiente. Isso verifica sintaxe da CLI local, não autenticação ou ferramentas do MT5. Nenhum servidor MT5/MetaEditor consta no catálogo de ferramentas desta sessão.

## 1. Requisitos e versões

A MetaQuotes anunciou o suporte MCP nativo no **MT5 build 6060, em 23/07/2026**. Adotar esse build como piso de introdução e usar Terminal e MetaEditor atualizados da mesma distribuição. A nota não especifica um mínimo independente para o MetaEditor nem garante que o build inicial contenha todo o catálogo atual. Registrar os dois builds e validar as ferramentas na instalação escolhida. [Release oficial](https://www.metatrader5.com/en/releasenotes/terminal/2447)

Requisitos de homologação propostos:

- Windows com ambiente de laboratório exclusivo, conta de usuário sem privilégios administrativos e sem credenciais de conta real.
- MT5 e MetaEditor executando no mesmo Windows que hospeda o processo local do Codex.
- Codex CLI e extensão oficial do Codex no VS Code com suporte MCP HTTP. As fontes consultadas não estabelecem uma versão mínima numérica do Codex para este cenário; não presumir que a versão local equivale à extensão do outro computador.
- Dados históricos e símbolo disponíveis no terminal de laboratório; se necessário, somente conta demo.
- Autorização humana prévia para qualquer instalação, atualização ou mudança de sistema. Este documento não autoriza essas ações futuras.

## 2. Configuração no computador com MT5

### Servidores e autenticação

Em Terminal e MetaEditor: `Tools > Options > MCP`. Habilitar o servidor interno; copiar os detalhes com `Copy`, conferindo cada aplicativo. As configurações são compartilhadas, exceto o endereço, que deve ser exclusivo. Exemplos oficiais: MetaEditor `http://127.0.0.1:22345/mcp`, Terminal `http://127.0.0.1:22346/mcp`; autenticação `Authorization: Bearer <token>`. Confirmar os valores efetivos pela interface. [Configuração MetaQuotes](https://www.metatrader5.com/en/terminal/help/mcp_and_ai/configuration)

O checkbox do Terminal não habilita automaticamente os outros servidores. Manter ambos os aplicativos abertos e verificar o servidor de cada um. O terceiro servidor documentado, marketdata, é remoto e fica fora desta proposta inicial. Não copiar indiscriminadamente todos os blocos exportados.

### Política de segurança proposta

Antes de habilitar conexões:

1. Em `Tools > Options > AI Assistant`, escolher trading proibido, acesso web bloqueado e desabilitar `Dangerous shell operations`. São controles documentados; testar sua aplicação ao cliente externo. Não selecionar apenas confirmação para trading. [Controles MetaQuotes](https://www.metatrader5.com/en/terminal/help/mcp_and_ai/configuration)
2. Usar VM dedicada ou usuário/instância exclusivamente de laboratório. Não disponibilizar diretórios de produção por compartilhamento gravável. Não copiar credenciais, perfis ou configurações de contas reais. Manter Algo Trading desabilitado e nunca anexar EAs a gráficos para esta homologação.
3. Não conceder ao usuário de laboratório escrita sobre EAs existentes. Somente novos arquivos em uma árvore exclusiva da Factory. Uma lista de ferramentas não restringe os argumentos de caminho: o isolamento e as permissões de filesystem são essenciais. Se não for possível garantir isso, não habilitar escrita.
4. Expor apenas loopback `127.0.0.1`; não usar `0.0.0.0`, endereço de LAN, túnel, proxy público ou redirecionamento de portas. Não criar regras de firewall de entrada. Uma alteração de firewall/ACL/VM requer autorização específica antes de execução.
5. Guardar tokens somente no ambiente do processo; não em Git, relatórios ou prompts. Remover tokens de qualquer cópia de tela/exportação. Revogar ou regenerar um token se houver exposição.
6. Limitar as ferramentas no Codex conforme o template anexo. Excluir operações de trading, anexação de EA/script, shell, web e exclusão de arquivos. Revisar também outros servidores/plugins já ativos: este template não os desabilita.
7. Usar somente agentes locais do Tester, sem MQL5 Cloud Network ou agentes remotos. Definir orçamento de tempo, CPUs, memória, disco e quantidade de experimentos antes de iniciar otimizações.

Essas são camadas complementares. O sandbox do Codex não deve ser tratado como sandbox do processo MT5: uma chamada MCP pode escrever usando as permissões do servidor. Também não assumir que o botão Algo Trading, sozinho, bloqueia as ferramentas de trading do MCP. O objetivo de impedir ordens reais depende sobretudo de não existir conta real acessível.

## 3. Codex CLI e extensão no VS Code

O Codex compartilha configuração MCP entre CLI e extensão no mesmo host. Aceita `~/.codex/config.toml` e `.codex/config.toml` do projeto confiável, token por `bearer_token_env_var` e filtro por `enabled_tools`. Na extensão: engrenagem > MCP servers; após configurar, reiniciar a extensão. [MCP no Codex](https://developers.openai.com/codex/mcp)

O template `config/mt5-codex.config.example.toml` está inativo (`enabled = false`) e não contém segredos. Seu conjunto ampliado de ferramentas é referência para homologação posterior, não configuração de primeira conexão. A configuração ativa criada posteriormente usa apenas consulta de workspace. Os nomes `MT5_*_TOKEN` são variáveis locais propostas pelo projeto, não parâmetros da MetaQuotes. Se o catálogo real diferir, interromper e reconciliar o template; não inventar substitutos.

Configuração mínima proposta para primeira conexão no computador de destino, a gravar somente após autorização explícita e sem substituir o arquivo global:

```toml
[mcp_servers.rico_metaeditor]
url = "http://127.0.0.1:22345/mcp"
enabled = true
bearer_token_env_var = "MT5_METAEDITOR_TOKEN"
enabled_tools = ["get_workspace_info"]

[mcp_servers.rico_terminal]
url = "http://127.0.0.1:22346/mcp"
enabled = true
bearer_token_env_var = "MT5_TERMINAL_TOKEN"
enabled_tools = ["get_workspace_info"]
```

Os identificadores `rico_metaeditor` e `rico_terminal` são nomes locais escolhidos para distinguir a instalação; os endpoints são os exemplos MetaQuotes a conferir na interface. Não são nomes de ferramentas. Não habilitar escrita, compilação ou Tester nessa primeira configuração.

### Rota recomendada: configuração por projeto

No computador de laboratório, abrir uma pasta nova no VS Code. Mesclar manualmente o template em `.codex/config.toml`, sem sobrescrever configurações existentes. Conferir URLs com a exportação da MetaQuotes. Inicialmente manter a lista somente com `get_workspace_info`, habilitar os dois servidores e confiar apenas no projeto revisado. Projetos não confiáveis ignoram a camada local `.codex`. [Referência de configuração](https://developers.openai.com/codex/config-reference)

Inserir tokens em uma sessão PowerShell sem gravá-los no histórico:

```powershell
# Requer PowerShell 7; Read-Host -MaskInput não existe no Windows PowerShell 5.1.
$env:MT5_METAEDITOR_TOKEN = Read-Host 'Token MCP do MetaEditor' -MaskInput
$env:MT5_TERMINAL_TOKEN = Read-Host 'Token MCP do Terminal' -MaskInput
codex.cmd --version
codex.cmd mcp list
codex.cmd
```

Dentro da interface interativa da CLI, usar `/mcp` para inspecionar os servidores ativos. `mcp list` mostra configuração; não prova uma chamada ao servidor. Solicitar ao Codex inventário dos nomes e schemas expostos pelos servidores e uma consulta de workspace de cada um. Não fazer escrita nesse primeiro contato.

Na extensão, garantir que o processo do VS Code herde essas variáveis. Encerrar previamente todos os processos do VS Code do laboratório e iniciá-lo pela sessão que contém os tokens; uma janela nova de processo já existente pode não herdar o ambiente novo. Abrir o mesmo projeto, reiniciar a extensão e repetir a consulta de workspace. Não usar tarefas em nuvem, SSH ou WSL nesta homologação: loopback deve alcançar o mesmo Windows do MT5. Não alterar rede para contornar essa condição.

Ao terminar, encerrar os clientes que herdaram os tokens e limpar a sessão:

```powershell
Remove-Item Env:MT5_METAEDITOR_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:MT5_TERMINAL_TOKEN -ErrorAction SilentlyContinue
```

Remover as variáveis do shell não as remove de processos já iniciados.

### Alternativa: registro pela CLI

Escolher esta rota **ou** a rota por projeto, evitando duplicação. Os comandos abaixo escrevem configuração do usuário; executar apenas no ambiente de laboratório, depois de revisar e autorizar a ativação:

```powershell
codex.cmd mcp add metaeditor --url http://127.0.0.1:22345/mcp --bearer-token-env-var MT5_METAEDITOR_TOKEN
codex.cmd mcp add terminal --url http://127.0.0.1:22346/mcp --bearer-token-env-var MT5_TERMINAL_TOKEN
```

Sintaxe confirmada por `codex.cmd mcp add --help` local. Adaptar URLs aos valores oficiais copiados da instalação. Antes de abrir uma sessão de agente, adicionar os filtros do template à configuração gerada. Não há necessidade documentada de um wrapper Python, servidor comunitário ou proxy para esta conexão HTTP nativa. Não usar `mcp login` como substituto do token Bearer fornecido pelo MT5.

Se `codex` resolver para um `.ps1` bloqueado pela ExecutionPolicy, o launcher instalado `codex.cmd` foi validado aqui para comandos de ajuda. Não alterar a política do PowerShell. Se não houver launcher no computador de destino, verificar a instalação e pedir autorização antes de instalar/corrigir programas.

## 4. Ferramentas oficialmente documentadas e capacidades

Seleção relevante; não é o catálogo completo. Nomes literais da [lista oficial MetaQuotes](https://www.metatrader5.com/en/terminal/help/mcp_and_ai/capabilities). Os schemas de argumentos não estão integralmente publicados nessa tabela; obtê-los do servidor antes de chamar.

| Capacidade | Ferramentas |
|---|---|
| Workspace | `get_workspace_info` |
| Criar/alterar MQL5 | `create_new_file`, `create_new_folder`, `write_file`, `replace_text_in_file` |
| Ler | `read_file`, `read_file_by_lines`, `list_directory` |
| Compilar/diagnosticar | `compile_file`, `build_project`, `syntax_check` |
| Configurar teste, genética e forward | `tester_prepare_config`, `tester_prepare_inputs` |
| Iniciar | `tester_run_backtest`, `tester_run_optimization` |
| Acompanhar/cancelar | `tester_get_status`, `tester_wait`, `tester_stop` |
| Recuperar | `tester_get_configuration`, `tester_get_report`, `get_tester_journal` |

**Documentado:** arquivos, compilação com diagnósticos, backtests, otimização genética, forward, acompanhamento, relatório e cancelamento. **Testado por MCP nesta etapa:** nenhum. Não há ferramenta separada de forward nesta seleção: configurá-lo no Tester. O catálogo varia com apps abertos e permissões. Relatório não comprova exportação integral de todos os passes; isso exige homologação.

## 5. Projeto do ciclo e preservação

O fluxo abaixo é proposta de arquitetura, não automação implementada nem promessa de comportamento dos schemas.

1. **Criar estratégia:** registrar hipótese, regras inequívocas, universo, custos, período de treino e forward reservado, critério de avaliação e limites computacionais. Identificador único por experimento; vincular ao experimento pai.
2. **Gerar EA:** produzir fonte novo na árvore isolada. Usar nomes exclusivos e controle de não sobrescrita onde o schema permitir; conferir existência antes. Para a futura implementação, exigir que o EA recuse execução fora do Strategy Tester. Nenhum EA foi gerado agora.
3. **Compilar:** arquivar fonte exato, hashes, build do compilador, diagnósticos e EX5. Só avançar com zero erros; justificar warnings ou corrigi-los. Um erro cria uma nova revisão, preservando o fonte que falhou.
4. **Testar:** salvar INI e SET resolvidos antes da execução. Capturar identificador efetivamente retornado pelo servidor, configuração recuperada, transições de estado e journals. Não presumir nome de campo de ID. Executar uma operação por terminal até homologar concorrência.
5. **Otimizar:** criar execução distinta, com intervalos revisados e orçamento. Reservar forward sem usá-lo para escolher parâmetros. Guardar resultados de treino e forward separadamente, inclusive passes rejeitados se acessíveis.
6. **Analisar:** calcular métricas a partir dos artefatos preservados, registrar origem de cada número e considerar custos, drawdown, número de operações e sensibilidade. Resultado ausente é indisponível, nunca zero. Genética não garante ótimo global e seleção repetida pelo forward contamina a validação.
7. **Propor outra estratégia:** gerar nova hipótese/revisão com vínculo e justificativa; não substituir a estratégia anterior pelo vencedor. Só iniciar o próximo experimento após gravar o encerramento do atual.

Estrutura sugerida para implementação posterior, independente dos diretórios internos do MT5:

```text
experiments/<id>/
  hypothesis.md
  manifest.json
  source/
  binary/
  config/
  diagnostics/
  runs/<run-id>/
    request.json
    response.json
    status.jsonl
    reports/
    journals/
  analysis.md
  SHA256SUMS.txt
```

Esses nomes são convenções do projeto, não endpoints nem campos MCP. `manifest.json` deve registrar parentesco, revisão Git, hashes, builds, catálogo/schema utilizado, símbolo/corretora demo, fuso, datas, modelo de ticks, depósito, moeda, alavancagem, custos, parâmetros fixos e intervalos, critério, agentes e estado final. Registrar disponibilidade/qualidade dos dados e se sementes ou caches puderem ser controlados; não inventar controles.

Guardar respostas brutas com segredos removidos, arquivos INI/SET reais e relatórios com imagens/arquivos dependentes. Preservar formatos originais antes de normalizar. Usar Git para texto/configuração sem credenciais e armazenamento versionado com backup para binários e resultados volumosos. Cache do Tester e histórico do chat não são arquivo de experimentos.

Para não perder o estado em interrupções: escrever registros de status de modo incremental; somente marcar concluído depois de validar e copiar os artefatos. Ao retomar, consultar o estado da execução conhecida antes de iniciar outra. Timeout do cliente não significa cancelamento do Tester. Não repetir automaticamente chamadas de início após resposta ambígua.

## 6. Limitações, riscos e lacunas

- A pesquisa inicial não fez conexão ao MT5. Posteriormente foram testados TCP e GET HTTP sem autenticação (401), conforme estado consolidado acima. Ainda não houve inicialização MCP autenticada, descoberta real de ferramentas, compilação MCP ou backtest MCP. Relatos de POC por interface/executável não comprovam MCP.
- Build 6060 estabelece introdução; a presença dos recursos atuais depende da instalação real. Verificar versão e schema em cada atualização.
- Escopo de arquivos e permissões efetivas devem ser medidos. Se uma ferramenta conseguir modificar produção, o isolamento é insuficiente mesmo que o prompt proíba isso.
- O template limita ferramentas do cliente, não é uma ACL do servidor. Outro cliente com token pode ter capacidades diferentes.
- Bind em loopback não protege contra outros processos locais comprometidos. O token é segredo e o usuário do laboratório deve ser exclusivo.
- Permissões da MetaQuotes, aprovação do Codex e autorização humana são controles distintos. Instalações, atualizações, ACLs, firewall e mudanças do sistema continuam pendentes de autorização explícita; não existe configuração TOML aqui que garanta sozinha essa regra.
- Testes podem depender de histórico baixado e conexão demo. Não habilitar Web/shell perigoso para resolver isso automaticamente. Diagnosticar primeiro e pedir autorização se uma mudança de sistema for necessária.
- Cancelar pode produzir artefatos parciais. Não os apresentar como resultados completos. Formato do relatório, métricas de forward e acesso a todos os passes ainda precisam ser verificados.
- Conflitos de porta e seleção da instância errada são riscos concretos, inclusive mencionados na POC. Confirmar identidade, workspace e processo; não conectar ao primeiro listener encontrado.

## 7. Procedimento de homologação no computador com MT5

O roteiro completo deve ser homologado no computador de destino. Há evidências parciais locais no início deste documento; elas não substituem os critérios operacionais. Criar uma ficha de evidências por passo com horário, build, cliente, resultado esperado/obtido e artefatos, sem tokens.

| Passo | Ação e evidência exigida |
|---|---|
| 0 — referência | Disponibilizar e reconciliar `PESQUISA_ARQUITETURA.md`; revisar este guia e template. |
| 1 — autorização | Registrar autorização específica para instalações/atualizações/configuração do sistema que forem necessárias. Preparar ambiente exclusivo sem produção acessível. |
| 2 — identidade | Registrar versões de Terminal, MetaEditor, CLI e extensão. Anotar pasta de dados de laboratório e ausência de conta real. |
| 3 — segurança | Confirmar trading proibido, web/shell perigoso bloqueados e Algo Trading desativado. Validar proteção dos EAs existentes por permissões, sem tentar alterá-los. |
| 4 — listener | Conferir endereços da interface e listeners loopback. Se houver processo/porta diferente, parar e resolver manualmente. |
| 5 — conexão | Com filtro inicial somente de workspace, comprovar autenticação e identidade de ambos os servidores pela CLI e extensão. Registrar schemas; consultar o catálogo completo apenas em sessão de descoberta supervisionada sem executar suas operações. Restaurar filtros antes de continuar. |
| 6 — fonte descartável | Habilitar apenas ferramentas necessárias. Criar novo arquivo em pasta vazia do laboratório e ler de volta. Alterar só esse arquivo; comparar conteúdo. |
| 7 — compilação | Usar erro de sintaxe deliberado no arquivo descartável e comprovar diagnóstico com arquivo/linha; corrigir em nova revisão e comprovar EX5 com zero erros. |
| 8 — backtest | Usar EA de homologação restrito ao Tester, dados curtos e parâmetros conhecidos. Guardar INI/SET, observar progresso, término, relatório e journal. Conferir também na UI o símbolo, período, inputs e resultado. |
| 9 — otimização | Escolher intervalo pequeno, habilitar genética e confirmar na configuração resolvida/UI. Preservar resultados e comprovar quais passes o MCP entrega. Não inferir genética apenas pela existência de vários testes. |
| 10 — forward | Usar divisão temporal explícita; confirmar datas e resultados separados de treino/forward. Documentar exatamente o formato retornado. |
| 11 — cancelamento | Iniciar teste descartável suficientemente longo, solicitar parada, confirmar estado terminal e inatividade do Tester. Marcar arquivos parciais como cancelados. |
| 12 — retomada | Fechar/reabrir Codex e aplicativos de laboratório em momento seguro. Recuperar um experimento por arquivos/ID e verificar hashes sem depender da conversa. |
| 13 — aprovação | Registrar checklist abaixo, lacunas e decisão. Se algo faltar, declarar integração parcial, não funcional completa. |

Comando de inspeção local proposto para o passo 4, sem alterar rede:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 22345,22346 |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

Usar as portas efetivas, se diferentes. Conferir o processo indicado no Gerenciador de Tarefas e comparar com a instância de laboratório. Acesso negado ou ausência de saída não provam ausência de listener; não elevar privilégios nem mudar firewall automaticamente. Um listener em endereço público/LAN reprova a configuração. Este comando não testa autenticação MCP.

Não há payloads de chamada neste guia: os argumentos devem vir dos schemas descobertos, e não de exemplos inventados.

## 8. Critérios objetivos de integração funcional

- [ ] Ambiente isolado comprovado, sem conta real ou EAs de produção graváveis; nenhuma ordem real enviada.
- [ ] Somente listeners loopback e autenticação válida; token inválido recusado em teste de conexão supervisionado sem executar operações.
- [ ] CLI e extensão chamam os dois servidores corretos; versões e schemas preservados.
- [ ] Escrita/leitura/modificação comprovadas exclusivamente em fonte descartável; produção preservada.
- [ ] Erro de compilação recuperado e corrigido; EX5 gerado e identificado por hash.
- [ ] Backtest inicia, progride e termina; relatório corresponde à configuração e à UI.
- [ ] Otimização genética e forward confirmados em configuração e resultados, sem confundir treino com validação.
- [ ] Cancelamento confirmado; timeout não tratado como parada.
- [ ] Configurações, resultados, diagnósticos e versões sobrevivem à reinicialização; backup verificado.
- [ ] Filtros excluem trading, shell, web e execução em gráficos; política do servidor revisada. Se não for possível verificar um bloqueio sem risco, não testar envio de ordem: manter a integração reprovada para esse requisito.

**Estado atual:** pesquisa revisada e configuração de exemplo preparada; transporte TCP/HTTP verificado anteriormente, mas integração autenticada e critérios operacionais completos permanecem pendentes. Não foram implementados agentes, interface ou gerador de estratégias. Para avançar: reconciliar o documento de arquitetura ausente, revisar o isolamento no destino, conferir processos/endpoints, inserir tokens privadamente no ambiente do cliente, iniciar nova sessão com a configuração carregada e comprovar somente a consulta de workspace antes de autorizar outras capacidades.
