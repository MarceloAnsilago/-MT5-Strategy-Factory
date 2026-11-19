# PETR4 M15 — prova de conceito no MT5 da Rico

Terminal usado: C:\Program Files\Rico - MetaTrader 5\terminal64.exe
Servidor observado na interface e no relatório: Rico-DEMO (build 6230).
Teste iniciado e relatório exportado pela interface do Strategy Tester. Nenhuma ordem de conta foi solicitada. O EA recusa inicialização fora do Tester.

Estratégia: EMA 9 e EMA 21 de fechamento; compara candles fechados 2 e 1 uma vez por candle novo. Compra no cruzamento acima, vende no cruzamento abaixo. Fecha antes de inverter e mantém uma posição por símbolo/magic. Volume padrão 100 ações, magic 9021004, períodos e volume configuráveis. Sem stop loss, take profit ou fechamento diário obrigatório; pode carregar posição entre sessões. Não houve otimização.

Compilação: 0 erros, 0 avisos, 482 ms, X64 Regular. Usado o MetaEditor local da cópia portátil para gerar o EX5; o teste efetivamente rodou no terminal da Rico.
Código e compilado preservados nesta pasta: PETR4_EMA_M15_POC.mq5 e PETR4_EMA_M15_POC.ex5.
Cópias de execução instaladas em C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\38FF261A42172F3478E54D3A1A8FE02B\MQL5\Experts\StrategyFactoryPOC.
Foi necessário Atualizar no Navegador do terminal para reconhecer o novo EA e selecioná-lo no Tester.

Configuração: PETR4 / M15; 2025.01.01 a 2025.04.01; OHLC por 1 minuto; execução sem atrasos; depósito BRL 10000; alavancagem 1:1; otimização desativada; inputs 9/21/100/9021004.

Resultados confirmados no HTML:
- 89 operações e 178 negócios de entrada/saída.
- Lucro líquido indicado pelo Tester: BRL 288.00 (2.88% do depósito); saldo final BRL 10288.00.
- Fator de lucro 1.37; 28 operações com lucro e 61 com perda; acerto 31.46%.
- Drawdown máximo do capital líquido: BRL 196.00 (1.94%).
- Qualidade de histórico 96%, 1876 barras, 110464 ticks.
- 44 posições compradas e 45 vendidas.
- Última posição encerrada por fim do teste em 2025.03.31 16:54:59.

Relatório original do MT5: reports\PETR4_EMA_M15_2025Q1_Rico.html e imagens PNG associadas.
Configuração para carregar pela interface: tester-petr4.ini.
Limitações: resultado de um único intervalo histórico com modelagem OHLC M1. Não foi validada a inclusão de todos os custos de corretagem, emolumentos, aluguel de ações e execução real. Não foi feito teste em período separado nem avaliação de robustez. O resultado positivo deste teste não estabelece lucratividade futura.
