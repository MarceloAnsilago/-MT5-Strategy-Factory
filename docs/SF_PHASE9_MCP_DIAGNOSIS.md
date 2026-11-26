# Fase 9 — permissões MCP e continuidade offline

26/11/2026 — America/Sao_Paulo. Base: `b72d496`. Investigação passiva; zero chamadas MCP, acesso ao cofre, escrita de teste no servidor ou reutilização de guardas.

## O que está comprovado

| Item | Evidência e limite |
|---|---|
| Raiz esperada | `C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\AEF1E6F57078EAB3775179FCBD94D671\MQL5` |
| Instalação dedicada | `C:\estrategia\infra\mt5-factory`; origin.txt vincula a área de dados a essa instalação. A raiz esperada é sua **área de dados**, não simplesmente a pasta dos executáveis. |
| Raiz efetivamente declarada | **Literal desconhecido.** A fase 8 descartou o corpo e os caminhos externos; nenhuma evidência sanitizada preservada permite recuperá-lo. Não atribuir o caminho a Common, Tester, Logs ou outra instalação por suposição. |
| Causa exata da recusa | Em `workspace_review.validate_workspace_result`, cada `permissions.write_roots` é interpretada como caminho e deve satisfazer `root.is_relative_to(expected)`. Pelo menos uma falhou. Schema e identidade MQL5 já haviam passado nessa tentativa. |
| Permissões anunciadas | O contrato prevê read_roots, write_roots, execute_roots e can_create_files/can_modify_files/can_delete_files. Os **valores retornados** não foram conservados. O catálogo inclui ferramentas de escrita, mas sua presença não prova capacidade efetiva ou autorização de uso. |
| Permissões reais | Não aferidas por operações de arquivo ou AccessCheck do token do processo. O anúncio MCP, a DACL do disco e uma escrita efetiva são evidências distintas. Não alegar que houve escrita fora da raiz. Nenhum teste mutante foi feito. |
| Configuração local | assistant.ini contém habilitação e endpoint de ambos os servidores, sem chaves de root/folder/write/permission/allow nas duas seções MCP. Endereços 127.0.0.1:22355 e 22356. Valores de chave não foram lidos para autenticação nem publicados. |

O erro é uma incompatibilidade entre a política local estrita e as raízes anunciadas pelo servidor. Não há evidência suficiente para atribuí-lo a configuração incorreta, root compartilhado padrão ou defeito do provedor. Procurar corpo descartado em memória de processo, clipboard ou logs brutos colocaria segredos em risco e não foi usado como substituto de uma consulta autorizada.

## Opções oficiais verificadas

A [configuração oficial MetaEditor](https://www.metatrader5.com/en/metaeditor/help/mcp_and_ai/configuration) documenta habilitação, endereço, chave e endpoints MCP. Também descreve controles de trading/web/shell do assistente e o ambiente MQL5/Tester/Logs/Common. Não documenta ali uma allowlist de write_roots restrita somente à MQL5. Esses controles do assistente não são prova de isolamento equivalente para todo cliente externo. Não foi encontrada uma opção suportada para resolver a divergência nesta instalação; isso não comprova impossibilidade em todas as versões.

O [catálogo oficial de capacidades](https://www.metatrader5.com/en/metaeditor/help/mcp_and_ai/capabilities) distingue ferramentas do editor, terminal e marketdata. Uma lista de ferramentas disponível não concede uso. A [descrição do assistente](https://www.metatrader5.com/en/metaeditor/help/mcp_and_ai) esclarece que trocar sua pasta de contexto não adiciona restrições de permissão.

## Solução recomendada

**Desbloquear a rota de desenvolvimento offline, mantendo MCP bloqueado.** Não existe dependência técnica entre a consulta de workspace e escrever/testar módulos puros de pesquisa em C:\estrategia. O bloqueio atual é do executor antigo, que prende todo o plano ao gate MCP e aos seis arquivos da fase 5. A proposta de fronteira e o plano sucessor tratam isso sem tocar no validador.

Em uma trilha separada e opcional, coletar uma única projeção diagnóstica sob autorização nova: workspace.mql5_folder; read_roots/write_roots/execute_roots; três flags de permissão; relação normalizada de cada raiz com a MQL5 esperada. Só esses campos, após validação estrutural e de caminhos, podem ser persistidos em relatório privado. Não guardar Community, conteúdo textual, credencial, sessão ou corpo bruto. A coleta é evidência diagnóstica e **não aprovação operacional**, inclusive se o validador novamente recusar. Não projetar o resultado incompatível como sucesso nem mudar o fingerprint da ferramenta.

Teto proposto: uma initialize, initialized, tools/list e get_workspace_info com `{}`; quatro POSTs, limite absoluto seis, zero retries/fallback e uma consulta no máximo. Nova guarda antes do cofre/envio, processo/configuração/contrato exatos e confirmações existentes preservados. Credencial indisponível encerra a tentativa; não autoriza recuperação/rotação automática. Nenhum POST nesta fase 9 sem aceite específico.

Após conhecer os literais, avaliar nesta ordem:

1. Configuração suportada pelo fornecedor que limite o servidor às raízes aprovadas. Confirmar documentação e comportamento; não inventar chave INI nem trocar caminhos para enganar o verificador.
2. Se o servidor sempre expuser raízes adicionais, ambiente dedicado com conta Windows/VM própria, sem acervos de outros projetos, e permissões mínimas do processo. É proposta futura: criar conta/VM, mudar ACLs ou instalar binários exige escopo próprio. Isolamento de SO não equivale automaticamente à regra atual de write_roots; a homologação continua bloqueada enquanto ela falhar.
3. Adaptador/gateway específico que permita somente ferramentas e caminhos explicitamente aprovados, com canonicalização, rejeição de reparse/hardlinks, auditoria e isolamento do processo. Filtro no cliente não revoga direitos do servidor. Reescrever/ocultar write_roots para fazer o validador passar é proibido; não encaminhar a resposta filtrada como se fosse do servidor original. Eventual novo endpoint/contrato exige revisão própria.
4. Manter MCP desativado e desenvolver offline. Compilação local supervisionada e testes demo seriam fases separadas futuras, não fallback automático desta proposta.

Como referência para uma futura análise de isolamento, a [Microsoft documenta configuração do Windows Sandbox](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file) com rede desabilitada e mapeamentos somente leitura. Isso não resolve automaticamente a conexão ao localhost do host nem a regra de raízes do MCP, e não substitui o sandbox MXC atual. Não criar ou instalar esse ambiente nesta proposta.

## O que já pode avançar sem MCP

Importação de arquivos sintéticos/locais aprovados com proveniência, auditoria de dados, composição de candidatos pelo gerador existente, referências de indicadores, análise conservadora, documentação e testes determinísticos. Reusar os módulos já existentes, sem recertificar dados incompletos, reexecutar backtests ou inventar métricas.

Os módulos de transporte, consentimento, segurança, acesso ao terminal e o validador de workspace permanecem protegidos. A nova rota não abre aplicações nem importa MetaTrader5. Não é encaminhada pelo executor genérico para escapar da fronteira antiga; depende da integração estreita submetida à aprovação em `SF_OFFLINE_AUTHORIZATION_PROPOSAL.md`.

Evidências locais: `C:/CodexAutoDev/reports/phase9-before.json`, `phase9-local-mcp-metadata.json`, `phase8-live-sanitized.json`, `phase8-integrity.json`. A raiz efetiva e as flags permanecem pendência explícita da consulta opcional; não bloqueiam a fila offline proposta.
