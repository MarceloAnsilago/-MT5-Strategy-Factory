# Strategy Factory — iniciar desenvolvimento autônomo offline

26/11/2026 — America/Sao_Paulo. SF-OFFLINE-1 e SF-PROLONGADO-1 aprovados pelo proprietário, com integração pontual do executor e limites finitos. O plano de produto não depende de MCP.

## Iniciar pelo atalho

1. Dê dois cliques em **AutoDev - Iniciar** na área de trabalho.
2. Na primeira abertura, confirme os limites no console: **480 minutos**, **50 chamadas**, **1 correção por tarefa**, **500000 tokens novos**, **10000000 em cache**, **100000 de saída**. Pressione Enter em cada campo para manter a proposta.
3. Confira o resumo e digite **ATIVAR**. A janela salva a configuração e termina sem chamada de modelo. Não envie essa palavra ao chat como substituto da confirmação local.
4. Dê dois cliques em **AutoDev - Iniciar** novamente. Após três segundos, o worker começa/retoma **SF-O01**, seguido pelas demais tarefas offline. Nenhum listener MCP ou credencial MT5 é requisito.

Nas próximas aberturas, basta Iniciar. Durante os três segundos, **P** abre configuração e **Esc** cancela. Após reiniciar o computador, use **AutoDev - Retomar**. **AutoDev - Pausar** e **AutoDev - Encerrar** preservam o checkpoint; consulte **AutoDev - Status** para confirmar a parada.

O computador precisa permanecer ligado e a autenticação ChatGPT/CLI disponível. Não há serviço de inicialização do Windows, compra de créditos ou reinício automático de limites. Falha de integridade, limite oficial, consumo desconhecido ou orçamento esgotado interrompem o worker.

## O que será desenvolvido

Execução filha `desktop-sf-offline-1`, vinculada ao histórico `desktop-36586a9b3f0c4f8b` sem alterar sua homologação pendente. Tarefas: dados locais com proveniência; catálogo de candidatos MA/RSI/ADX pelo gerador existente; comparação conservadora; referência ATR e fonte de indicador; pipeline de pesquisa; validação E2E e documentação utilizável.

O plano fica em `C:/CodexAutoDev/plans/strategy_factory_offline_v1.json`. Código/arquitetura/fontes de estratégia/indicador, testes novos e documentação ficam na fronteira aprovada em C:\estrategia. Não se permite alterar mecanismos operacionais/de segurança, testes históricos, credenciais, instalações ou acervos homologados. Os commits locais são feitos pelo controlador após aceitação independente; o worker não acessa .git nem decide sua própria aprovação.

Testes históricos e aceitações executam em espelho descartável dentro do MXC. O worker usa perfil de permissões que estende workspace, sem rede, com fontes protegidas somente leitura e diretórios não produtivos/credenciais negados. Rede do serviço ChatGPT/CLI é distinta da rede de comandos do worker, que permanece bloqueada.

Somente fontes e simulações sintéticas: nenhuma compilação, instalação em MT5, backtest, aquisição de mercado, conta ou ordem está autorizada por esse plano. Ao concluir o bloco ou atingir limite, o programa para; oito horas são um teto, não duração garantida. Segurança/orçamento são paradas globais. Replanejamento técnico continua dentro do escopo aprovado.

## Orçamento preservado

Os limites são acumulados: incluem três chamadas, 391,875 segundos, 102938 tokens novos, 1398528 cache e 9935 saída do histórico. Com os valores propostos restam até **47 chamadas**, aproximadamente **473min28s**, 397062 tokens novos, 8601472 cache e 90065 saída. A conversa desta integração não é medida pelo ledger do worker; não foi declarada consumo zero.

Os journals autênticos das três chamadas antigas são importados uma única vez na execução filha para manter contabilidade e tratamento de consumo desconhecido; seus eventos não são contados novamente no relatório diário da filha. A sessão antiga do modelo não é retomada para executar o novo plano.

## MCP — diagnóstico separado concluído

A consulta autorizada desta integração fez quatro POSTs e uma única get_workspace_info, com guarda nova, sem retries/fallback. O servidor declara escrita e execução na MQL5 dedicada **e** em `C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\Common`; anuncia criação/alteração/exclusão habilitadas. A raiz Common compartilhada não é descendente da MQL5 esperada. O validador recusou a homologação e permanece intacto. Esses direitos anunciados não foram exercidos por escrita de teste e não provam a DACL efetiva do processo.

Nenhum payload bruto, Community ou credencial foi persistido. O impedimento operacional está registrado em `C:/CodexAutoDev/reports/phase10-mcp-diagnostic.json`; não bloqueia este plano offline. Nova operação MCP requer novo escopo/guarda específicos, sem reutilizar esta tentativa.

## Estado e evidências

Primeira execução fica preparada, com perfil real desativado até o passo ATIVAR. Nenhuma chamada de modelo foi feita para fingir início. Configuração: `C:/CodexAutoDev/config.strategy_factory_offline.json`; controlador: `factory_successor.py`. O perfil antigo e seu checkpoint são preservados. Evidências e validações: `C:/CodexAutoDev/reports/phase10-*` e relatório final da integração.
