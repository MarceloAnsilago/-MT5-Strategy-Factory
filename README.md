# MT5 Strategy Factory

Projeto experimental de estratégias MQL5 para o Strategy Tester do MetaTrader 5. Este snapshot prepara o primeiro backup versionado; commit e envio ao GitHub ainda dependem de autorização.

O fonte principal é [MT5SF_Estrategia_001.mq5](MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.mq5), que declara a versão **1.22**. Foi copiado byte a byte da instalação Rico, com SHA256 conferido, sem modificar o código. Quatro revisões anteriores também foram preservadas como `.mq5.bak`.

Pela leitura do fonte, a Estratégia 001 usa cruzamento de EMAs em candles fechados, PETR4/M5 como padrão, volume de 100 ações, SL nominal de 1% e TP nominal de 2%. Possui controles de propriedade da exposição e limites de recuperação, e exige execução no Tester. Esses recursos encontrados no código não equivalem a homologação comportamental ou garantia de perda máxima.

O repositório também preserva o fonte de homologação sem negociação, configurações do Tester revisadas e provas de conceito anteriores EURUSD/M15 e PETR4/M15, com documentação e relatórios HTML/PNG. Os resultados dessas provas de conceito não são resultados da Estratégia 001 v1.22.

Consulte [ESTADO_DO_PROJETO.md](ESTADO_DO_PROJETO.md) para resultados, limitações e pendências, e [REVISAO_DO_BACKUP.md](REVISAO_DO_BACKUP.md) para o escopo exato proposto.

O ambiente completo do MT5, executáveis, credenciais, configuração ativa do Codex, bases da corretora, caches e logs não integram o backup. O arquivo `config/mt5-codex.config.example.toml` é somente exemplo inativo, com nomes de variáveis, sem tokens. A biblioteca padrão `Trade/Trade.mqh` deve ser fornecida pela instalação do MT5; não foi duplicada neste snapshot.

Nenhuma compilação, backtest ou otimização foi executada para preparar este backup. Não há instrução de execução em conta real.
