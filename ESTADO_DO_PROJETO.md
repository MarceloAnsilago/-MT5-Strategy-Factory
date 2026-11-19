# Estado do projeto — 19/11/2026

## Revisão v1.23 — relatórios finais validados

A revisão 1.23 foi implementada e validada por compilação, testes isolados e um backtest comparativo controlado. A v1.22 está preservada integralmente no arquivo `MT5SF_Estrategia_001.v1.22_pre_v1.23_001.mq5.bak`, SHA256 `d98154e180c1e707469003fffd85357aa7ac10cfa510a4990da13a3ea7eae9af`. O nome estável do fonte atual passa a declarar 1.23; a validação na Rico utilizou a pasta separada `Validation_v123_20261119`, preservando a instalação original v1.22.

O escopo limita-se à apuração e emissão dos relatórios finais: global, CONFIRMED e INCONCLUSIVE separados; callbacks e negócios somente históricos com escopos explícitos; mensagens divididas e valores indisponíveis identificados por `UNAVAILABLE`. Inputs, regras operacionais, funções de prova de propriedade e classificação conservadora do fechamento final foram preservados. EA e script MQL5 compilaram com zero erros e zero avisos; 11 testes Python passaram; o script isolado registrou `REPORT_TEST_RESULT failures=0` em 19/11/2026 às 18:11:55.001. O comparativo v1.23 reproduziu saldo 10085, GLOBAL +85, CONFIRMED +89, INCONCLUSIVE −4 e duas entradas; 264 registros operacionais normalizados coincidiram com a referência histórica. Detalhes em [REVISAO_001_V123.md](REVISAO_001_V123.md) e [VALIDACAO_001_V123.md](VALIDACAO_001_V123.md).

## Referência v1.22 e evidências históricas

O fonte v1.22 foi incorporado ao backup inicial a partir da subpasta `MQL5/Experts/MT5StrategyFactory` da instalação Rico, com identidade SHA256 conferida. Sua referência integral agora é `MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.v1.22_pre_v1.23_001.mq5.bak`; o commit inicial também preserva o conteúdo anterior no nome estável. Não foi garantida a inexistência de outra revisão em locais não inspecionados.

Revisões históricas encontradas e copiadas: v1.00 anterior às proteções, v1.10 anterior à v1.20, v1.20 anterior à v1.21 e v1.21 anterior à v1.22. Fonte `Homologacao_001` também preservado. EX5 permanecem em seus locais originais, excluídos do Git. Não foi comprovada a correspondência entre EX5 e fonte por recompilação.

Configurações locais do Tester com nomes v110, v120, v121 e v122 foram preservadas após inspeção. A configuração v122 especifica PETR4/M5, 16/11/2026 a 18/11/2026, modelo 0 (todos os ticks), depósito BRL 10000, alavancagem 1 e otimização desligada. Uma configuração salva não comprova que o teste terminou ou produziu determinado resultado. O `.set` representa os últimos inputs salvos; sua correspondência a uma execução específica não foi comprovada.

Não foi recuperado um relatório integral exportado da v1.22. Após o backup inicial, foram recuperadas evidências no journal da execução de 18/11/2026 às 20:32:32: PETR4/M5, todos os ticks gerados, duas entradas, saldo final R$ 10.085,00 para depósito de R$ 10.000,00. O resultado global de R$ +85,00 deve ser separado dos R$ +89,00 dos negócios atribuídos pelo reconciliador e do fechamento final de R$ −4,00, cuja atribuição permanece inconclusiva (`magic=0`, sem callback). Esses números não demonstram robustez ou custos completos. Fontes, parâmetros, hashes e excertos estão no [dossiê do backtest recuperado](DOSSIE_BACKTEST_001_V122_20261118.md).

O vínculo com o Run ID `7709658501521644233` ainda não foi comprovado: o MCP informa Tester parado com `run_id="0"` e não encontra o relatório JSON desse ID. O EX5 atual possui 105.308 bytes; o journal registra 105.378 bytes carregados. A diferença de 70 bytes está documentada sem presumir sua causa. A compilação histórica registra zero erros e avisos, mas falta o hash do binário efetivamente executado para comprovar a cadeia fonte → EX5 → teste. Nenhuma nova compilação ou execução foi realizada para recuperar essas evidências.

## Provas de conceito anteriores

Resultados conferidos nos relatórios HTML existentes, sem executar novos testes:

| EA | Ativo/período | Intervalo configurado | Operações | Lucro líquido | Evidência |
|---|---|---|---:|---:|---|
| EMA_Cross_POC v1.00 | EURUSD/M15 | 01/01/2025–01/04/2025 | 271 | USD -112,94 | `MT5StrategyFactoryPOC/reports/EMA_EURUSD_M15_2025Q1.html` |
| PETR4_EMA_M15_POC v1.00 | PETR4/M15 | 01/01/2025–01/04/2025 | 89 | BRL 288,00 | `MT5StrategyFactoryPOC/PETR4/reports/PETR4_EMA_M15_2025Q1_Rico.html` |

As continuações documentam modelagem OHLC M1 e ausência de otimização. O HTML PETR4 registra fator de lucro 1,37, drawdown máximo do capital líquido BRL 196,00 (1,94%) e qualidade de histórico 96%. O HTML EURUSD registra qualidade 100%. Esses indicadores declarados pelo Tester não comprovam completude dos custos ou validade fora da amostra. Não há validação de lucratividade futura.

`RESULTADO.md` mantém o registro de uma tentativa inicial malsucedida e aponta para a continuação bem-sucedida. `DIAGNOSTICO_MT5_RICO.md` e `INTEGRACAO_MCP_MT5.md` são registros históricos de etapas diferentes e foram preservados. Os dois MCPs responderam ao preflight de workspace e às consultas de leitura na continuidade. Isso não comprova retroativamente todos os critérios de homologação desses documentos.

## Backup e pendências

Backup inicial **concluído**, com commit `1692728437c8b796bff76646c2dcd60fc84a4a81`, mensagem `Backup inicial - MT5 Strategy Factory - Estrategia 001 v1.22`, enviado para `origin/main`; o hash remoto foi confirmado após o push. Repositório público por decisão do usuário: [visualizar o backup inicial](https://github.com/MarceloAnsilago/-MT5-Strategy-Factory/commit/1692728437c8b796bff76646c2dcd60fc84a4a81). Foram incluídos os 39 arquivos aprovados e o `.gitattributes`, totalizando 40 arquivos, com bytes conferidos e originais preservados. Não houve substituição de histórico nem uso de push forçado.

O `.gitignore` libera somente os caminhos revisados e exclui o ambiente de execução. Foi encontrado identificador de conta no `MT5StrategyFactoryPOC/tester.ini`, que permanece original e excluído. `.codex/`, `terminal/config/`, bases, executáveis, logs e caches ficam fora do Git. Verificação textual dos arquivos candidatos não identificou credenciais concretas; referências a tokens nos exemplos usam nomes de variáveis. A inspeção é limitada a padrões e revisão de conteúdo, não uma garantia universal de ausência de dados sensíveis.

O dossiê e a atualização documental foram publicados no segundo commit `3e777b31ad94a54e2d21163fc6a06989992be1e8`. A revisão v1.23 e seu resumo de validação integram a terceira entrega autorizada. Os documentos históricos, o dossiê e o manifesto do primeiro backup permanecem intactos; suas descrições anteriores devem ser lidas no contexto de cada etapa. As novas exceções no `.gitignore` incluem apenas a revisão e a validação documental v1.23 e sua verificação Python; logs, binários e auditorias locais continuam excluídos. A publicação desta implementação foi autorizada pelo usuário, condicionada à revisão dos arquivos e da ausência de dados sensíveis. Permanecem pendentes, para a referência histórica v1.22, a rastreabilidade do Run ID, a identidade do EX5 executado e o relatório integral; validações mais amplas de segurança e robustez também continuam pendentes. O comparativo da v1.23 não resolve essas lacunas históricas.
