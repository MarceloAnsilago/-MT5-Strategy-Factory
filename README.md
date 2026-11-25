# MT5 Strategy Factory

Projeto experimental de estratégias MQL5 para o Strategy Tester do MetaTrader 5. O backup inicial e o dossiê histórico já foram publicados. A revisão v1.23 melhora exclusivamente os relatórios finais e teve sua validação controlada concluída.

O fonte principal é [MT5SF_Estrategia_001.mq5](MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.mq5), atualmente na revisão **1.23**, dedicada aos relatórios finais, compilada sem erros ou avisos e validada no cenário comparativo documentado. A v1.22 foi preservada byte a byte como `MT5SF_Estrategia_001.v1.22_pre_v1.23_001.mq5.bak`; quatro revisões anteriores também permanecem preservadas. Consulte [REVISAO_001_V123.md](REVISAO_001_V123.md) para escopo, verificações e pendências. A compilação da v1.23 requer o header `FinalReportTotals.mqh` ao lado do fonte.

Pela leitura do fonte, a Estratégia 001 usa cruzamento de EMAs em candles fechados, PETR4/M5 como padrão, volume de 100 ações, SL nominal de 1% e TP nominal de 2%. Possui controles de propriedade da exposição e limites de recuperação, e exige execução no Tester. Esses recursos encontrados no código não equivalem a homologação comportamental ou garantia de perda máxima.

O repositório também preserva o fonte de homologação sem negociação, configurações do Tester revisadas e provas de conceito anteriores EURUSD/M15 e PETR4/M15, com documentação e relatórios HTML/PNG. Os resultados dessas provas de conceito não são resultados da Estratégia 001 v1.22.

Consulte [ESTADO_DO_PROJETO.md](ESTADO_DO_PROJETO.md) para resultados, limitações e pendências, e [REVISAO_DO_BACKUP.md](REVISAO_DO_BACKUP.md) para o escopo exato proposto.

O ambiente completo do MT5, executáveis, credenciais, configuração ativa do Codex, bases da corretora, caches e logs não integram o backup. O arquivo `config/mt5-codex.config.example.toml` é somente exemplo inativo, com nomes de variáveis, sem tokens. A biblioteca padrão `Trade/Trade.mqh` deve ser fornecida pela instalação do MT5; não foi duplicada neste snapshot.

A validação da v1.23 inclui 11 testes Python aprovados, script MQL5 com `failures=0` e um backtest comparativo local. Consulte [VALIDACAO_001_V123.md](VALIDACAO_001_V123.md) para configuração, resultados e limites. Não há instrução de execução em conta real.

## Fase 2.1 — executor Python do Strategy Tester

Implementado em Python 3.11+, sem dependências adicionais. A Estratégia 001,
GeraSet e Uni.mql5 não foram modificados. Nesta fase foram executados apenas
testes offline e uma simulação da CLI; nenhum backtest, compilação ou ordem.

### Arquitetura e método

- `strategy_factory/tester.py`: configuração validada, plano offline, orquestração,
  deadline, parada por `run_id`, isolamento e bloqueios exclusivos.
- `strategy_factory/mcp.py`: cliente Streamable HTTP JSON-RPC com inicialização MCP,
  bearer somente em memória, sessão, respostas JSON/SSE e lista fechada de ferramentas.
- `strategy_factory/reports.py`: análise conservadora de HTML MT5 e JSON normalizado.
- `strategy_factory/__main__.py`: CLI com simulação por padrão.
- `tests/test_tester.py`: testes offline, transporte e Tester substituídos por fakes.

O caminho escolhido usa `rico_terminal`: `get_workspace_info` →
`tester_prepare_config` → `tester_run_backtest(wait=false)` →
`tester_get_status` → `tester_get_report(run_id, file_format=json)`.
Em timeout/falha, tenta `tester_stop` somente para o identificador desta execução.
O schema das ferramentas foi inspecionado no catálogo desta sessão; não houve
chamada de início para comprovar a execução completa. MetaEditor permanece fora
do executor; compilação será uma etapa separada futura.

Também foi investigado `/config:arquivo.ini`, documentado oficialmente pela
[MetaQuotes](https://www.metatrader5.com/en/terminal/help/start_advanced/start).
A POC histórica deste projeto confirmou execução pela interface, não sucesso
automático por linha de comando. Não foi implementado fallback que abra outro
terminal ou altere configurações de conta. As ferramentas nativas escolhidas são
documentadas em [MCP capabilities](https://www.metatrader5.com/en/terminal/help/mcp_and_ai/capabilities).

### Uso offline e testes

```powershell
python -m unittest discover -s tests -v
python -m strategy_factory config/tester/factory.example.json
```

O exemplo contém um caminho fictício `C:\MT5-LAB`, não credenciais. A simulação
não lê tokens, não conecta ao MCP e não escreve no MT5. Cada chamada cria
`runs/<dataUTC>_<uuid>/` com `request.json`, `plan.json` e `result.json`.
Os arquivos são criados exclusivamente, sem sobrescrever arquivos anteriores.
`runs/` e seus relatórios ficam fora do Git.

O JSON permite escolher EA compilado absoluto `.ex5`, símbolo, timeframe, datas
ISO com granularidade diária, depósito, moeda, modelo de ticks, alavancagem e
atraso de execução. Spread fixo é rejeitado explicitamente: o schema Rico não
expõe esse parâmetro. Otimização, genética e forward ficam desabilitados.

### Primeiro backtest, somente após autorização específica

1. Autorizar um único cenário curto, confirmando EA compilado de homologação,
   caminho permitido, ativo, datas, depósito, modelo e orçamento de tempo.
2. Criar uma cópia local do JSON em `runs/` com o caminho real permitido pelo
   workspace Rico; não alterar a Estratégia 001 validada.
3. No processo Python, fornecer `MT5_TERMINAL_TOKEN` pelo ambiente seguro já
   utilizado no laboratório. A autenticação da extensão não é automaticamente
   herdada pelo Python. O cliente não lê nem descriptografa DPAPI.
4. Somente então executar, por exemplo:

```powershell
python -m strategy_factory runs/cenario-autorizado.json --execute --authorize-backtest --timeout 120
```

O endpoint padrão é `http://127.0.0.1:22346/mcp`; `--endpoint` aceita somente
HTTP loopback, sem credenciais na URL ou redirecionamentos. O token não é gravado
nos diagnósticos. O adaptador também aceita um callable autenticado
`call_tool(nome, argumentos)` via `TesterRunner` para integração futura.

### Relatórios, falhas e limitações

Em execução autorizada, preserva `prepare.json`, `remote_run.json`, snapshots
`status_*.json`, `report.json` e `analysis.json` no diretório exclusivo. O relatório
JSON é retornado inline pelo MCP e arquivado localmente; não procura arquivos de
outros testes nem consulta o último relatório sem identificar a execução.
O `.ini` remoto recebe nome UUID exclusivo em `MQL5\Profiles\Tester`; não altera
configuração de negociação do terminal. Não há exportação de HTML/XML/XLSX nesta
versão, nem cópia de imagens auxiliares.

O analisador separa drawdown de saldo e de patrimônio, absoluto em dinheiro e
relativo em porcentagem. Extrai lucro líquido, Profit Factor, operações, taxa de
acerto e retorno esperado quando explicitamente reconhecidos. Valores ausentes,
duplicados ou inválidos ficam `null`, com diagnóstico. JSON normalizado aceita
`statistics` com chaves `net_profit`, `profit_factor`,
`balance_drawdown_absolute`, `balance_drawdown_relative`,
`equity_drawdown_absolute`, `equity_drawdown_relative`, `trades`, `win_rate`,
`expected_payoff`. Percentuais JSON usam escala 0–100. Resultados por período
requerem `period_results: [{"period":"2026-11", "net_profit":85, "trades":4}]`;
não são reconstruídos de negócios sem atribuição confiável. HTML suporta rótulos
reconhecidos em português/inglês; outras variantes permanecem inconclusivas.

Os formatos nativos de status/relatório ainda precisam de um teste autorizado.
O executor rejeita status desconhecido e mantém os dados brutos para ajustar o
adaptador. JSON nativo sem campos reconhecidos gera análise inconclusiva, nunca
zeros inventados. `stopped` indica que o processo parou; não comprova sozinho
sucesso econômico ou integridade do histórico. O relatório precisa ser revisado.

O timeout limita a espera de polling; cada requisição HTTP tem timeout de socket
de 15 segundos. Chamadas de rede e confirmação de parada podem exceder o deadline.
Se a parada não for confirmada, o lock permanece e exige reconciliação manual.
Em crash ou início ambíguo sem `run_id`, nunca remove automaticamente o lock.
Há um lock no diretório de execuções e outro por pasta MQL5 em
`%TEMP%\mt5-strategy-factory-locks`, compartilhado por processos do mesmo usuário,
mesmo usando diretórios de execução diferentes. Esses locks não bloqueiam testes
iniciados pela interface, outros usuários ou clientes externos; reservar o Tester
exclusivamente para a Factory durante a execução autorizada.

Diagnósticos de exceções armazenam somente tipo, identificador e estado do lock,
sem mensagens potencialmente sensíveis do transporte. Os retornos brutos de
relatórios podem conter informações da conta de teste; permanecem locais e
ignorados pelo Git. Não existe chamada de trading, alteração de conta, leitura
de credenciais DPAPI, compilação ou otimização no executor.

Validação local desta fase: **33 testes Python aprovados**, incluindo os 11
existentes; extração do HTML histórico confirmada sem executar o MT5.

### Fase 2.2 — compatibilidade observada com o MCP Rico

Uma única homologação autorizada confirmou o fluxo nativo por meio do callable
autenticado da extensão, sem copiar tokens para Python. O EA de homologação
existente recusa execução fora do Tester e tem `OnTick` vazio. A Estratégia 001
foi preservada. Configuração, retornos, histórico e journal permanecem em `runs/`,
fora do Git; nenhuma repetição automática foi realizada.

O status nativo usa `tester_status`, e pode retornar `run_id="0"` quando o Tester
está ocioso. O executor aceita esse campo, preserva o retorno original e não para
um job ativo que pertença a outro identificador. Relatórios com um `run_id`
explícito diferente do solicitado são preservados e rejeitados para análise.

O relatório JSON mínimo observado contém `run_id`, `generated_bars`,
`generated_ticks`, `symbol`, `initial_deposit`, `withdrawal`, `profit`, `deals` e
`trades`. Nesse formato identificado, `profit` alimenta `net_profit`. A ausência
de Profit Factor, drawdown, acerto, expectativa ou períodos continua produzindo
`null`, inclusive em homologação com zero operações. Não deduzir essas métricas
de um saldo inalterado. Tempos do journal do agente e tempo de orquestração têm
escopos distintos; o resultado do executor agora registra também tempos de
orquestração/observação e o timeout configurado.

Validação após as correções: **37 testes Python aprovados**. Os testes continuam
offline; a execução controlada usa os resultados reais preservados localmente,
sem publicar logs ou relatórios da conta de teste.

### Fase 2.3 — EA com operações, preparado para autorização

O [EA Homologacao_002](MQL5/Experts/MT5StrategyFactory/Homologacao_002/MT5SF_Homologacao_002.mq5)
foi compilado com 0 erros e 0 avisos, sem iniciar backtest. Implementa cruzamento
EMA 9/21 comprador, volume mínimo, SL/TP e bloqueio fora do Tester e de otimização.
A análise financeira ganhou métricas adicionais, comparação com evidências nativas
e journal e uma CLI offline. **66 testes aprovados**, com fixtures identificadas
como sintéticas. A Estratégia 001 foi preservada.

Consulte [HOMOLOGACAO_002.md](HOMOLOGACAO_002.md) para cenário exato, configurações
de agentes locais, compilação, uso da análise e limitações. Após autorização
explícita, uma única execução com operações foi concluída e reconciliada; os
relatórios e resultados detalhados permanecem locais, fora do Git.

O adaptador agora trata a convenção nativa de perda bruta como magnitude,
os nomes de operações vencedoras/perdedoras e drawdown relativo. Cálculos de
drawdown absoluto e acerto têm proveniência separada dos campos publicados.
**69 testes aprovados** após as correções; não houve repetição do backtest.
Campos ausentes continuam indisponíveis e validação parcial não é promovida
a completa. Não há conclusão sobre rentabilidade comercial.

### Fase 2.4 — análise automatizada e comparação offline

`strategy_factory.analysis` gera resumos versionados por execução, com parâmetros,
métricas e proveniência, avisos, qualidade dos dados e integridade da reconciliação.
As classificações não avaliam rentabilidade. O executor existente passa a gravar
o resumo automaticamente em futuras execuções autorizadas e em simulações/falhas
tratadas; a CLI também analisa arquivos já existentes sem tocar no MT5.

Coleções comparam resumos e sinalizam cenários, contextos ou evidências incompatíveis.
Não há executor de lote, ranking, geração de estratégias ou otimização.
Consulte [ANALISE_AUTOMATIZADA.md](ANALISE_AUTOMATIZADA.md) para comandos, schema,
classificações e limitações, e `examples/analyze_synthetic.py` para um exemplo
inteiramente sintético. **94 testes aprovados**; nenhum backtest nesta etapa.

### Fase 2.5 — rastreabilidade e enriquecimento

`strategy_factory.traceability` acrescenta evidências por campo ao resumo **1.1**:
solicitado, confirmado pelo MT5, divergente ou não verificável. Inputs efetivos
podem ser extraídos do journal vinculado; INI/SET e snapshots de ativo/histórico
continuam separados como observações/valores solicitados. Custos ausentes não
viram zero. Comparações aceitam resumos 1.0 e 1.1 e exigem confirmações adicionais
antes de habilitar deltas; hashes opacos de contexto não comprovam dados efetivos.

Consulte [RASTREABILIDADE.md](RASTREABILIDADE.md) para contrato de evidências,
comandos, limitações e requisitos que ainda faltam para lotes. **115 testes
aprovados**; evidências históricas preservadas. Nenhum backtest, otimização,
ordem ou alteração de configuração de negociação foi realizado nesta fase.

### Fase 2.6 — manifesto e controle de lotes

Manifesto JSON 1.0, orçamento conservador de tentativas/tempo/armazenamento,
registros de aprovação vinculados ao SHA256 e controle persistente SQLite.
Simulações têm estados, cancelamento, preservação de parciais e retomada explícita,
sem retry automático ou duplicação de tentativas. Os resumos reutilizam o schema
1.1 e preservam custos/evidências desconhecidos como não verificáveis.

O backend real permanece desabilitado mesmo com registro de autorização válido.
Consulte [LOTES.md](LOTES.md) para módulos, comandos, limites e procedimento de
aprovação futura. **139 testes aprovados**; somente testes offline e simulações.
Nenhum EA, credencial ou configuração de negociação foi alterado.

### Fase 3.1 — gerador de estratégias MQL5

`strategy_factory.generator` gera candidatos independentes a partir de JSON
validado, combinando MA, RSI e ADX, entradas long/short, saídas e risco limitado.
Identidades/hashes determinísticos, registro SQLite e criação exclusiva preservam
histórico e bloqueiam duplicações. O template usa candles fechados, volume mínimo
e bloqueios fora do Tester e durante otimização.

Três demos foram produzidos em `MQL5/Experts/MT5StrategyFactory/Generated/` e
compilados pelo MCP Rico: **0 erros e 0 avisos em cada um**. **158 testes aprovados**.
Nenhum backtest ou ordem foi iniciado. Consulte [GERADOR.md](GERADOR.md) para regras,
limites, arquivos, compilação e integração com manifesto/resumo. O backend real
continua desabilitado; a Fase 3.2 depende de nova autorização.

### Fase 3.3A — orquestração segura offline

`strategy_factory.batch_offline` estende o controlador existente com contrato
de cenário/hash, períodos independentes, simulação de falhas e reconciliação
explícita. Consolida resumos auditados 1.1 sem ranking ou soma de carteira.
**225 testes offline aprovados**; execução real permanece bloqueada.
Consulte [FASE_33A_ORQUESTRADOR_LOTES.txt](FASE_33A_ORQUESTRADOR_LOTES.txt)
para contratos, transições, comandos, limitações e critérios da Fase 3.3B.

### Fase 3.3B — integração simulada com o runner individual

`IntegrationBatchController` delega ao `TesterRunner` existente usando apenas
`FakeTesterAdapter`, com autorizações sintéticas individuais, reserva isolada,
parada cooperativa, reconciliação verificável e diagnóstico de aceitação.
**256 testes offline aprovados**; adaptador operacional permanece bloqueado.
Consulte [FASE_33B_INTEGRACAO_SEGURA.txt](FASE_33B_INTEGRACAO_SEGURA.txt).

### Fase 3.3C — transporte de consulta e recuperação persistente

Consultas reais confirmaram MCPs, Rico-DEMO/build 6230 e Tester parado.
`HomologationTransport` restringe chamadas a consultas; a recuperação inspeciona
ledgers sem escrita, e a prontidão distingue evidência efetiva de metadados.
**289 testes offline aprovados**. A proposta supervisionada preserva os três
EAs, sem datas definitivas ou autorização; execução operacional segue bloqueada.
Consulte [FASE_33C_HOMOLOGACAO_TRANSPORTE.txt](FASE_33C_HOMOLOGACAO_TRANSPORTE.txt).

### Fase 3.3D — prontidão e contrato de consentimento offline

Cobertura local sustenta candidatos de desenvolvimento e validação; teste final
permanece pendente. O laboratório de consentimento testa vínculo individual,
consumo atômico, revogação e recuperação sem emitir autorização executável.
**320 testes offline aprovados**. Checklist: **BLOCKED_MISSING_EVIDENCE**;
executor bloqueado, sem backtests ou reservas reais.
Consulte [FASE_33D_PRONTIDAO_OPERACIONAL.txt](FASE_33D_PRONTIDAO_OPERACIONAL.txt).

### Fase 3.3E — auditoria offline de histórico

`history_audit` verifica snapshots locais sem preencher lacunas ou certificar
cobertura. `dataset_policy` vincula fontes, exposição prévia e condições da
corretora a versões imutáveis, com revalidação e revisão retrospectiva 1.1.
Foram observadas 1.252 barras M5 distintas, sete M1 e nenhum registro de ticks
nos snapshots examinados. **354 testes aprovados**, incluindo os 320 anteriores.
Desenvolvimento e validação continuam candidatos; teste final pendente e execução
bloqueada por evidências insuficientes. Consulte
[FASE_33E_AUDITORIA_HISTORICO.txt](FASE_33E_AUDITORIA_HISTORICO.txt).

### Fase 3.3F — plano de aquisição e laboratório offline

`history_acquisition` prepara cobertura M1/M5 de janeiro/2024 a setembro/2026,
com janelas diárias, consentimento vinculado ao hash, orçamento e persistência
verificável. A proposta não afirma disponibilidade e aguarda aprovação humana.
O laboratório aceita somente fontes sintéticas; o adaptador real permanece
bloqueado. **388 testes aprovados**, preservando os 354 anteriores.
Consulte [FASE_33F_PLANO_AQUISICAO_HISTORICO.txt](FASE_33F_PLANO_AQUISICAO_HISTORICO.txt)
e [a proposta sanitizada](config/history/phase33f.proposal.json).

### Fase 3.3G — transporte autorizado, aguardando vigência

`history_transport` implementa a fronteira de aquisição exclusiva M1/M5, com
janela temporal, identidade recente, piloto obrigatório, limites e recibos
persistentes sem repetição automática. O plano original permanece intacto.
A autorização vale em **24/11/2026, das 08:00 às 18:00 UTC−03:00**; a preparação
foi realizada em 23/11, com **zero consultas de histórico**. São **412 testes
offline aprovados**; execução de estratégias continua bloqueada.
Consulte [FASE_33G_AQUISICAO_HISTORICO.txt](FASE_33G_AQUISICAO_HISTORICO.txt).

### Alternativa Python — adaptador exclusivamente offline

`python_history_adapter` mantém o backend real desabilitado e aceita somente
fixtures sintéticas finitas em um laboratório privado separado. Valida identidade
Rico-DEMO/build 6230, UTC, barras, lacunas e consistência M1/M5, com orçamento,
intenção durável, hashes e recibos. Não importa `MetaTrader5`, não conecta ao
terminal e não reaproveita a autorização ou a sessão MCP bloqueada.

A [proposta de homologação](config/history/python_mt5.homologation.proposal.json)
está **não aprovada**, sem conta vinculada, janela de autorização ou calendário
confirmado. Veja [o relatório técnico](FASE_33G_ADAPTADOR_PYTHON_OFFLINE.txt).

Revisão offline de 24/11: interrupção cooperativa com preservação de evidência,
contratos estritos de tipo e rejeição de caminhos por links/reparse points.
**450 testes aprovados**, sem importar `MetaTrader5`; backend real desabilitado.
Veja [a revisão técnica](FASE_33G_REVISAO_ADAPTADOR_PYTHON_OFFLINE.txt).

### Ponte Python — arquitetura preparada, sem ativação

`python_connection_bridge` mantém a ponte nativa incondicionalmente bloqueada.
Fixtures verificam EXE/processo/diretório de dados, identidade demo, ciclo de
conexão, erros imediatos e desligamento com orçamento reservado. Um índice
transacional modela tentativas compartilhadas MCP/Python, sem alterar a sessão
3.3G. **470 testes offline aprovados**, sem importar `MetaTrader5`.
Veja [o relatório](FASE_33G_PREPARACAO_PONTE_PYTHON.txt) e a
[proposta de diagnóstico sem histórico](config/history/python_mt5.connection-diagnostic.proposal.json),
ainda não aprovada.

### Fase 3.3H — decisão de isolamento

Recomendada uma instalação MT5 dedicada à Factory, em modo padrão, com EXE,
processo, data_path e conta demo vinculados a um novo plano. A instalação atual
e a sessão 3.3G permanecem intactas; nenhuma instalação ou conexão foi realizada.
**470 testes offline aprovados**. Leia
[FASE_33H_ANALISE_ISOLAMENTO_MT5.txt](FASE_33H_ANALISE_ISOLAMENTO_MT5.txt)
para evidências, limitações e o primeiro diagnóstico proposto, somente de metadados.

### Fase 3.3I — preparação local do MT5 dedicado

Inspeção local identificou oito diretórios de terminal e uma cópia antiga da POC,
sem comprovar uma instalação já disponível para dedicação exclusiva. Recomendado
destino novo e vazio, com confirmações humanas separadas para instalar e iniciar.
Inventários privados preparados; **470 testes offline aprovados**.
Nenhum instalador ou terminal foi iniciado. Consulte
[FASE_33I_PREPARACAO_MT5_DEDICADO.txt](FASE_33I_PREPARACAO_MT5_DEDICADO.txt).

### Fase 3.3J-H1 — instalador preparado, sem execução

Instalador oficial MetaQuotes baixado em pasta privada, com SHA256 registrado,
assinatura Authenticode válida e cadeia de certificados validada online.
Destino futuro criado vazio: `C:\estrategia\infra\mt5-factory`.
Integridade dos conjuntos protegidos preservada; **470 testes offline aprovados**.
Compatibilidade com Rico-DEMO pendente. H2 aguarda nova autorização humana.
Consulte [FASE_33J_H1_PREPARACAO_INSTALADOR.txt](FASE_33J_H1_PREPARACAO_INSTALADOR.txt).

### Fase 3.3J-H2 — abertura e inspeção limitada

Instalador revalidado e aberto uma única vez, sem iniciar instalação.
Tela inicial observada; opções de diretório e primeira abertura não homologadas
por ausência de resposta visível à interação automatizada. Solicitado cancelamento
manual; processo posteriormente ausente e destino dedicado vazio.
Inventários protegidos sem diferenças; **470 testes offline aprovados**.
H3 permanece bloqueada, aguardando autorização e resolução dessas pendências.
Consulte [FASE_33J_H2_INSPECAO_INSTALADOR.txt](FASE_33J_H2_INSPECAO_INSTALADOR.txt).

### Fase 3.3J-H2B — inspeção manual e cancelamento confirmados

Campos de pasta e grupo observados; o destino padrão corresponde a uma
instalação existente e deve ser evitado. Instalador cancelado manualmente,
processo ausente e destino Factory vazio. Binários, MQL5 e arquivos anteriores
da Factory preservados; diferença em `terminal.ini` da Rico registrada para
revisão humana, sem restauração ou atribuição de causa.
**470 testes offline aprovados**. H3 não autorizada; controle da primeira
abertura do terminal permanece pendente.
Consulte [FASE_33J_H2B_INSPECAO_MANUAL.txt](FASE_33J_H2B_INSPECAO_MANUAL.txt).

### Fase 3.3J-H3 — instalação dedicada com ocorrências

MT5 build 6328 instalado na pasta exclusiva. A primeira abertura automática
recebeu autorização humana adicional; nenhuma conta foi configurada pelo agente.
Binários e MQL5 anteriores preservados. Dois atalhos públicos foram substituídos,
o MetaEditor dedicado também iniciou e houve conflito de porta MCP: ocorrências
registradas para revisão humana, sem correção automática.
**470 testes offline aprovados**. Não avançar para conta, API ou histórico.
Consulte [FASE_33J_H3_INSTALACAO_SUPERVISIONADA.txt](FASE_33J_H3_INSTALACAO_SUPERVISIONADA.txt).

### Fase 3.3J-H4 — diagnóstico e atalhos pendentes

Conflito confirmado na porta **22346**, ocupada pelo terminal Rico; o número
122346 transcrito na H3 foi corrigido pelo log original. Logs registram 131
compilações na área dedicada; MQL5 anterior preservado. A restauração dos dois
atalhos públicos foi bloqueada pela permissão Windows, sem alteração parcial.
Terminal dedicado segue aberto; nenhum processo encerrado ou MCP modificado.
**470 testes offline aprovados**. Aguardar orientação humana.
Consulte [FASE_33J_H4_DIAGNOSTICO_E_ATALHOS.txt](FASE_33J_H4_DIAGNOSTICO_E_ATALHOS.txt).

### Fase 3.3J-H5A — fechamento manual confirmado

Terminal dedicado fechado manualmente pelo responsável; PID e caminho ausentes
na conferência posterior. MetaEditor dedicado permanece fechado. Terminal e
MetaEditor Rico mantêm as identidades e respondem ao Windows, sem reinicialização
observada. Alterações de configuração/log dedicados registradas sem restauração.
**470 testes offline aprovados**. MCP e atalhos permanecem pendentes; aguardar
nova autorização.
Consulte [FASE_33J_H5A_FECHAMENTO_TERMINAL.txt](FASE_33J_H5A_FECHAMENTO_TERMINAL.txt).

### Fase 3.3J-H5B — plano offline MCP, edição bloqueada

Arquivo Factory identificado e backup privado verificado. Portas candidatas
22356/22355 sem ocupação ou reserva nos escopos consultados. Nenhum endpoint
alterado: a documentação oficial encontrada não especifica a edição offline
do INI para build 6328, condição de parada exigida nesta fase.
**470 testes offline aprovados**; Rico, clientes, atalhos e arquivos protegidos
sem diferenças observadas. Isolamento ainda pendente; aguardar nova orientação.
Consulte [FASE_33J_H5B_ISOLAMENTO_MCP.txt](FASE_33J_H5B_ISOLAMENTO_MCP.txt).

### Fase 3.3J-H5C — endpoint Terminal persistido pela interface

Terminal Factory salvo em `http://127.0.0.1:22356/mcp`, sem alterar outros
campos MCP. Endpoint MetaEditor continua em 22345, pendente de inspeção separada.
Terminal fechado manualmente e processos dedicados ausentes; Rico e arquivos
protegidos anteriores preservados. **470 testes offline aprovados**.
Nenhuma conexão MCP realizada; funcionamento do novo endpoint não homologado.
Consulte [FASE_33J_H5C_CONFIGURACAO_MCP_INTERFACE.txt](FASE_33J_H5C_CONFIGURACAO_MCP_INTERFACE.txt).

Retomada em 25/11/2026: persistência Terminal em 22356 confirmada; editor
permanece em 22345. Processos dedicados ausentes; 470 testes offline aprovados.
MCP Rico intacto; diferenças históricas em outros arquivos discriminadas no
[relatório de retomada](FASE_33J_H5C_RETOMADA_VERIFICACAO.txt).
Aguardar autorização humana para configurar o editor pela interface oficial.

### Fase 3.3J-H5D — MetaEditor configurado manualmente

Após interrupção por falta de resposta da interface, o usuário configurou o
MetaEditor Factory em `http://127.0.0.1:22355/mcp` e o fechou normalmente.
Persistência confirmada por leitura; Terminal Factory mantido em 22356.
Processos dedicados ausentes; Rico e demais arquivos protegidos preservados
no baseline H5D. **470 testes offline aprovados**. MCP não homologado.
Consulte [FASE_33J_H5D_METAEDITOR_MCP.txt](FASE_33J_H5D_METAEDITOR_MCP.txt).

### Fase 3.3J-H5E — homologação interrompida em erro HTTP

Chave MetaEditor Factory regenerada pelo humano; quatro listeners identificados.
Clientes exclusivos preparados com helper sem segredo no TOML e allowlist de
workspace, mas **desativados** após erro HTTP na primeira requisição initialize
do MetaEditor. Nenhuma ferramenta de workspace executada; Terminal não sondado.
Aplicativos dedicados fechados; Rico preservada; **470 testes offline aprovados**.
Homologação pendente de diagnóstico autorizado, sem nova tentativa automática.
Consulte [FASE_33J_H5E_HOMOLOGACAO_MCP.txt](FASE_33J_H5E_HOMOLOGACAO_MCP.txt).

### Fase 3.3J-H5F — diagnóstico HTTP 401

Uma única requisição `initialize` autorizada ao MetaEditor Factory retornou
**HTTP 401**, sem repetição ou outras chamadas MCP. A categoria de rejeição
de autenticação foi identificada; o motivo específico permanece pendente.
MetaEditor fechado manualmente; Terminal Factory não iniciado. Rico preservada
no baseline H5F; clientes Factory permanecem desativados. **470 testes offline
aprovados**. Nenhuma configuração ou credencial alterada nesta fase.
Consulte [FASE_33J_H5F_DIAGNOSTICO_HTTP_MCP.txt](FASE_33J_H5F_DIAGNOSTICO_HTTP_MCP.txt).

### Fase 3.3J-H5G — investigação offline da autenticação

Hipótese principal, com confiança moderada: representação de `ApiKey` do INI
enviada diretamente como token sem equivalência comprovada com a origem oficial
da interface. Montagem Bearer e caracteres conferidos sem defeito demonstrado;
causa definitiva ainda não confirmada. **8 verificações fictícias e 470 testes
offline aprovados**. Nenhuma conexão, abertura ou correção; integridade preservada.
Consulte [FASE_33J_H5G_DIAGNOSTICO_AUTENTICACAO.txt](FASE_33J_H5G_DIAGNOSTICO_AUTENTICACAO.txt).

### Fase 3.3J-H5H — credenciais comparadas: DIFERENTES

Comparação local em memória confirmou diferença entre a credencial atual obtida
por Copiar na interface Factory e o campo do INI usado pelo helper H5E.
Sem correção ou conexão MCP; a causa definitiva do HTTP 401 não foi demonstrada.
Factory fechada, Rico preservada e clientes Factory desativados. **9 verificações
fictícias e 470 testes offline aprovados**.
Consulte [FASE_33J_H5H_COMPARACAO_CREDENCIAIS.txt](FASE_33J_H5H_COMPARACAO_CREDENCIAIS.txt).

### Fase 3.3J-H5I-A — protótipo privado de credencial protegida

Protótipo isolado com Gerenciador de Credenciais Windows e helper via pipe,
validado somente com dados fictícios: **32 verificações e 470 testes offline
aprovados**. Entradas de teste removidas; configurações e helper H5E intactos.
Factory fechada, clientes desativados e Rico preservada. Aplicação real e
sondagem única ficam propostas para H5I-B, sob nova autorização.
Consulte [FASE_33J_H5I_A_PREPARACAO_AUTENTICACAO.txt](FASE_33J_H5I_A_PREPARACAO_AUTENTICACAO.txt).
