# Validação controlada — Estratégia 001 v1.23

Validação concluída em 19/11/2026 no MetaEditor/MetaTrader 5 da Rico, em destinos separados `Validation_v123_20261119`. O escopo da revisão é exclusivamente o relatório final e a observabilidade; as regras operacionais e de atribuição permanecem as da v1.22.

## Compilação e testes isolados

| Verificação | Resultado observado |
|---|---|
| EA v1.23 | 0 erros, 0 avisos; compilador build 6230, AVX2+FMA3 |
| TestFinalReport.mq5 | 0 erros, 0 avisos |
| Contratos Python | 11 testes aprovados |
| Execução do script MQL5 | `REPORT_TEST_RESULT failures=0`, 19/11/2026, 18:11:55.001 |

O script foi executado isoladamente; o journal de Experts identifica `TestFinalReport (PETR4,M5)`. Não há PASS individual nem total de asserções impresso: **35** é o total previsto pelo fluxo do fonte, incluindo as 12 verificações de tamanho de chunks. O marcador final com zero falhas sustenta a conclusão normal desse percurso, com o vínculo à revisão baseado também nos caminhos e hashes verificados.

Os casos abrangem +89/−4/+85, callbacks e histórico, zero conhecido versus indisponível, dados incompletos, custos (comissão, swap e fee), números inválidos, overflow, repetição sem acumulação e divisão/reconstrução de mensagens. Os testes Python são contratos estáticos e verificações de evidência; não executam MQL5.

Para reproduzir os contratos, a partir da raiz:

```text
python -B -m unittest discover -s tests -p test_report_contract.py -v
```

O EA requer `FinalReportTotals.mqh` ao lado do fonte. Para o script isolado, preservar a estrutura `tests/TestFinalReport.mq5` e seu include relativo `../FinalReportTotals.mqh`. Compilar e executar o script separadamente, em ambiente de laboratório autorizado; ele usa somente dados sintéticos e não inicia o EA ou o Tester. EX5 não integra o repositório.

## Único backtest comparativo

Run ID devolvido pelo MCP: `7709994546072310394`; execução concluída em 19/11/2026 aproximadamente 18:16:32–18:16:33 (hora local do journal), sem timeout. EA selecionado: `MT5StrategyFactory/Validation_v123_20261119/MT5SF_Estrategia_001.ex5`, banner v1.23 confirmado. Conta DEMO, Strategy Tester local; agente local e nuvem desligada confirmados no journal. Otimização, forward e visualização desligados. Nenhum envio de ordem real foi solicitado.

Configuração: PETR4/M5, 16/11/2026 a 18/11/2026, todos os ticks gerados (Model=0), depósito BRL 10000, alavancagem 1:1. Os 18 inputs foram comparados com a referência histórica e mantidos:

| Input | Valor |
|---|---|
| InpSymbol / InpTimeframe | PETR4 / 5 (M5) |
| InpFastPeriod / InpSlowPeriod / InpAppliedPrice | 9 / 21 / 1 |
| InpShares | 100 |
| InpStopLossPercent / InpTakeProfitPercent | 1 / 2 |
| InpMagic / InpDeviationPoints | 20261118001 / 5 |
| InpDiagnosticEnabled / InpDiagnosticMaxRecords | true / 400 |
| InpOwnershipMaxRecords / InpOwnershipFailureMaxRecords | 600 / 200 |
| InpFinalMaxDetails / InpReconcileMaxAttempts | 100 / 12 |
| InpDiagnosticWindowTicks / InpEquityExtremeStep | 8 / 1 |

Os nomes exatos e valores serializados estão na referência pública `config/tester/MT5SF_Estrategia_001.set`; o quadro deve ser lido em conjunto com esse arquivo e o fonte. Para repetir em outra instalação, selecionar explicitamente o EX5 v1.23 compilado em destino separado, com agentes remotos e nuvem desabilitados. Não reutilizar um caminho que aponte para o EX5 original v1.22. A configuração privada da instalação e seus dados de conta não são publicados.

| Métrica | v1.22 recuperada | v1.23 |
|---|---:|---:|
| Saldo final | R$ 10.085,00 | R$ 10.085,00 |
| GLOBAL | +R$ 85,00 | +R$ 85,00 |
| CONFIRMED | +R$ 89,00 | +R$ 89,00 |
| INCONCLUSIVE | −R$ 4,00 | −R$ 4,00 |
| Entradas | 2 | 2 |

O Tester registrou 85594 ticks, 190 barras, quatro negócios de mercado e dois trades. A comparação normalizada do journal, do banner até antes do primeiro relatório final, encontrou **264 registros operacionais coincidentes**, desconsiderando prefixos do journal e a revisão no banner. Não houve regressão operacional observada nesse cenário.

Foram recuperadas 56 linhas finais, sem truncamento observado. GLOBAL, CONFIRMED e INCONCLUSIVE aparecem separados. Os três negócios confirmados foram observados por callback; o inconclusivo foi encontrado apenas no histórico. O negócio 5, posição 4, magic=0, permaneceu INCONCLUSIVE, com `possible_end_of_test=true`; essa indicação não constitui prova de propriedade. +89−4=+85 concilia o financeiro sem atribuir integralmente o global ao EA. OnTester e OnDeinit mantiveram os mesmos totais, sem dupla contagem observada.

## Identidade e rastreabilidade

SHA256 dos arquivos verificados na validação:

| Arquivo | SHA256 |
|---|---|
| Fonte v1.23 | 748a54c54b10b5ec04ca553c2e37af9de8a0506cb51a9e7b51577e0e0fa8c19f |
| FinalReportTotals.mqh | 87196893c946691d7749d90966187bd5d2f068a2a272b8aba49f79f3ebf0557f |
| TestFinalReport.mq5 | b445a1289e25d24548ba59dfc2c33e578717ec3aa430c7a646b3a4503daff247 |
| EX5 v1.23 (120126 bytes, somente local) | c179695e082a7cd1f7d7066a42a011afb7a07edb64540a9716df31e0ec7be112 |
| EX5 do script (somente local) | 4eb68de2cf8cbcd4aa8f1a6550fca5a8307caca1a4cb834348d09a94d9b7e91e |
| Backup do fonte v1.22 | d98154e180c1e707469003fffd85357aa7ac10cfa510a4990da13a3ea7eae9af |

As fontes e journals foram preservados na auditoria local, excluída do Git. Hashes permitem identificar as evidências sem publicar os arquivos brutos:

| Evidência local | SHA256 |
|---|---|
| Journal de Experts do script (154 bytes) | 481e65064246b2c31aceee8ea0f06148786caadfde5be233a1c31aa4b7b4bffe |
| Journal do Tester de 19/11/2026 | c8047281f1ecc892b4daef877adcc1bbadb5200d324e6ab66cbc3a204cadf401 |
| Relatório JSON do Run ID comparativo | 9c47946ee7b131c3d8945d8ff15020441a76a268ac8321815869105bc5af9394 |
| Journal histórico de 18/11/2026 | 95fc37512ff42bdbae87be78db538edec6029dba028ac3d4c72ce29ee6233011 |

## Limites

O resultado comprova o cenário examinado; não demonstra robustez, rentabilidade futura ou equivalência para outros períodos e falhas. Não houve teste de estresse de todos os textos possíveis no Tester. O JSON nativo contém valor extremo de margin_level, que não foi interpretado como nível de margem útil nem usado na conclusão.

O vínculo da execução histórica v1.22 com o Run ID `7709658501521644233` continua não comprovado. A diferença entre o tamanho do EX5 histórico no journal e o binário original recuperado também permanece sem causa estabelecida; consultar [DOSSIE_BACKTEST_001_V122_20261118.md](DOSSIE_BACKTEST_001_V122_20261118.md). O comparativo não elimina essas lacunas. Novos testes ou alterações requerem autorização própria.
