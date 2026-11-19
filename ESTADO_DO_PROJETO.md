# Estado do projeto — 19/11/2026

## Estratégia 001

Fonte disponível e incorporado ao workspace: `MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.mq5`. Cabeçalho e `#property version` declaram **1.22**, correspondente à revisão solicitada. A origem é a subpasta `MQL5/Experts/MT5StrategyFactory` da pasta de dados da instalação Rico identificada no diagnóstico local. A cópia é idêntica por SHA256 ao arquivo encontrado. Não foi estabelecido um histórico Git anterior nem garantida a inexistência de outra revisão em locais não inspecionados.

Revisões históricas encontradas e copiadas: v1.00 anterior às proteções, v1.10 anterior à v1.20, v1.20 anterior à v1.21 e v1.21 anterior à v1.22. Fonte `Homologacao_001` também preservado. EX5 permanecem em seus locais originais, excluídos do Git. Não foi comprovada a correspondência entre EX5 e fonte por recompilação.

Configurações locais do Tester com nomes v110, v120, v121 e v122 foram preservadas após inspeção. A configuração v122 especifica PETR4/M5, 16/11/2026 a 18/11/2026, modelo 0 (todos os ticks), depósito BRL 10000, alavancagem 1 e otimização desligada. Uma configuração salva não comprova que o teste terminou ou produziu determinado resultado. O `.set` representa os últimos inputs salvos; sua correspondência a uma execução específica não foi comprovada.

Não foram localizados relatórios HTML/CSV ou documentação específica de resultados da v1.22 no workspace, na pasta do projeto MQL5 da Rico ou na busca de relatórios em seu Tester. Não há, neste snapshot, resultado financeiro, número de operações ou aprovação de robustez comprovados para essa versão. Logs e caches brutos não foram incorporados como substitutos de relatórios. A localização e revisão de evidências adicionais continuam pendentes.

## Provas de conceito anteriores

Resultados conferidos nos relatórios HTML existentes, sem executar novos testes:

| EA | Ativo/período | Intervalo configurado | Operações | Lucro líquido | Evidência |
|---|---|---|---:|---:|---|
| EMA_Cross_POC v1.00 | EURUSD/M15 | 01/01/2025–01/04/2025 | 271 | USD -112,94 | `MT5StrategyFactoryPOC/reports/EMA_EURUSD_M15_2025Q1.html` |
| PETR4_EMA_M15_POC v1.00 | PETR4/M15 | 01/01/2025–01/04/2025 | 89 | BRL 288,00 | `MT5StrategyFactoryPOC/PETR4/reports/PETR4_EMA_M15_2025Q1_Rico.html` |

As continuações documentam modelagem OHLC M1 e ausência de otimização. O HTML PETR4 registra fator de lucro 1,37, drawdown máximo do capital líquido BRL 196,00 (1,94%) e qualidade de histórico 96%. O HTML EURUSD registra qualidade 100%. Esses indicadores declarados pelo Tester não comprovam completude dos custos ou validade fora da amostra. Não há validação de lucratividade futura.

`RESULTADO.md` mantém o registro de uma tentativa inicial malsucedida e aponta para a continuação bem-sucedida. `DIAGNOSTICO_MT5_RICO.md` e `INTEGRACAO_MCP_MT5.md` são registros históricos de etapas diferentes. A disponibilidade atual de ferramentas MCP não comprova retroativamente a execução dos critérios de homologação desses documentos. Não foi feita nova validação MCP nesta preparação.

## Backup e pendências

Git local inicializado em `main`, sem commits. `origin` aponta para `https://github.com/MarceloAnsilago/-MT5-Strategy-Factory.git`. Consulta de leitura ao GitHub em 19/11/2026 retornou visibilidade **public**, tamanho 0 e lista de branches vazia. Não houve alteração do remoto, commit, stage, push ou substituição de histórico.

O `.gitignore` libera somente os caminhos revisados e exclui o ambiente de execução. Foi encontrado identificador de conta no `MT5StrategyFactoryPOC/tester.ini`, que permanece original e excluído. `.codex/`, `terminal/config/`, bases, executáveis, logs e caches ficam fora do Git. Verificação textual dos arquivos candidatos não identificou credenciais concretas; referências a tokens nos exemplos usam nomes de variáveis. A inspeção é limitada a padrões e revisão de conteúdo, não uma garantia universal de ausência de dados sensíveis.

O usuário confirmou que o repositório permanecerá **público**. Antes do primeiro commit/push: concluir a revisão final dos manifestos e obter autorização explícita para commit e envio. A localização de eventuais evidências adicionais da v1.22 permanece uma pendência documental, sem atribuir resultados não comprovados a este snapshot. Nenhuma alteração da estratégia, compilação, backtest ou otimização foi realizada nesta etapa. Todos os arquivos preexistentes foram mantidos.
