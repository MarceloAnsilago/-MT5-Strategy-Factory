# Referência ATR de Wilder

`strategy_factory.research.indicator_reference.atr(high, low, close, period)`
recebe três sequências de mesmo comprimento em ordem cronológica. O primeiro
True Range (TR) é `high - low`. Para cada barra seguinte, o TR é o maior entre
`high - low`, `abs(high - close_anterior)` e `abs(low - close_anterior)`.
Cada posição usa apenas a barra atual e o histórico disponível até ela.

A lista retorna `None` durante o aquecimento. O primeiro ATR, no índice
`period - 1`, é a média dos primeiros TRs. Daí em diante, Wilder atualiza o
valor como `ATR_anterior + (TR - ATR_anterior) / period`. Um período maior que
a série produz apenas `None`. Períodos que não sejam inteiros positivos,
comprimentos diferentes e preços ausentes ou inválidos geram `ValueError`.

Para `high=[11, 13, 14]`, `low=[9, 10, 11]`, `close=[10, 12, 13]`
e período 2, os TRs são 2, 3 e 3. O primeiro ATR é `(2 + 3) / 2 = 2.5`
e o seguinte é `(2.5 + 3) / 2 = 2.75`. O resultado é
`[None, 2.5, 2.75]`.

`src/mql5/Indicators/SF_ATR_Research.mq5` tem status `source_only`.
A validação nativa permanece `native_validation_pending`. A verificação
desta etapa consiste em testes Python com vetores sintéticos e inspeção
estática da fonte MQL5. Compilação, instalação, backtest e equivalência
nativa seguem pendentes.
