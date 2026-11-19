# Estado do projeto — 19/11/2026

## Estratégia 001

Fonte disponível e incorporado ao workspace: `MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.mq5`. Cabeçalho e `#property version` declaram **1.22**, correspondente à revisão solicitada. A origem é a subpasta `MQL5/Experts/MT5StrategyFactory` da pasta de dados da instalação Rico identificada no diagnóstico local. A cópia é idêntica por SHA256 ao arquivo encontrado. Não foi estabelecido um histórico Git anterior nem garantida a inexistência de outra revisão em locais não inspecionados.

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

Nesta continuidade foi autorizado somente preparar o dossiê e atualizar o estado: não houve novo commit ou push, alteração de código MQL5, compilação, backtest ou otimização. Os documentos históricos e o manifesto do primeiro backup permanecem intactos; suas descrições de estado anteriores devem ser lidas no contexto daquela etapa. O `.gitignore` recebeu apenas a inclusão explícita do novo dossiê, sem liberar logs, binários ou auditorias locais. Antes de qualquer publicação desta atualização, revisar o conteúdo e obter autorização. Permanecem pendentes a rastreabilidade do Run ID, a identidade do EX5 executado, o relatório integral e as validações de segurança e robustez.
