# Transição para homologação do workspace MCP

26/11/2026 — America/Sao_Paulo. Preparação offline; chamadas reais ainda não autorizadas. As revisões anteriores estão concluídas e não devem ser refeitas. O commit local desta entrega reúne exclusivamente os seis arquivos aprovados do plano AutoDev.

## Condições anteriores à tentativa

Obter autorização específica `new_workspace_mcp_session_and_one_reviewed_call` para uma sessão nova e uma única consulta `get_workspace_info` com `{}`. A renovação de créditos e o perfil de desenvolvimento prolongado não concedem essa autorização. O adaptador operacional ainda exige revisão própria do transporte, privacidade, limites e uso do validador offline, antes de habilitação. O verificador legado permanece intacto.

Criar uma guarda nova e exclusiva (guard), por criação atômica sem sobrescrita, antes de carregar credencial do cofre ou fazer o primeiro envio. Não reutilizar H5F, H5I-B, H5J-B, H5J-D, guardas consumidas ou sessão encerrada. Preservar a guarda ao concluir ou falhar. Nunca registrar credenciais, headers de autenticação ou identificadores de sessão.

Antes de cada POST, confirmar processo dedicado atual: PID e instante de criação, caminho e hash do EXE aprovado, build, origem/diretório de dados e listener local na porta correta pertencente ao mesmo processo. Editor: 22355; terminal: 22356. Confirmar o destino da autorização; ela não se estende automaticamente ao outro MCP. Qualquer identidade incompleta ou divergente impede envio.

O AutoDev abre somente os aplicativos dedicados, sob configuração segura com EAs/trading desabilitados e identidade validada. Confirmar essas condições atuais antes de uso operacional. Listener não comprova autenticação, workspace, modo de conta ou AlgoTrading. Se ausente, verificar localmente Ferramentas > Opções > MCP na instalação dedicada; não regenerar/copiar chaves para chat. Não iniciar instância Rico nem relaxar a validação para contornar ausência de listener.

## Sequência autorizável, ainda não executada

1. `initialize`, negociando exatamente MCP `2025-06-18`.
2. `notifications/initialized`, preservando em memória eventual `Mcp-Session-Id`; enviar `MCP-Protocol-Version: 2025-06-18` nos POSTs posteriores ao initialize.
3. `tools/list`: exigir os 23 nomes exatos observados em H5J-D, página única, sem cursor. Conferir a definição completa de `get_workspace_info` com `review_definition`; SHA-256 canônico fixo `e7261a54334778f38f7f0caa56c3fc8d3a2cd7fa327ee8c9f28198bd755ddfa2`. A descrição integra o fingerprint; `description` é anotação validada, sem conceder permissões.
4. Um único `tools/call` para `get_workspace_info`, argumentos `{}`. Exigir sucesso e `structuredContent` conforme outputSchema completo; usar `validate_workspace_result` com MQL5 esperado confirmado previamente. Validar `workspace.mql5_folder`, tipos e raízes de escrita aninhadas. Nunca usar texto como fallback.

Quatro POSTs previstos, teto absoluto proposto de seis; contar inclusive envios com falha. Zero retries, fallback, reinicialização ou chamadas adicionais com o saldo. Parar na primeira divergência ou após a única consulta. Não persistir o corpo bruto. Validar Community em memória e descartar `community_login` e metadados; guardar somente projeção sanitizada e resultado das verificações. Não fazer operação financeira, ordens, Tester, compilação ou backtest.

## Autorizações consolidadas para a continuidade

- Já autorizados: concluir esta transição offline, verificações e commit Git local dos seis caminhos. Sem push ou deploy; hooks desabilitados por comando, sem alterar configuração Git ou `.gitignore`.
- Perfil prolongado: o proprietário precisa selecionar limites e confirmar `ATIVAR` pelo fluxo local existente. Proposta: 480 minutos, 50 chamadas, uma correção por tarefa, 500.000 tokens novos, 10.000.000 em cache, 100.000 de saída. São tetos acumulados; preservar consumo histórico, três chamadas e 391,875 segundos. Créditos renovados não zeram contadores nem substituem confirmação.
- MCP: autorização específica acima e revisão do adaptador precedem credenciais e rede. Compilação, backtests e demais ferramentas precisam de escopo próprio posterior. Esta entrega não cria autorização nem guarda operacional.
- Trabalho prolongado: aprovar um plano de desenvolvimento com tarefas, caminhos e aceitação depois da homologação. O plano atual termina no gate MCP; tempo disponível não cria tarefas nem amplia permissões.

Preservar sandbox MXC, auto_review, quatro clientes MCP desativados no desenvolvimento offline, parada por limite oficial, consumo desconhecido, orçamento e integridade. Sem compra de créditos, acesso a outras instalações, mudanças de segurança, push/publicação ou reutilização de guardas.

Referências: `AUTODEV_WORKSPACE_CONTRACT_REVIEW.md`, `config/workspace/factory_review.json`; controlador em `C:/CodexAutoDev`, procedimento `docs/PHASE6_OPERATION.md` e evidências da fase 7 em `reports/phase7-*`.
