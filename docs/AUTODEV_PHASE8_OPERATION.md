# Fase 8 — homologação operacional de leitura

26/11/2026 — America/Sao_Paulo. Base local: `6cb60dc`.

**Resultado: autenticação, protocolo, catálogo, definição, schema e identidade confirmados na última consulta; homologação recusada porque o servidor declara raiz de escrita fora da MQL5 dedicada.** O diagnóstico final é `workspace_write_root_outside`. Nenhuma operação de escrita MCP foi enviada e nenhuma raiz mais ampla foi aceita. O terminal teve disponibilidade passiva conferida, mas seu protocolo, conta e workspace não foram homologados.

Foram três tentativas independentes com aceites específicos: primeira interrompida antes de rede por credencial indisponível; segunda com quatro POSTs e rejeição do resultado sob diagnóstico inicialmente genérico; terceira, autorizada adicionalmente, com quatro POSTs e diagnóstico preciso. Total: oito POSTs e duas consultas get_workspace_info; zero retries/fallback em cada tentativa. Todas as guardas foram preservadas. Não repetir consulta sem plano/aceite novo e correção prévia do impedimento.

O diagnóstico genérico da segunda tentativa foi uma limitação do adaptador corrigida nesta entrega. Nenhum corpo anterior foi recuperado de logs nem reconstruído. Testes finais: 130 AutoDev, 513 produto (490 anteriores + 23 novos), 81 compatibilidade e 18 aceitação independente; todos aprovados, sem pulos. O módulo workspace_review e os testes históricos permanecem intactos.

## Escopo e implementação

O proprietário autorizou revisão/correção do adaptador, abertura dos aplicativos dedicados, inspeção local, testes, documentação e commits locais. A consulta de workspace exige validações anteriores e a confirmação literal do mecanismo: `Autorizo a consulta de workspace pela ferramenta apresentada.` Cada tentativa possui aceite e guarda próprios; nenhuma guarda anterior pode ser reaproveitada.

`strategy_factory/workspace_homologation.py` implementa uma política específica para o contrato exato revisado na fase 5. O verificador legado, sua classificação conservadora e as proteções do controlador permanecem inalterados. O novo adaptador usa as funções de protocolo e o transporte HTTP preservados da H5J-C por injeção explícita; não substitui métodos nem transforma uma recusa do verificador legado em aprovação.

Antes de credenciais e de cada POST: conferir PID/criação, EXE/hash/build/assinatura, origem dos dados, listener exclusivo no endereço local, configurações fixadas por hash e atestado de inicialização segura do terminal dedicado. O entry point privado está em `runs/phase8_workspace_20261126*/live_attempt.py`; importá-lo não executa consulta. A preparação não lê cofre nem envia rede. A execução exige confirmação por stdin e locks do controlador, cria guarda exclusiva com flush/fsync antes do cofre e termina definitivamente após sucesso ou falha.

Sequência única: initialize, notifications/initialized, tools/list e tools/call get_workspace_info com `{}`. MCP exatamente 2025-06-18, sessão apenas em memória, catálogo histórico exato de 23 ferramentas sem paginação, fingerprint integral `e7261a54334778f38f7f0caa56c3fc8d3a2cd7fa327ee8c9f28198bd755ddfa2`, structuredContent obrigatório. O validador offline original exige schema, identidade MQL5 e raízes de escrita restritas. Quatro POSTs previstos; teto absoluto seis não autoriza chamadas extras. Zero retries, fallback, DELETE, GET, reconexão ou repetição do tools/call.

Respostas brutas, conteúdo textual, Community, identificadores de sessão e credenciais não são registrados. Persistem somente contagens, estados HTTP e categorias locais fixas. A existência de HTTP 200 não homologa o resultado. A versão declarada no relatório é a exigida pela política; a negociação só é comprovada quando initialize passa.

## Aplicativos e credencial

Executáveis dedicados: `C:/estrategia/infra/mt5-factory/MetaEditor64.exe` e `terminal64.exe`, com dados próprios em `C:/Users/User/AppData/Roaming/MetaQuotes/Terminal/AEF1E6F57078EAB3775179FCBD94D671`. Portas locais 22355 e 22356. Abertura pelo inicializador existente, sem alterar sua segurança; terminal recebe safe-start.ini com Experts/trading/DLL desabilitados. Modo de conta e APIs do terminal não são consultados por esta homologação do editor.

A credencial do cofre é exclusiva do MetaEditor Factory e persiste somente no logon. Quando ausente, a recuperação supervisionada reutiliza o importador H5I-B intacto. Exige histórico e roaming do clipboard desativados, cópia nova originada no PID exato do MetaEditor, parser oficial do endpoint 22355, alvo ausente e nenhuma sobrescrita. Conferência em memória e limpeza do clipboard são obrigatórias. Cópia originada no terminal é recusada antes de ler seu conteúdo. Não usar ApiKey do INI, não gerar chave substituta, não enviar segredo ao chat, não alterar helper, persistência ou clientes Codex.

## Impedimento de permissões

A documentação oficial descreve acesso do ambiente a MQL5, Tester, Logs e Common, e documenta habilitação, endereço e chave nas opções MCP. Não foi encontrada ali uma opção para restringir write_roots somente à MQL5, nem chave desse tipo no assistant.ini inspecionado. Isso não prova que a restrição seja impossível em todas as versões. Não habilitar shell perigoso, mudar ACLs, atualizar binários, usar junctions ou ampliar a política local para fabricar compatibilidade. Referências: [configuração oficial](https://www.metatrader5.com/en/metaeditor/help/mcp_and_ai/configuration), [capacidades oficiais](https://www.metatrader5.com/en/metaeditor/help/mcp_and_ai/capabilities).

A próxima decisão é obter um meio suportado de restringir o servidor ao contrato local, ou submeter uma proposta separada de isolamento/política à revisão humana. O caminho externo não foi persistido; não se presume se corresponde a Common, Tester ou outro diretório. Um novo aceite de consulta, sozinho, não corrige essa incompatibilidade. As restrições atuais impedem o agente de relaxar suas próprias proteções.

## Planejamento existente e continuidade

O plano `C:/CodexAutoDev/plans/factory_phase5.json` contém três tarefas offline já concluídas e termina em `new-live-workspace-homologation`. O plano `strategy_factory_first_run.json` é proposta antiga já superada pelas entregas e não deve ser executado para repetir revisão. Não há fila sucessora aprovada que sustente oito horas de desenvolvimento.

Os documentos do produto mantêm gates distintos: abertura/identidade dedicada (H6), conexão Python e metadados (H7), transporte e aquisição histórica com plano/conta/janela próprios (3.3F/3.3G) e revisão operacional dos lotes (3.3D). Uma leitura de workspace do MetaEditor não libera API do terminal, aquisição de dados, compilação, Tester, conta ou ordens. Não retomar a sessão 3.3G bloqueada nem reutilizar resultados conhecidos como teste independente.

Há um impedimento objetivo adicional no executor: `factory_phase5.py` limita `ALLOWED` aos seis arquivos da fase 5, usa referência Git histórica fixa e mantém operações externas bloqueadas; `FactoryVerifier` recusa alterações fora desses caminhos. `profile_manager.py` também fixa o plano da fase 5. Ativar orçamento não amplia essa fronteira. Nesta fase nenhum desses controles foi alterado. Um sucessor requer revisão humana da fronteira de execução para os caminhos do produto e um plano com critérios verificáveis; a restrição de não modificar as próprias proteções impede o agente de liberar isso sozinho. Não encaminhar pelo executor genérico para contornar a restrição.

## Perfil prolongado e atalhos

Perfil-base validado em `C:/CodexAutoDev/config.autonomous.json`, preparado e desativado. Proposta: 480 minutos acumulados, 50 chamadas, uma correção por tarefa, 500.000 tokens novos, 10.000.000 cache e 100.000 saída; inclui três chamadas e 391,875 segundos anteriores. Consumo desta conversa não integra automaticamente o ledger do worker. Sandbox MXC, auto_review, política congelada, parada por limite oficial, consumo desconhecido e integridade continuam obrigatórios.

Atalhos reais conferidos: apontam para `C:/CodexAutoDev/launchers/autodev.cmd` e o launcher existente. Agora use **AutoDev - Status** para consultar a pendência; **AutoDev - Relatório** pode mostrar o consolidado diário histórico, e as evidências atuais estão em `C:/CodexAutoDev/reports/phase8-*`.

Somente depois de resolver homologação e plano/fronteira sucessores:

1. Dois cliques em **AutoDev - Iniciar**; se perfil já selecionado, pressione **P** nos três segundos iniciais para escolher limites.
2. Informe duração em minutos, chamadas, correções e os três tetos; Enter conserva proposta. Confira e digite **ATIVAR** no console. Esse passo salva e termina sem chamada.
3. Dois cliques em **AutoDev - Iniciar** novamente; após três segundos, o worker inicia/retoma. **Esc** cancela nessa contagem.
4. Após reiniciar o computador, **AutoDev - Retomar**. **Pausar** e **Encerrar** preservam checkpoint; conferir **Status**.

Esses passos descrevem o fluxo real do atalho, não uma declaração de prontidão atual. Sem plano sucessor e revisão da fronteira, o atalho pode parar no gate ou concluir sem desenvolver produto. Não ativar um orçamento para ocultar esse impedimento.

Resultados, autorizações de cada tentativa, commit final e situação conclusiva estão no relatório local `C:/CodexAutoDev/reports/phase8-final.md` e seus JSONs. Nenhum push automático, compra de créditos, operação financeira, mudança de projeto ou enfraquecimento das proteções foi autorizado ou realizado.
