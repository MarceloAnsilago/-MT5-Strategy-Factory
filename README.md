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
