# Fase 2.3 — preparação e homologação autorizada

Em 20/11/2026, o EA exclusivo `MT5SF_Homologacao_002.mq5` foi criado em
`MQL5/Experts/MT5StrategyFactory/Homologacao_002/`. A cópia no MetaEditor Rico
foi relida e corresponde ao texto do repositório. Compilação final via MCP:
**0 erros, 0 avisos**, compilador build 6230, AVX2 + FMA3, 479 ms.
O EX5 fica somente na instalação MT5, fora do Git. A preparação foi concluída
sem iniciar backtest; uma execução única foi posteriormente autorizada e concluída,
conforme atualização ao final. Estratégia 001, GeraSet, Uni.mql5, DPAPI e
inicializador preservados.

## EA e limites operacionais

O `OnInit` recusa execução fora de `MQL_TESTER` e também recusa otimização,
antes de criar indicadores. O guard é repetido no `OnTick` e antes das requisições.
O EA não deve ser anexado a um gráfico operacional, mesmo com essa proteção.

- Somente compras: cruzamento da EMA 9 acima da EMA 21 nos dois candles fechados
  mais recentes. Avaliação uma vez por novo candle, sem usar candle aberto no sinal.
- Saída: cruzamento inverso, SL de 1% ou TP de 2%, ajustados ao tick mínimo.
  Não fecha e reabre no mesmo candle. Não há venda a descoberto.
- Volume sempre `SYMBOL_VOLUME_MIN`, sem progressão. PETR4 informou mínimo e passo
  de **100 ações**, tick de R$ 0,01 e moeda BRL.
- No máximo uma posição; bloqueia novas entradas se houver posição ou ordem.
  Antes de fechar, verifica símbolo, magic e direção da posição.
- Sem martingale, grid, ordens pendentes intencionais ou serviço externo.
  Rejeição, preenchimento parcial ou estado inesperado interrompe novas requisições;
  não há tentativas de recuperação. SL/TP existentes permanecem sujeitos ao Tester.
- No fim do período, uma posição remanescente pode ser encerrada pelo próprio
  Tester. Não há chamada de negociação em `OnDeinit`.

Inputs propostos: `InpFastPeriod=9`, `InpSlowPeriod=21`,
`InpStopLossPercent=1.0`, `InpTakeProfitPercent=2.0`,
`InpMagic=20261123002`, `InpDeviationPoints=5`.
Estão fixados no arquivo `.set`; não são parâmetros de otimização.

## Cenário preparado e posteriormente autorizado

| Parâmetro | Valor preparado |
|---|---|
| EA | `MT5StrategyFactory\Homologacao_002\MT5SF_Homologacao_002.ex5` |
| Ativo / timeframe | PETR4 / M5 |
| Intervalo | 03/11/2026 00:00 até 14/11/2026 00:00 exclusivo |
| Pregões com barras | 3, 4, 5, 6, 9, 10, 11, 12 e 13/11 |
| Barras M5 retornadas na inspeção | 849 |
| Depósito / moeda / alavancagem | 10000 / BRL / 1:1 |
| Modelo | Todos os ticks gerados, `Model=0` |
| Atraso de execução | 0 ms |
| Timeout do executor | 180 s |
| Otimização / forward / visual | Desligados |
| Agentes | `UseLocal=1`, `UseRemote=0`, `UseCloud=0` |
| Repetições | Uma tentativa autorizada, sem repetição automática |

A consulta M5 não retornou barras de 02/11, por isso o início foi ajustado para
03/11. A consulta de ticks de 03/11 retornou vazia e informou disponibilidade a
partir de 16/11. Não se assume cobertura de ticks reais para o intervalo desejado;
o modelo gerado foi escolhido explicitamente. Barras disponíveis não garantem
qualidade futura de geração nem operações vencedoras/perdedoras. Na preparação,
nenhum resultado financeiro foi presumido.

Os arquivos `config/tester/MT5SF_Homologacao_002_phase23.ini` e `.set` foram
copiados por MCP, sem sobrescrita, para `MQL5\Profiles\Tester` e o INI foi relido.
Só há seção `[Tester]`, sem configurações de conta ou negociação operacional.
Qualquer nova execução requer uma nova autorização; a tentativa autorizada foi consumida.

Após autorização, usar `TesterRunner.run(..., simulate=False, authorized=True,
timeout=180, prepared_config_path=<INI inspecionado>, inputs_path=<SET>)` por
meio do callable MCP da extensão. A opção de configuração preparada evita que
`tester_prepare_config` substitua os controles de agentes locais, que não são
expostos no seu schema. Caminhos devem estar sob `MQL5\Profiles\Tester`, nas
raízes permitidas pelo workspace. Cabe ao chamador conferir que o INI coincide
com o cenário autorizado; o executor não interpreta o conteúdo remoto.
Os caminhos locais concretos ficam apenas em `runs/phase23_preparation/`.

## Validação financeira

`strategy_factory/reports.py` extrai campos explicitamente reconhecidos de HTML
PT/EN ou JSON. Agora inclui saldos inicial/final, lucro/perda brutos, negócios,
ordens, posições, operações vencedoras/perdedoras e qualidade do histórico.
Cada métrica tem disponibilidade e valores de origem. Campos ausentes não são
preenchidos com fórmulas ou com dados de outra fonte.

Operações (`trades`), negócios executados (`deals`), ordens (`orders`) e posições
(`positions`) têm contagens próprias. Não se usa `deals/2` como quantidade de
operações, nem se conta depósito como negócio de mercado. O escopo de cada
contagem precisa ser o mesmo ao comparar fontes. O JSON mínimo Rico observado
na fase 2.2 não publica todas essas contagens/estatísticas; faltas continuam `null`.

`strategy_factory/financial.py` compara o relatório com outra exportação nativa
e/ou journal explicitamente vinculados ao mesmo `run_id`. O chamador deve recortar
o journal ao único teste antes da análise; não basta associar o nome de um arquivo.
Journal truncado, relatório incompleto, origem ambígua ou campos ausentes não
produzem validação completa. Divergências preservam ambos os valores, sem corrigir
o relatório silenciosamente. Tolerâncias padrão: R$ 0,01, 0,01 para razões e pontos
percentuais, e zero para contagens. Os cálculos são verificações separadas.

O EA registra no `OnTester` linhas `MT5SF002 STAT name=... value=...`, lendo
`TesterStatistics` com verificação de erro. Registra `UNAVAILABLE` em falha ou
sentinela. Taxa de acerto deriva dos vencedores/trades; drawdown absoluto deriva
do depósito e do saldo/patrimônio mínimo nativos. O relativo usa o máximo relativo,
sem confundi-lo com o percentual associado ao maior drawdown em dinheiro.
Qualidade do histórico vem do relatório/journal nativo, não desses marcadores.

Profit Factor sem perdas é `null`, com estado `infinite` quando há lucro bruto
positivo, ou `undefined` sem lucro/perda; DBL_MAX não vira um número financeiro
utilizável. Acerto e expectativa sem operações ficam `not_applicable`. Resultado
por período exige agregação explícita, sem atribuição presumida de negócios.

Uso offline (arquivos reais devem permanecer em `runs/`):

```powershell
python -m unittest discover -s tests -v
python -m strategy_factory.financial runs/execucao/report.json --run-id ID --journal runs/execucao/journal.json --journal-run-id ID --output runs/execucao/reconciliation.json
```

A CLI aceita envelope MCP JSON ou payload já extraído. Cria saída com exclusão
de sobrescrita e não chama o MT5. O executor também grava automaticamente
`financial_validation.json` para identidades internas; comparação com journal
e exportação nativa deve ser feita após a captura das evidências vinculadas.

Fixture `tests/fixtures/financial_synthetic.json` explicitamente sintética:
ganhos, perdas e empate, contagens distintas, saldos e métricas conhecidas.
Testes cobrem extração, divergências, sentinelas, dados incompletos, vínculo entre
execuções, configuração de agentes e guardas do EA. **66 testes Python aprovados**,
incluindo os contratos existentes. Compilar não equivale a validar comportamento;
a precisão financeira com operações do Tester exigia a execução autorizada descrita abaixo.

## Atualização após a única execução autorizada

O fluxo foi concluído pelo MCP, com o EA e cenário preparados, sem alterar a
Estratégia 001 ou o código MQL5. O journal confirmou agente local, nuvem desligada,
inputs, inicialização restrita ao Tester e conclusão normal. Não houve repetição.
Status, relatório bruto, journal completo, tempos e reconciliação permanecem em
`runs/phase23_execution/` e no diretório exclusivo da execução, fora do Git.
Valores da conta de teste e relatórios não são publicados neste documento.

O JSON Rico com operações expõe `gross_loss` como magnitude positiva. O adaptador
agora normaliza esse campo para perda negativa **somente** no schema nativo Rico
identificado, preservando valor de origem e operação em `native_mapping`.
JSON normalizado genérico continua rejeitando perda positiva como ambígua.
`profit_trades`/`loss_trades` são mapeados separadamente; contagens de ordens e
posições ausentes não são deduzidas da quantidade de negócios.

Drawdown relativo usa `rel_drawdown_percent_balance` e
`rel_drawdown_percent_equity`, não o percentual associado ao drawdown máximo
em dinheiro. Drawdown absoluto pode ser calculado a partir do depósito e mínimo
nativos; taxa de acerto pode ser calculada a partir de operações vencedoras e
total de operações. Esses cálculos ficam em `derived_metrics`, com fórmula e
operandos; não preenchem campos ausentes em `metrics`. A reconciliação os compara
com os marcadores `TesterStatistics` do journal como verificações próprias.

Foram confirmadas diferenças de arredondamento entre JSON e journal dentro das
tolerâncias definidas, sem divergência financeira nos campos comparáveis após
a normalização. A avaliação global continua parcial/inconclusiva porque faltam
campos no relatório JSON: não se promove evidência parcial a validação completa.
`margin_level` pode conter DBL_MAX e não é usado como medida financeira útil.
Não há conclusão de rentabilidade ou generalização para ticks reais.

Correções verificadas exclusivamente com reanálise dos arquivos salvos e
fixtures sintéticas adicionais: **69 testes Python aprovados**. O teste original
e seus arquivos de análise foram preservados; a reconciliação corrigida é uma
nova saída local. Nenhuma correção exigiu recompilação ou outro backtest.

Referências: [estatísticas nativas MQL5](https://www.mql5.com/en/docs/constants/environment_state/statistics),
[relatório do Tester](https://www.metatrader5.com/en/terminal/help/algotrading/testing_report),
[CTrade](https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade).
