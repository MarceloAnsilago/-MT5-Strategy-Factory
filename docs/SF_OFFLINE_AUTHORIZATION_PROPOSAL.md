# SF-OFFLINE-1 — proposta de autorização permanente e revogável

**PROPOSTA NÃO ATIVADA.** Projeto exclusivo `C:\estrategia`, base revisada `b72d496`. A aprovação permite integrar a fronteira abaixo; não concede ao agente poder de mudar a própria política, o validador ou o orçamento durante uma execução.

## Permissão permanente de produto

Até revogação pelo proprietário, permitir criar/alterar código-fonte, módulos, arquitetura de produto, estratégias e indicadores em fonte, testes novos, documentação, correções, commits Git locais e replanejamento técnico dentro desta fronteira. Não exigir novo aceite para decisões técnicas ordinárias que preservem escopo, critérios e limites. Nenhuma duração/quantidade de chamadas ilimitada é concedida: cada sessão conserva orçamento finito aprovado, consumo histórico e paradas obrigatórias.

Raízes graváveis propostas, relativas ao projeto: `strategy_factory/`, `src/`, `tests/`, `docs/`, `examples/`, `config/research/` e `artifacts/offline/`. A negação abaixo tem precedência. Novos arquivos fora dessas raízes exigem revisão; root README pode ser atualizado somente como documentação sanitizada. Fonte MQL5 nova fica em `src/mql5/`, sem instalação/compilação/cópia para diretórios homologados.

`artifacts/offline/<id exclusivo>/` recebe exclusivamente saídas sintéticas, temporários e bancos novos. Nunca usar runs históricos como destino. Ler somente fontes do produto, fixtures sintéticas e arquivos de entrada explicitamente relacionados no manifesto; não varrer discos, perfis, cofre ou clipboard. O sandbox restringe escrita a C:\estrategia e temporários designados; testes de aceitação usam espelho descartável separado do original.

Os cinco artefatos desta aprovação são selados por hash no plano de controle e não editáveis pelo worker, mesmo quando ficam sob docs/ ou config/research/. A política não é carregada de um arquivo de produto que o próprio worker possa reescrever. Antes da ativação, a integração deve demonstrar restrições efetivas: um prompt e hashes verificados só depois da execução não impedem exposição prévia de credenciais. Se a proteção necessária não puder ser comprovada, permanecer desativada e reportar a limitação.

## Fronteiras imutáveis do agente de produto

- Todo `C:\CodexAutoDev`, incluindo supervisão, budget, checkpoint, aceitações, atalhos, perfis e políticas. Só o plano de controle confiável atualiza seus próprios estados pelos fluxos auditados existentes; o worker não escreve neles.
- `.codex/`, `.git/config`, `.git/hooks`, `.gitignore`, `.gitattributes`, configurações de autenticação, credenciais, variáveis persistentes, registro, ACLs e políticas de sandbox. Git local só via fluxo aprovado com hooks/fsmonitor desabilitados por comando; sem configurar hooks, remotes, aliases, filtros ou drivers. Sem hard reset, limpeza destrutiva, amend de histórico ou push.
- `infra/`, `MQL5/`, `MT5StrategyFactoryPOC/`, instalações/data roots de MT5/Rico, executáveis/binários homologados e todo `runs/`, incluindo brutos, ledgers, recibos, bloqueios e guardas. Leitura de evidências sanitizadas pode ser aprovada por manifesto, nunca leitura de segredos/contas por conveniência.
- Arquivos operacionais de `config/` fora de `config/research/`; nenhum plano/manifesto de pesquisa vira execução real por renomear status ou flags.
- Módulos protegidos enumerados em `config/research/sf_offline_boundary.proposed.json`: transporte/MCP, Tester, consentimento, segurança de lotes, política de dataset/risco, gerador validado/template, revisão de prontidão e workspace. Novos módulos não podem substituir/monkeypatchar ou desviar esses controles. Refatoração que os afete requer revisão separada.
- Testes históricos existentes, fixtures de contrato e aceitações independentes. Acrescentar novos testes é permitido; não remover, pular, renomear para esconder, enfraquecer asserts ou alterar fixtures antigas para fabricar aprovação. Melhorias legítimas nesses testes passam por revisão específica. Os 130 testes AutoDev e 513 produto/81 compatibilidade/18 aceitação compõem o piso de regressão atual.

Não autorizar rede, downloads, novas dependências, MCP, cofre/clipboard, APIs MetaTrader5, abertura de apps, compilação, Tester/backtests, conta/ordens, publicação ou compra de créditos para o worker offline. Criar código-fonte de estratégia/indicador não autoriza executá-lo em mercado. Métodos com rede/MT5 não podem ser disparados por imports, testes ou subprocessos. Sem symlinks, junctions, reparse points ou hardlinks que atravessem a fronteira.

## Integração única do executor, separada da permissão permanente

Depois de aprovação humana deste pacote, permitir ao integrador confiável, fora do worker de produto, implementar **somente** o necessário para registrar SF-OFFLINE-1 no executor existente:

- Criar `factory_successor.py`, `acceptance/factory_successor.py`, `tests/test_factory_successor.py`, perfil offline próprio e plano materializado versionado sob C:\CodexAutoDev.
- Alterar apenas os pontos de despacho de `main.py`, `preflight.py`, `launcher.py` e `profile_manager.py`; extensão de inclusão de fontes no espelho em `factory_offline_tests.py`. Se houver outro arquivo necessário, apresentar o diff/justificativa antes de ampliar a lista.
- Manter `factory_phase5.py`, o plano e o checkpoint históricos intactos. Não alargar sua ALLOWED nem remover seu gate; novo perfil identifica inequivocamente o plano sucessor. Não reutilizar o executor genérico para contornar a verificação.
- Preservar sandbox MXC/workspace-write, rede desabilitada, auto_review/on-request, clientes MCP desligados por invocação, higienização de ambiente, locks, validação de Git/arquivos, contabilidade cumulativa e todas as paradas de segurança, uso e orçamento. Sem modificar codex_client, budget_policy, checkpoints_store, guardas, políticas financeiras ou verificadores de workspace.
- Criar uma **nova execução filha** para o plano sucessor, vinculada ao checkpoint histórico; não marcar a homologação MCP como concluída. Transportar os três contadores cumulativos de tokens, três chamadas e 391,875 segundos; gravar uma única importação de uso, sem duplicar a fase 5 no consolidado diário nem zerar saldos. A fonte de migração e os hashes antigos/novos ficam auditados.
- Construir manifesto independente abrangendo arquivos novos ainda ignorados, denials e testes protegidos; comparação de baseline própria do perfil. Aprovação por tarefa exige paths autorizados, nenhum protegido alterado, teste comportamental independente no plano de controle, regressão e commit local revisado. O modelo não controla seu verificador.
- Validar cada negação e a continuação offline com MCP indisponível usando fakes. Os testes devem provar que outra instalação/projeto, arquivo crítico, link, alteração de budget/checkpoint, uso desconhecido, limite oficial, resposta incompatível, operação real e push continuam recusados. Nenhum código de produto é executado fora do sandbox para a aceitação.

Essa autorização pontual de integração não se transfere ao worker para editar o controlador. Nenhum arquivo do controlador foi alterado nesta fase. Trata-se de conexão da fronteira aprovada, sem funcionalidades secundárias de interface, agendamento ou supervisão.

## Plano e orçamento

Plano proposto `SF-PROLONGADO-1`, detalhado em `SF_SUCCESSOR_PLAN.md` e JSON correspondente. Seu grafo **offline não contém gate MCP**. A trilha MCP é separada, opcional e dependente de autorização própria; não ocupar a primeira tarefa do plano offline com ela.

Limites propostos por sessão: 480 minutos acumulados; 50 chamadas acumuladas; uma correção por tarefa (duas tentativas); timeout máximo 420 segundos; 500.000 tokens novos, 10.000.000 cache, 100.000 saída. Incluem o consumo histórico. A conversa atual não é medida pelo ledger do worker. Revogação, pausa, erro de integridade, limite oficial, uso desconhecido ou orçamento esgotado sempre param; não são impedimentos técnicos que possam ser ignorados em nome da continuidade.

Após integração e testes, realizar preflight/dry-run sem modelo nem operações externas. Configuração fica desativada até confirmação local **ATIVAR**, com resumo real dos limites e consumo. Só então iniciar pelo atalho existente. Aprovar este documento não simula digitação do proprietário nem altera arquivos de ativação antecipadamente.

Replanejamento pode escolher tarefas offline prontas, decompor trabalho e propor novos módulos dentro da fronteira. Mudanças de grafo criam revisão auditada do plano e preservam resultados concluídos; não mudar aceitação retrospectivamente, plan_digest ou pins para mascarar falha. Enquanto o integrador não comprovar seleção por dependências, materializar blocos offline em ordem topológica, deixando todas as tarefas operacionais fora da fila ativa. Sem implementar agendador secundário nesta fase.

## Solicitação humana única

Revisar os documentos e hashes em `C:/CodexAutoDev/reports/phase9-approval-package.json`. Responder em uma mensagem:

`APROVO SF-OFFLINE-1 E SF-PROLONGADO-1, INCLUINDO A INTEGRAÇÃO ÚNICA DO EXECUTOR E OS LIMITES PROPOSTOS. MCP DIAGNÓSTICO: NÃO.`

Isso aprova o trabalho offline e sua integração; a confirmação local ATIVAR continua como etapa final de ativação. Se desejar também conhecer os caminhos efetivamente anunciados, substituir NÃO por SIM e acrescentar nesta mesma mensagem a frase do mecanismo:

`Autorizo a consulta de workspace pela ferramenta apresentada.`

A opção SIM refere-se **somente** à tentativa diagnóstica descrita em `SF_PHASE9_MCP_DIAGNOSIS.md`: nova guarda, até uma get_workspace_info no MetaEditor Factory/22355, quatro POSTs previstos, teto seis, zero retries/fallback, projeção explícita de raízes/flags sem Community, sem aprovar operação nem aceitar permissões excessivas. Qualquer bloqueio dessa trilha não bloqueia a aprovação offline. Ausência de SIM explícito significa que a consulta permanece proibida.
