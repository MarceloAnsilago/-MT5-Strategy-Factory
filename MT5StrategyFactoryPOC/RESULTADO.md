Continuação concluída pela interface. Consulte CONTINUACAO.md e reports\EMA_EURUSD_M15_2025Q1.html: 271 operações, EURUSD M15, 2025.01.01–2025.04.01, OHLC M1. O registro abaixo documenta a tentativa inicial, anterior ao teste bem-sucedido.

# MT5 Strategy Factory — prova de conceito

Pasta independente do GeraSet: C:\estrategia\MT5StrategyFactoryPOC.

## Verificação das capacidades
- Nenhuma ferramenta MCP de MT5/MetaTrader/MetaEditor foi encontrada entre as ferramentas expostas nesta sessão. Não foi possível validar chamadas MCP para símbolos, compilação, início de teste ou recuperação de relatório.
- Símbolos: verificados diretórios de histórico local, incluindo EURUSD, AUDUSD, GBPUSD e USDJPY. Isso não equivale a consultar a lista de símbolos pela API nem garante qualidade do histórico.
- Compilação: executada com MetaEditor64.exe local, em cópia portátil isolada. Resultado: 0 errors, 0 warnings, 518 ms, X64 Regular. EX5 gerado (29056 bytes).
- Backtest: solicitado por terminal64.exe /portable /config:C:\estrategia\MT5StrategyFactoryPOC\tester.ini. A primeira tentativa retornou “tester not started because the account is not specified”, saída -1000012353. Também ocorreu erro MCP de bind 127.0.0.1:22346, código 10048 (porta já em uso); isso não disponibiliza ferramentas MCP nesta sessão.
- Tentativas seguintes com a configuração demo local registraram startup, sem início do Tester nem geração de relatório durante a observação. Instância isolada encerrada. O terminal Rico já aberto não foi encerrado.

## EA
Arquivo: terminal\MQL5\Experts\EMA_Cross_POC.mq5
Compilado: terminal\MQL5\Experts\EMA_Cross_POC.ex5
Inputs: FastPeriod=9, SlowPeriod=21, Volume=0.10, Magic=9021001.
Usa EMA de fechamento, compara shifts 2 e 1 uma vez por candle novo. Fecha a posição anterior e confirma o fechamento antes de inverter. Filtra símbolo e magic; não interfere em posição de outro EA/manual no símbolo. Recusa execução fora do Strategy Tester pelo MQL_TESTER. Volume validado contra limites e step do símbolo. Sem stop loss/take profit nesta regra de prova de conceito.

## Teste solicitado (não concluído)
EURUSD, M15, de 2025.01.01 até 2025.04.01, modelo 1 (OHLC M1), depósito USD 10000, alavancagem 1:100, sem otimização, agentes locais apenas.
Número de operações: indisponível; não representa zero operações.
Relatório HTML solicitado: reports\EMA_EURUSD_M15_2025Q1.htm — NÃO GERADO.
Evidências: compile.log, reports\terminal-attempts.log, reports\tester-attempts.log.
Pendente: inicialização funcional da conta demo/terminal isolado para o Tester, execução do backtest e leitura do relatório; validação comportamental do EA ainda depende desse teste.

Recursos locais usados: C:\Program Files\MetaTrader 5\metaeditor64.exe, terminal64.exe e metatester64.exe, copiados para terminal; includes, configurações e histórico de EURUSD da instalação MetaQuotes-Demo existente. As configurações locais podem conter dados de conta: não compartilhar a pasta terminal\config.
Nenhuma ordem foi enviada a uma conta pelo EA; somente se tentou iniciar o Strategy Tester.

