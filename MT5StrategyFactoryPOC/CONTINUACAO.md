# Continuação da prova de conceito — 18/11/2026

## Caminho que funcionou
Abertura do atalho MT5 Portatil POC.lnk pelo Explorador de Arquivos. O atalho aponta para terminal\terminal64.exe /portable, com diretório de trabalho terminal. A janela MetaQuotes-Demo mostrou Conta Demo - Hedge, conexão ativa e cotações atualizando. Não foi necessário informar login nem senha.
Reutilizado EMA_Cross_POC.ex5 já compilado; não houve recompilação nesta continuação.
Carregada pela interface a configuração tester-ui.ini (somente seção Tester, sem credenciais). Teste único iniciado pelo botão Iniciar. O Tester concluiu e o relatório foi exportado pela interface: Teste de Volta (backtest) > menu de contexto > Relatório > HTML.

## Resultado confirmado no relatório
- Expert: EMA_Cross_POC
- EURUSD, M15, 2025.01.01 a 2025.04.01
- Modelo: OHLC por 1 minuto (confirmado na configuração da interface)
- Inputs: FastPeriod=9, SlowPeriod=21, Volume=0.1, Magic=9021001
- Depósito USD 10000; alavancagem 1:100
- Total de negociações/operações: 271
- Ofertas/negócios de entrada e saída: 542
- Lucro líquido: USD -112.94; saldo final: USD 9887.06
- Qualidade do histórico declarada pelo Tester: 100%; 6022 barras, 358792 ticks
- Relatório: reports\EMA_EURUSD_M15_2025Q1.html, acompanhado dos PNGs na mesma pasta.
O último fechamento ocorreu em 2025.03.31 23:59:59, por término do teste; a data final configurada foi 2025.04.01.

## Porta MCP
A consulta inicial dentro do sandbox não permitiu Get-NetTCPConnection (Acesso negado), e netstat comum não exibiu a porta. Consulta ampliada somente de leitura identificou TCP 127.0.0.1:22346, PID 13664, terminal64.exe, caminho C:\Program Files\Rico - MetaTrader 5\terminal64.exe. Não foi alterado nem encerrado esse processo.

## MCP do Codex
Nenhuma ferramenta de MT5/MetaTrader/MetaEditor disponível no catálogo desta sessão.
Configuração global C:\Users\User\.codex\config.toml: encontrada seção mcp_servers.node_repl; não encontrada seção de MT5. Não há C:\estrategia\.codex\config.toml.
O CLI local codex.cmd mcp list respondeu: No MCP servers configured yet.
Isso é evidência local de configuração e disponibilidade, não uma listagem tools/list do servidor do MT5. Não foi possível chamar ferramenta MCP de backtest nesta sessão. O endpoint ocupado pelo terminal da Rico não foi usado para iniciar teste.

A instância portátil e o relatório ficaram abertos. O terminal da Rico foi preservado. Nenhuma ordem foi enviada a uma conta por esta execução; as transações relatadas são simulações do Strategy Tester. Nenhuma senha/token foi coletada ou registrada nesta continuação.
