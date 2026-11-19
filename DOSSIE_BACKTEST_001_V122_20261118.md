# Dossiê de evidências — Estratégia 001 v1.22 — 18/11/2026

Consolidado em 19/11/2026 a partir de arquivos existentes e consultas de leitura aos MCPs `rico_metaeditor` e `rico_terminal`. Nenhuma compilação ou nova execução de teste foi realizada. Este documento é uma referência documental de uma execução recuperada, não um relatório integral exportado pelo Tester nem uma homologação de robustez.

## Identificação e alcance

- Estratégia: `MT5SF_Estrategia_001.mq5`, versão declarada **1.22** no fonte e na mensagem de inicialização do journal.
- Execução recuperada: carregamento da configuração às **20:32:31.707 de 18/11/2026**; registros de execução e término às **20:32:32.622**, no horário local registrado pelo host. Não confundir esses horários com os horários simulados do mercado.
- Referência do código: commit inicial `1692728437c8b796bff76646c2dcd60fc84a4a81`, branch `main`. [Backup inicial no GitHub](https://github.com/MarceloAnsilago/-MT5-Strategy-Factory/commit/1692728437c8b796bff76646c2dcd60fc84a4a81).
- **O vínculo com o Run ID `7709658501521644233` ainda não foi comprovado.** A execução é identificada aqui pela sequência temporal, nome do EA, configuração e mensagens do journal; não por esse ID.
- `tester_get_status` para esse ID respondeu `tester_status="stopped"`, `run_id="0"`, `progress_description="tester stopped"`. Isso não confirma a identidade nem a conclusão desse Run ID.
- `tester_get_report`, formato JSON e sem caminho de gravação, respondeu `tester report for single run not found`. Não foi recuperado um relatório JSON por esse identificador. A consulta anterior ao journal também não encontrou o ID no intervalo investigado.

## Configuração e parâmetros

Fonte principal: [MT5SF_Estrategia_001.mq5](MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.mq5).

Configuração carregada, segundo o journal: [MT5SF_Estrategia_001_v122_PETR4_M5_20261116_20261118_everytick.ini](config/tester/MT5SF_Estrategia_001_v122_PETR4_M5_20261116_20261118_everytick.ini). A cópia do projeto foi conferida com a configuração existente na pasta de perfis da Rico no diagnóstico de continuidade.

| Campo | Valor recuperado | Evidência |
|---|---|---|
| Expert | `MT5StrategyFactory\Estrategia_001\MT5SF_Estrategia_001.ex5` | INI e journal |
| Ativo / timeframe | PETR4 / M5 | INI, inputs e journal |
| Intervalo configurado | 16/11/2026 00:00 até 18/11/2026 00:00 | INI e journal |
| Último fechamento simulado registrado | 17/11/2026 17:54:59 | Journal |
| Modelo | `Model=0`, todos os ticks gerados | INI e `every tick generating` no journal; não ticks reais |
| Depósito / moeda | R$ 10.000,00 / BRL | INI e journal |
| Alavancagem | 1:1 | INI e journal |
| Atraso de execução | `ExecutionMode=0` | INI |
| Otimização / forward / visual | Desativados (`0`) | INI |
| Lucro em pips | Desativado (`ProfitInPips=0`) | INI |
| Servidor e agente | Rico-DEMO; agente com build 6230 no registro da sessão | Journal; nome do servidor demo não é login de conta |
| Histórico processado | 85.594 ticks; 190 barras | Journal |
| Qualidade declarada do histórico | 100% | Journal; não comprova qualidade de execução real |

Os valores abaixo estão presentes no bloco de inputs efetivamente registrado na execução. O `.set` preservado é uma evidência auxiliar de inputs salvos; não se presume que ele tenha sido carregado apenas por existir.

| Parâmetro | Valor registrado |
|---|---|
| `InpSymbol` | `PETR4` |
| `InpTimeframe` | `5` (M5) |
| `InpFastPeriod` / `InpSlowPeriod` | `9` / `21` |
| `InpAppliedPrice` | `1` (`PRICE_CLOSE`) |
| `InpShares` | `100.0` |
| `InpStopLossPercent` / `InpTakeProfitPercent` | `1.0` / `2.0` |
| `InpMagic` | `20261118001` — identificador do EA, não login de corretora |
| `InpDeviationPoints` | `5` |
| `InpDiagnosticEnabled` | `true` |
| `InpDiagnosticMaxRecords` | `400` |
| `InpOwnershipMaxRecords` | `600` |
| `InpOwnershipFailureMaxRecords` | `200` |
| `InpFinalMaxDetails` | `100` |
| `InpReconcileMaxAttempts` | `12` |
| `InpDiagnosticWindowTicks` | `8` |
| `InpEquityExtremeStep` | `1.0` |

## Três resultados que devem permanecer separados

| Apuração | Valor | Interpretação e limite |
|---|---:|---|
| Resultado global do teste | **R$ +85,00** | Diferença entre saldo final registrado de R$ 10.085,00 e depósito de R$ 10.000,00. É o total global recuperado, sem atribuição automática de todos os negócios ao EA. |
| Resultado dos negócios atribuídos pelo reconciliador | **R$ +89,00** | Três negócios confirmados: duas entradas e uma saída por TP. O resumo registra lucro bruto de 89,00 e custos de 0,00 para esse conjunto. A soma é restrita aos registros atribuídos, não ao ciclo completo de todas as posições. |
| Fechamento final inconclusivo para atribuição | **R$ −4,00** | Negócio 5, ordem 5, posição 4, `magic=0`, saída sem callback observado/processado. O journal o associa ao encerramento por fim do teste; a prova de propriedade exigida pelo código não foi satisfeita. |

A identidade aritmética é **89,00 − 4,00 = 85,00**. Ela reconcilia os valores recuperados, mas não substitui a prova de atribuição individual. Não reclassificar o negócio 5 como `CONFIRMED` apenas porque o saldo fecha.

| Negócio | Posição / ordem | Classificação v1.22 | Preço / volume | Lucro registrado |
|---|---|---|---|---:|
| 2 | 2 / 2 | `CONFIRMED`, entrada | 45,17 / 100 | R$ 0,00 |
| 3 | 2 / 3 | `CONFIRMED`, saída TP | 44,28 / 100 | R$ +89,00 |
| 4 | 4 / 4 | `CONFIRMED`, entrada | 44,02 / 100 | R$ 0,00 |
| 5 | 4 / 5 | `INCONCLUSIVE`, candidato a fechamento de fim do teste | 43,98 / 100 | R$ −4,00 |

O resumo recuperado informa dois sinais avaliados, duas solicitações de entrada, três negócios próprios processados por callback, uma saída TP e nenhuma saída SL. Isso não equivale a três operações completas. A reconciliação final registra um negócio adicional no total global e diferença de −4,00 em relação ao conjunto confirmado. `OnDeinit` informa `halted=false` e `uncertain=false`; esses estados de execução não eliminam o registro final de atribuição inconclusiva.

Custos registrados como zero não comprovam inclusão de corretagem, emolumentos, aluguel ou todos os custos reais. O intervalo curto não demonstra lucratividade futura, robustez ou comportamento de todas as proteções.

## Fonte, compilação histórica e EX5

O fonte no projeto, o fonte localizado na Rico e o conteúdo do commit inicial foram conferidos como idênticos por bytes no diagnóstico de continuidade. O SHA256 correspondente está na tabela de artefatos abaixo.

O log histórico do MetaEditor registra compilação em **18/11/2026 às 20:29:25**, com **zero erros, zero avisos**, 1096 ms e alvo `AVX2 + FMA3`. Trata-se de evidência anterior recuperada, não de compilação executada para este dossiê. A versão 1.22 também foi encontrada como marcador UTF-16 no EX5 atual.

| Medição | Tamanho |
|---|---:|
| EX5 existente no disco na coleta | **105.308 bytes** |
| Tamanho informado no journal como carregado pelo agente | **105.378 bytes** |
| Diferença observada | **70 bytes** |

**A causa dessa diferença não foi estabelecida.** Não presumir empacotamento, corrupção, recompilação ou troca de arquivo. Não há hash histórico do binário efetivamente carregado que permita compará-lo ao EX5 atual. Datas, caminhos, versão declarada e log de compilação oferecem correspondência circunstancial; não comprovam integralmente a cadeia fonte → EX5 → execução.

O arquivo INI v122 e os inputs registrados são coerentes com a execução recuperada. Isso não comprova qual configuração está selecionada atualmente na interface do Tester.

## Fontes, integridade e preservação

`BASE_RICO` designa a pasta de dados associada à instalação Rico, confirmada pelos dois MCPs. São usados caminhos relativos a essa base para evitar publicar caminhos pessoais de usuário. Os logs completos, EX5 e cache permanecem nos locais originais e fora do Git; não foram copiados para o repositório.

- Fonte primária dos resultados: `BASE_RICO/Tester/logs/20261118.log`, especialmente a sequência local 20:32:31–20:32:32.
- Fonte da compilação histórica: `BASE_RICO/Logs/metaeditor.log`, eventos de 18/11/2026 às 20:24–20:31.
- Configurações de origem: `BASE_RICO/MQL5/Profiles/Tester/`; cópias de referência em `config/tester/`.
- EX5 atual: `BASE_RICO/MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.ex5`.
- Cache candidato: `BASE_RICO/Tester/cache/MT5SF_Estrategia_001.PETR4.M5.20261116_20261118.0.82332519B859279F9816AE980C651F84.tst`. Nome e horário são compatíveis; o conteúdo binário não foi interpretado nem seu vínculo com o Run ID comprovado.
- Métodos: preflight `get_workspace_info`, leitura de arquivos por MCP, consultas `tester_get_status` e `tester_get_report` sem exportação, inspeção local de bytes e cálculo SHA256 em leitura. Nenhuma ferramenta de preparação, compilação ou execução foi chamada.

Os hashes identificam os bytes existentes no momento da coleta. Logs operacionais podem crescer com consultas posteriores; uma mudança futura de hash não prova alteração da execução histórica. Os excertos abaixo são uma seleção, não uma cópia integral nem um relatório exportado. Caminhos pessoais foram substituídos por `BASE_RICO`; textos selecionados não contêm credenciais. A numeração de linhas refere-se ao log decodificado, iniciando em 1.

## Pendências para comparações futuras

1. Estabelecer, se ainda recuperável, o vínculo entre a execução documental e o Run ID `7709658501521644233`.
2. Esclarecer a diferença de tamanhos do EX5 e estabelecer cadeia de hashes de fonte, includes, compilado e configuração em futuras execuções autorizadas.
3. Recuperar um relatório integral, se disponível, sem substituir este dossiê por uma execução nova. Algumas mensagens `FINAL` já estão truncadas no log original; o conteúdo ausente não foi reconstruído.
4. Validar a atribuição do fechamento final mantendo separadas a contabilidade global e a prova individual de propriedade. Não flexibilizar controles de negociação com base nessa inferência documental.
5. Validar falhas e recuperação em cenários controlados e, posteriormente, custos e robustez fora da amostra, sob autorização própria.

Este dossiê pode servir de referência para configuração, eventos e totais observados; ainda não é uma referência de reprodução bit a bit nem uma homologação completa. Não houve commit ou push desta atualização documental.

## SHA256 dos artefatos na coleta documental

Hashes dos arquivos integrais em bytes; não dos excertos sanitizados. O EX5 medido é o atual no disco, não um hash histórico da execução.

| Artefato | Bytes | SHA256 |
|---|---:|---|
| `Fonte no projeto` | 84249 | `d98154e180c1e707469003fffd85357aa7ac10cfa510a4990da13a3ea7eae9af` |
| `INI v122 em config/tester` | 590 | `a32a11f1d39df7b767ba1aa8191ac9064290ff2488b5ff27111bce32abf63481` |
| `SET auxiliar em config/tester` | 1838 | `c19cf15df4a1f49253af584267650724b048994d1cae21c4cdd679b96c00f283` |
| `INI com inputs em config/tester` | 2324 | `161b1b65a363e3ff9c15eb3c10e43125be2dc188ee739a78917b62a6be5f4357` |
| `EX5 atual na Rico` | 105308 | `87744f172091f518c8ab50aa48db9d3e9da50c4527876f06a207d7eb3a95e13c` |
| `Tester/logs/20261118.log` | 927718 | `95fc37512ff42bdbae87be78db538edec6029dba028ac3d4c72ce29ee6233011` |
| `Logs/metaeditor.log` | 768618 | `5127750f855306b868d7f189e944289d9afd58902ef152061ba35cd4ac9201bd` |
| `Cache candidato .0.82332519B859279F9816AE980C651F84.tst` | 6486 | `e15a9ea2caebbaa25896b5ad65d5889807f8c839e324ae4d0e39f375730c785d` |

## Excertos do journal do Tester

Fonte: `BASE_RICO/Tester/logs/20261118.log`. Linhas selecionadas da execução recuperada. As linhas FINAL terminadas em `history` ou `history_` já estão truncadas na origem.

```text
L2471: PD	0	20:32:31.707	Tester	loaded file 'BASE_RICO\MQL5\Profiles\Tester\MT5SF_Estrategia_001_v122_PETR4_M5_20261116_20261118_everytick.ini' with tester settings
L2478: KN	0	20:32:32.412	Tester	PETR4,M5 (Rico-DEMO): testing of Experts\MT5StrategyFactory\Estrategia_001\MT5SF_Estrategia_001.ex5 from 2026.11.16 00:00 to 2026.11.18 00:00
L2483: GD	0	20:32:32.527	Tester	quality of analyzed history is 100%
L2492: FP	0	20:32:32.622	Core 01	expert file added: Experts\MT5StrategyFactory\Estrategia_001\MT5SF_Estrategia_001.ex5. 105378 bytes loaded
L2494: PJ	0	20:32:32.622	Core 01	initial deposit 10000.00 BRL, leverage 1:1
L2504: ER	0	20:32:32.622	Core 01	PETR4,M5 (Rico-DEMO): every tick generating
L2505: KF	0	20:32:32.622	Core 01	PETR4,M5: testing of Experts\MT5StrategyFactory\Estrategia_001\MT5SF_Estrategia_001.ex5 from 2026.11.16 00:00 to 2026.11.18 00:00 started with inputs:
L2506: ON	0	20:32:32.622	Core 01	  InpSymbol=PETR4
L2507: IO	0	20:32:32.622	Core 01	  InpTimeframe=5
L2508: RI	0	20:32:32.622	Core 01	  InpFastPeriod=9
L2509: KO	0	20:32:32.622	Core 01	  InpSlowPeriod=21
L2510: OR	0	20:32:32.622	Core 01	  InpAppliedPrice=1
L2511: IJ	0	20:32:32.622	Core 01	  InpShares=100.0
L2512: ER	0	20:32:32.622	Core 01	  InpStopLossPercent=1.0
L2513: RH	0	20:32:32.622	Core 01	  InpTakeProfitPercent=2.0
L2514: QQ	0	20:32:32.622	Core 01	  InpMagic=20261118001
L2515: OL	0	20:32:32.622	Core 01	  InpDeviationPoints=5
L2516: PE	0	20:32:32.622	Core 01	  InpDiagnosticEnabled=true
L2517: EL	0	20:32:32.622	Core 01	  InpDiagnosticMaxRecords=400
L2518: IK	0	20:32:32.622	Core 01	  InpOwnershipMaxRecords=600
L2519: EL	0	20:32:32.622	Core 01	  InpOwnershipFailureMaxRecords=200
L2520: CI	0	20:32:32.622	Core 01	  InpFinalMaxDetails=100
L2521: OM	0	20:32:32.622	Core 01	  InpReconcileMaxAttempts=12
L2522: IN	0	20:32:32.622	Core 01	  InpDiagnosticWindowTicks=8
L2523: PF	0	20:32:32.622	Core 01	  InpEquityExtremeStep=1.0
L2527: EL	0	20:32:32.622	Core 01	2026.11.16 00:00:00   MT5SF001 v1.22: Tester only. FOK only. Auditoria na inicializacao, transacoes, OnTrade e ticks. Uma tentativa de reparo/fechamento por identificador e cancelamento por ticket, registrados no ambiente Tester.
L2808: LH	0	20:32:32.622	Core 01	2026.11.17 17:54:59   position closed due end of test at 43.98 [#4 buy 100 PETR4 44.02 sl: 43.58 tp: 44.90]
L2812: NP	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL phase=OnTester snapshot_unchanged=false scan_complete=true history_confirmed_own_deals=3 history_own_entries=2 history_own_exits=1 history_SL=0 history_TP=1 inconclusive_records=1 unreadable=0 other_market_deals=0 nonmarket_records=1 callback_observed_all=3 callback_processed_own=3 history_own_without_callback=0 history_own_without_processed_callback=0 processed_callback_without_history=0 queued_unprocessed=0 history_own_gross_profit=89.00 history_own_costs=0.00 history
L2813: GE	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL_DIFFERENCES phase=OnTester history_confirmed_minus_callback_processed=0 tester_ALL_minus_history_confirmed_deals=1 tester_ALL_minus_history_confirmed_net=-4.00 attribution_of_tester_totals=NOT_ASSUMED
L2814: JJ	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL: TesterStatistics abrange TODO o teste; fechamento de fim de teste e apenas candidato quando indicado. Nenhuma negociacao na reconciliacao.
L2815: ML	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL_DEAL phase=OnTester ticket=2 result=CONFIRMED symbol=PETR4 magic=20261118001 position_id=2 order=2 entry=0 reason=3 time_msc=1794825000000 price=45.17000000 volume=100.00000000 profit=0.00 callback_seen=true callback_processed=true possible_end_of_test=false evidence=deal/order symbol, magic, ticket and position link verified
L2816: GN	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL_DEAL phase=OnTester ticket=3 result=CONFIRMED symbol=PETR4 magic=20261118001 position_id=2 order=3 entry=1 reason=5 time_msc=1794831066000 price=44.28000000 volume=100.00000000 profit=89.00 callback_seen=true callback_processed=true possible_end_of_test=false evidence=deal/order symbol, magic, ticket and position link verified
L2817: KN	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL_DEAL phase=OnTester ticket=4 result=CONFIRMED symbol=PETR4 magic=20261118001 position_id=4 order=4 entry=0 reason=3 time_msc=1794846600000 price=44.02000000 volume=100.00000000 profit=0.00 callback_seen=true callback_processed=true possible_end_of_test=false evidence=deal/order symbol, magic, ticket and position link verified
L2818: IS	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL_DEAL phase=OnTester ticket=5 result=INCONCLUSIVE symbol=PETR4 magic=0 position_id=4 order=5 entry=1 reason=0 time_msc=1794938099742 price=43.98000000 volume=100.00000000 profit=-4.00 callback_seen=false callback_processed=false possible_end_of_test=true evidence=deal symbol/magic does not establish EA ownership
L2819: LP	0	20:32:32.622	Core 01	final balance 10085.00 BRL
L2821: RN	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL phase=OnDeinit snapshot_unchanged=true scan_complete=true history_confirmed_own_deals=3 history_own_entries=2 history_own_exits=1 history_SL=0 history_TP=1 inconclusive_records=1 unreadable=0 other_market_deals=0 nonmarket_records=1 callback_observed_all=3 callback_processed_own=3 history_own_without_callback=0 history_own_without_processed_callback=0 processed_callback_without_history=0 queued_unprocessed=0 history_own_gross_profit=89.00 history_own_costs=0.00 history_
L2822: KS	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL_DIFFERENCES phase=OnDeinit history_confirmed_minus_callback_processed=0 tester_ALL_minus_history_confirmed_deals=1 tester_ALL_minus_history_confirmed_net=-4.00 attribution_of_tester_totals=NOT_ASSUMED
L2823: PO	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 FINAL: TesterStatistics abrange TODO o teste; fechamento de fim de teste e apenas candidato quando indicado. Nenhuma negociacao na reconciliacao.
L2825: HR	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 SUMMARY evaluated_signals=2 entry_requests=2 logged_own_deals=3 exit_deals=1 SL_exits=0 TP_exits=1 observed_equity_high=10162.00000000 observed_equity_low=9997.00000000 diag_records=157 ownership_records=99 uncertain=false
L2826: PR	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001 LOG_SUMMARY ownership_success_printed=99 ownership_failure_printed=0 success_suppressed=2361521 failure_suppressed=0 final_detail_printed=4
L2827: JG	0	20:32:32.622	Core 01	2026.11.17 17:54:59   MT5SF001: deinit reason=1 halted=false; nenhuma ordem enviada no deinit
L2828: NE	0	20:32:32.622	Core 01	PETR4,M5: 85594 ticks, 190 bars generated. Environment synchronized in 0:00:00.105. Test passed in 0:00:00.114.
```

## Excertos da compilação histórica

Fonte: `BASE_RICO/Logs/metaeditor.log`. Nenhuma compilação foi executada na coleta.

```text
L3133: 0	2026.11.18 20:29:25.837	Compile	BASE_RICO\MQL5\Experts\MT5StrategyFactory\Estrategia_001\MT5SF_Estrategia_001.mq5 - 0 errors, 0 warnings, 1096 ms elapsed, cpu='AVX2 + FMA3'
L3134: 0	2026.11.18 20:29:25.846	127.0.0.1	BASE_RICO\MQL5\Experts\MT5StrategyFactory\Estrategia_001\MT5SF_Estrategia_001.mq5 compile succeeded: 0 errors, 0 warnings found
```
