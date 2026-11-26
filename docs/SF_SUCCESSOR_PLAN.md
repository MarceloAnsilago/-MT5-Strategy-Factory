# SF-PROLONGADO-1 — desenvolvimento offline de produto

**PROPOSTA NÃO ATIVADA.** Depende da aprovação de SF-OFFLINE-1 e da integração/testes do perfil sucessor. Não depende de homologação MCP. Este plano não implementa funcionalidades nem ativa o worker nesta fase.

## Prioridade e dependências

| Tarefa | Prioridade | Depende de | Entrega e aceitação principal |
|---|---:|---|---|
| SF-O01 — dados locais e proveniência | P1 | Nenhuma | Adaptador CSV/JSON indicado por manifesto; conserva bytes/hash/origem e usa history_audit/dataset_policy. Rejeita OHLC inválido, não finitos, conflitos e fuso ambíguo. Mantém classificação não certificada. |
| SF-O02 — catálogo de estratégias | P1 | Nenhuma | Composição e grade determinística de MA/RSI/ADX pelo gerador existente, até 32 candidatos; preserva limites de regras/handles/risco e escreve somente fonte source_only em diretório novo. |
| SF-O03 — comparação de experimentos | P1 | Nenhuma | Relatórios conservadores de fixtures 1.1: contexto compatível, desconhecidos preservados, ordenação explicada e determinística. Sem produzir retorno financeiro de fonte não executada. |
| SF-O04 — referência de indicador | P2 | Nenhuma | ATR/Wilder com vetores sintéticos e valores esperados independentes; fonte MQL5 de indicador sem trading/rede. Warmup e ausência de lookahead testados; validação nativa permanece pendente. |
| SF-O05 — pipeline de pesquisa | P2 | O01, O02, O03 | CLI local com fixture sintética, auditoria, candidatos e relatório; hash de inputs/outputs, diretório exclusivo e interrupções identificadas. Reprodutibilidade de conteúdo demonstrada. |
| SF-O06 — validação integrada e entrega | P3 | O05 | Exemplo executável offline, E2E independente, quickstart e estado verificável. Limites medidos e pendências nativas explícitas; nenhum resultado sintético vira backtest homologado. |

As tarefas O01–O04 são independentes. Arquivos de saída, APIs a reutilizar e critérios negativos de cada tarefa estão em `config/research/sf_successor_plan.proposed.json`. O05 não depende de O04. Falta de credencial, listener, terminal, dados reais ou compilador não impede O01–O06.

## Execução com os componentes existentes

Reusar history_audit, dataset_policy, generator, analysis, reports e traceability por suas interfaces públicas. O novo código de pesquisa fica em `strategy_factory/research/`; fontes MQL5 não instaladas em `src/mql5/`. Não refazer gerador, validador, supervisor ou sistema de consentimento. Nenhum novo painel, serviço, automação de startup ou sistema de créditos.

Na primeira execução só entram fixtures sintéticas aprovadas. Arquivo histórico real exige manifesto de entrada explícito, hash, origem e classificação adequada; nenhum download ou varredura automática do acervo. Saídas e registros de candidatos usam `artifacts/offline/<id exclusivo>/`, nunca ledgers/run IDs antigos. O gerador mantém template e guardas intactos; somente famílias já suportadas são compostas. ATR é fonte/referência de pesquisa, sem alegação de compilação ou equivalência validada no MT5.

Aceitação independente é materializada no plano de controle antes de entregar a tarefa ao modelo. O worker não edita essa aceitação. O resultado precisa demonstrar comportamento, casos negativos e rastreabilidade; contagem de testes ou declaração de sucesso isoladas não bastam. Piso de regressão: 513 produto, 81 compatibilidade, 18 aceitação existente e 130 AutoDev, preservando todos os casos anteriores, sem pulos. O número cresce quando os testes novos forem implementados; esta proposta não declara esses testes já executados.

## Continuidade e paradas

Escolher tarefas prontas por prioridade e ID; congelar plano/critério antes da execução. Materializar O01/O02/O03/O04 antes de O05/O06 em blocos topológicos. Não colocar tarefa de autorização MCP no começo do plano de produto, nem adicionar uma dependência dela. O plano da fase 5 continua histórico com homologação pendente; não falsificar conclusão para avançar.

Se uma entrega encontrar impedimento técnico sem impacto de segurança, documentar seu estado e preservar critérios. A revisão auditada do plano pode mover outras tarefas independentes prontas para o próximo bloco; dependentes permanecem bloqueadas. O executor atual não comprova seleção automática por DAG: a integração deve usar blocos compatíveis com o supervisor existente e validar o replanejamento antes de prometer continuidade. Não desenvolver um agendador secundário para esta proposta.

Falha de integridade, budget, consumo desconhecido, limite oficial, negação de aprovação ou pedido de parada são **globais**: nunca ignorar para manter o worker ocupado. No máximo uma correção por tarefa sob os limites propostos. Sem loop infinito para preencher oito horas; concluir quando não houver trabalho pronto autorizado e registrar motivo.

## Trilha operacional separada

SF-MCP-DIAG: uma leitura autorizada para recuperar os literais de raízes e as flags descartadas na fase 8, sem Community ou corpo bruto, com nova guarda e contrato exato. SF-MCP-RESTRICT: depois dessa evidência, investigar restrição suportada ou propor isolamento. Ambas são opcionais para a fila offline e permanecem desativadas.

Compilação, backtests/Tester, aquisição histórica, Python MetaTrader5, criação/autenticação de conta demo e integração com a instalação dedicada não são aprovadas por este plano. Precisam de contratos e escopos operacionais próprios, quando realmente necessários. Nenhuma operação em conta real está admitida.

## Critério de prontidão para o atalho

O integrador precisa: validar a fronteira positiva/negativa; manter os 130 testes do controlador; executar regressões do produto no espelho; auditar a migração de uso para execução filha; comprovar que MCP ausente não é gate; validar seleção dos caminhos novos e impedir arquivos protegidos; realizar preflight/dry-run sem modelo/rede; manter o novo perfil desativado até ATIVAR.

Depois disso, o proprietário usa **AutoDev - Iniciar**, seleciona limites e confirma **ATIVAR**. A primeira abertura apenas configura; a segunda inicia após três segundos. **P** configura durante essa contagem; **Esc** cancela; **Retomar** recupera a execução filha. Estes são critérios futuros da integração: o atalho atual ainda aponta ao perfil antigo e não deve ser apresentado como pronto.

## Orçamento e próximos resultados

Proposta: 480 minutos, 50 chamadas acumuladas, uma correção por tarefa, 500.000 tokens novos/10.000.000 cache/100.000 saída, timeout 420s. Incluir três chamadas, 391,875s e o consumo histórico registrado; zero reinicialização de contadores. Credenciais e saldo monetário não são inferidos desses números. Sem compra de créditos.

Ao terminar o bloco, consolidar módulos/fontes novos, testes, artefatos sintéticos rastreáveis, commits locais e pendências. Planejamento posterior pode avançar arquitetura e estratégias dentro da fronteira aprovada, com critérios verificáveis e orçamento. Não transformar autonomia permanente em autorização financeira, de rede ou de autoconfiguração de segurança.
