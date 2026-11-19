# Estratégia 001 v1.23 — revisão de relatórios finais

Estado em 19/11/2026: implementação e validação controlada concluídas. EA e script compilaram com zero erros e zero avisos; 11 testes Python aprovados; script MQL5 com `failures=0`; um backtest comparativo local concluído. Os destinos isolados na Rico preservaram a v1.22. Evidências publicáveis e limites em [VALIDACAO_001_V123.md](VALIDACAO_001_V123.md).

## Versionamento e preservação

Foi mantido o padrão existente: fonte atual com nome estável `MT5SF_Estrategia_001.mq5` e cópia da revisão anterior nomeada `MT5SF_Estrategia_001.v1.22_pre_v1.23_001.mq5.bak`, na mesma pasta. A cópia é idêntica por bytes ao fonte v1.22 do commit `3e777b31ad94a54e2d21163fc6a06989992be1e8`, SHA256 `d98154e180c1e707469003fffd85357aa7ac10cfa510a4990da13a3ea7eae9af`. As revisões anteriores e o dossiê publicado permanecem intactos.

O fonte atual declara 1.23. Fora do bloco de relatório final, as únicas mudanças são a identificação da revisão e a divisão das mensagens de resumo em `OnDeinit`. Inputs, `OnTick`, `OnTradeTransaction`, `OnTrade`, `OnTester`, lógica de inicialização, entradas, saídas, indicadores, SL/TP, volume e proteções não foram alterados. A parte de liberação dos indicadores, observação de equity e diagnóstico em `OnDeinit` também foi preservada.

## Organização do relatório

`FinalReportTotals.mqh` contém apenas agregação monetária e emissão de texto; não conhece magic nem decide propriedade. A classificação continua nas funções existentes, que foram preservadas integralmente: `FinalDealLinkOwned`, `FinalOriginOwned`, `FinalMarketDeal` e `ReadFinalSnapshots`.

| Seção | Escopo |
|---|---|
| `GLOBAL` / `GLOBAL_COUNTS` | Resultado líquido, depósito e contagens de todo o Tester, sem atribuição automática ao EA |
| `CONFIRMED` / `CONFIRMED_MONEY` | Negócios candidatos cuja propriedade passou nas regras da v1.22; bruto, custos e líquido |
| `INCONCLUSIVE` / `INCONCLUSIVE_MONEY` | Negócios candidatos não confirmados; valor monetário conhecido não significa propriedade confirmada |
| `*_CALLBACKS` | Por grupo: observado, somente histórico e processado como próprio |
| `CALLBACKS` | Fila observada em runtime e negócios processados como próprios; filtrados/pendentes identificados separadamente |
| `HISTORY_MARKET` | Negócios de mercado legíveis, de todos os símbolos: observados por callback versus somente histórico; registros ilegíveis explicitamente excluídos |
| `RECONCILIATION` | Soma dos candidatos e diferença em relação ao global; nunca promove classificação |
| `DEAL_<ticket>*` | Identificadores, execução, valores, observabilidade e evidência em mensagens separadas |
| `RUNTIME_*` | Contadores e estado de runtime, explicitamente distintos da atribuição final |

Os grupos CONFIRMED e INCONCLUSIVE não representam necessariamente todos os movimentos financeiros do Tester. Negócios de terceiros, outros símbolos e registros não comerciais continuam separados, e a diferença global não é atribuída automaticamente a um grupo.

Os valores incluem lucro, comissão, swap e fee quando todos os campos necessários foram lidos e são números finitos. Falha de leitura, snapshot incompleto ou valor inválido produz `UNAVAILABLE`, sem converter ausência em zero. Em snapshot parcialmente legível, as contagens representam apenas registros observados e são identificadas por `membership_complete=false`; os totais financeiros dos grupos ficam indisponíveis conservadoramente. Cada detalhe legível pode ainda mostrar seu valor individual, sem certificar a soma completa.

Uma classificação INCONCLUSIVE pode ter valor conhecido: no cenário histórico, seu líquido é −4,00. Se o valor não puder ser estabelecido, permanece `UNAVAILABLE`. Um grupo vazio em snapshot completo pode ter líquido conhecido zero; isso é distinto de um grupo de tamanho desconhecido.

Estatísticas globais exigem contexto final validado, passagem por `OnTester`, leituras sem erro, valores finitos, depósito positivo e contagens inteiras não negativas. Em `OnDeinit` sem passagem por `OnTester`, não se presume que estatísticas finais estejam prontas. O valor de retorno de `OnTester` continua zero; não foi criado critério de otimização.

Todas as novas mensagens finais passam pelo emissor que divide o payload em até 180 caracteres por parte, com fase, seção e `part=n/total`. Quebras de linha no payload viram espaços. Prefixos atuais mais payload ficam abaixo de 350 caracteres, oferecendo margem para os prefixos do journal. O limite de detalhes continua contando negócios detalhados, não linhas; cada negócio pode gerar várias mensagens. Os limites e proteções operacionais não dependem dessa emissão.

## Cenário de referência e limites de atribuição

Para dados completos equivalentes ao dossiê, o esperado é:

| Medida | Esperado |
|---|---:|
| GLOBAL líquido | +85,00 |
| CONFIRMED líquido | +89,00 |
| INCONCLUSIVE líquido | −4,00 |
| Candidatos líquidos | +85,00 |
| Global menos candidatos | 0,00 |
| CONFIRMED: callbacks / somente histórico | 3 / 0 |
| INCONCLUSIVE: callbacks / somente histórico | 0 / 1 |
| Mercado legível: callbacks / somente histórico | 3 / 1 |

O negócio 5 continua INCONCLUSIVE, com `magic=0` e `possible_end_of_test=true`; nem essa heurística nem a conciliação aritmética passam a autorizar atribuição ou operações de negociação. O vínculo com o Run ID histórico e a diferença de tamanhos do EX5 permanecem pendências do dossiê.

## Verificações e testes

Executado localmente, sem terminal, rede ou compilador:

```text
python -B -m unittest discover -s tests -p test_report_contract.py -v
```

Onze testes Python verificam a identidade da v1.22, preservação dos blocos operacionais e classificadores, fronteiras do diff, ausência de mutações no relatório, caminhos de indisponibilidade, divisão das mensagens e conciliação decimal dos quatro negócios do dossiê publicado. São testes de contrato, inspeção estática e evidência histórica: **não executam MQL5 e não comprovam compilação ou comportamento do terminal**.

O script isolado `MQL5/Experts/MT5StrategyFactory/Estrategia_001/tests/TestFinalReport.mq5` usa diretamente o mesmo header de agregação da v1.23. Ele contém verificações para +89/−4/+85, callbacks versus histórico, valores faltantes, snapshot incompleto, zero conhecido, comissão/swap/fee, NaN, overflow, nova passagem sem acumulação e divisão de textos longos. Não possui acesso a histórico, indicadores ou funções de negociação. Foi compilado sem erros ou avisos e executado isoladamente, com `REPORT_TEST_RESULT failures=0` confirmado no journal de Experts. O total previsto pelo fluxo do fonte é 35 asserções; o script não imprime contador total nem PASS individual.

## Validação concluída e limites

As etapas de compilação, script isolado e comparativo foram concluídas sob autorizações específicas, conforme [VALIDACAO_001_V123.md](VALIDACAO_001_V123.md). No único backtest v1.23, as mensagens finais foram recuperadas sem truncamento observado, os resultados +85/+89/−4 permaneceram separados e o fechamento com magic=0 continuou INCONCLUSIVE. Foram comparados 264 registros operacionais normalizados, todos coincidentes com a referência recuperada.

Riscos: o formato textual novo exige adaptação de consumidores dos logs e produz mais linhas; falhas de campos auxiliares tornam os valores conservadoramente indisponíveis. O cenário executado não prova equivalência em outros períodos, mercados ou condições de falha. A compilação requer `FinalReportTotals.mqh` ao lado do fonte. Não copiar apenas o `.mq5`.

Novas execuções, alterações ou otimizações dependem de autorização específica. A validação publicada não inclui journals brutos, EX5 ou configurações privadas.

Documentação técnica usada para as APIs de estatísticas e números inválidos: [TesterStatistics](https://www.mql5.com/en/docs/common/testerstatistics), [ENUM_STATISTICS](https://www.mql5.com/en/docs/constants/environment_state/statistics), [MathIsValidNumber](https://www.mql5.com/en/docs/math/mathisvalidnumber) e [MathSqrt](https://www.mql5.com/en/docs/math/mathsqrt).
