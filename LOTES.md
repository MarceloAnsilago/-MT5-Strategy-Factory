# Fase 2.6 — manifesto, orçamento e autorização de lotes

Infraestrutura de planejamento e **simulação offline**. Não existe backend de
execução real neste módulo: `BatchController.execute()` recusa a chamada mesmo
com autorização válida. Não há transporte MCP, inicialização do MT5, otimização
ou envio de ordens. A infraestrutura anterior permanece disponível e inalterada.

## Módulos e esquema

- `batch_manifest.py`: validação estrita, SHA256 canônico, orçamento e registros
  de aprovação com escopo/validade/tentativas explícitas.
- `batch_control.py`: estados persistentes SQLite, snapshots, exclusão entre
  workers, cancelamento, reserva durável de tentativas e retomada selecionada.
- `batch.py`: CLI de planejamento, simulação e inspeção; não tem comando live.
- `config/batches/manifest.schema.json`: JSON Schema versionado **1.0**.
- `config/batches/example.json`: exemplo com caminho fictício e hashes ausentes.

O manifesto identifica lote/revisão, estratégias/versões, EAs e hashes declarados,
IDs de execução, cenários e inputs. Cada estratégia pode ter `compiled_sha256`
e `source_sha256`; `null` significa desconhecido, nunca identidade confirmada.
O planejador não lê o binário e não promove esses hashes a confirmação de runtime.

A validação Python é obrigatória. O JSON Schema verifica a forma; as verificações
aritméticas, caminhos EX5, parâmetros MT5, referências, duplicações e campos
sensíveis são aplicadas por `validate_manifest`, reutilizando `BacktestConfig`
e a validação de inputs existentes. Sem dependências Python adicionais.

IDs não permitem separadores de caminho. Não aceita campos extras ou políticas
de trading operacional, otimização, forward, agentes remotos ou retries automáticos.
Uma mesma estratégia/cenário/inputs não pode aparecer duplicada sob outro ID no
mesmo manifesto. Versões e hashes fazem parte do conteúdo autorizado.

## Orçamento

| Campo | Regra |
|---|---|
| `max_strategies` | Máximo de estratégias declaradas |
| `max_backtests` | Máximo total de tentativas, inclusive as reservadas/interrompidas |
| `max_attempts_per_test` | Teto por ID; não significa autorização de retry |
| `timeout_per_test_seconds` | Limite por tentativa |
| `timeout_batch_seconds` | Envelope de tempo do lote |
| `max_concurrency` | Somente 1 nesta versão |
| `max_artifact_bytes` | Bytes lógicos dos artefatos pertencentes ao lote |
| `max_run_artifact_bytes` | Bytes lógicos por diretório de tentativa |
| `min_free_disk_bytes` | Espaço livre mínimo verificado antes das gravações |

Planejamento conservador: `runs × max_attempts_per_test ≤ max_backtests` e
`runs × max_attempts_per_test × timeout_per_test_seconds ≤ timeout_batch_seconds`.
Não presume que testes terminarão cedo. Orçamentos inválidos bloqueiam o plano.

O exemplo reserva uma estratégia, dois itens, uma tentativa por item, 180 s por
teste, 360 s por lote, 1 MiB de artefatos, 256 KiB por tentativa e 64 MiB livres.
São valores de demonstração, não autorização para executar o cenário.

A simulação controla tempo **lógico sintético**, além de verificar o tempo de
parede do seu próprio loop. Não espera 180 s nem mede um backtest real. Cenários
sintéticos podem representar falha/timeout sem chamar um runner externo.

Bytes UTF-8 são contados antes de gravar, com criação binária exclusiva para
evitar diferenças CRLF no Windows. Artefatos existentes contam para a quota.
O SQLite central de controle, seus journals, metadados do filesystem, uso por
outros processos e caches/logs do MT5 **não** entram nessa quota lógica. Há
verificação de espaço livre, mas não uma quota de SO, limite de RAM/CPU nem
watchdog de processos externos. Esses controles precisam existir no backend real
futuro. Escritas/estados de erro também dependem de disco funcional.

## Uso offline

```powershell
python -m strategy_factory.batch validate config/batches/example.json
python -m strategy_factory.batch propose-authorization config/batches/example.json
python -m strategy_factory.batch --root runs/lote_exemplo plan config/batches/example.json
python -m strategy_factory.batch --root runs/lote_exemplo simulate config/batches/example.json
python -m strategy_factory.batch --root runs/lote_exemplo status batch-demo-001
```

`validate` e `propose-authorization` não criam aprovações nem iniciam testes.
`simulate` produz apenas artefatos locais de simulação, não resultados financeiros.
Repetir o comando após conclusão é bloqueado. Use outro ID/root para uma nova
demonstração deliberada; isso não reutiliza permissões de um lote real.

O snapshot do manifesto é imutável. Reutilizar ID com conteúdo diferente é
bloqueado; um novo plano exige novo ID e aprovação própria. SHA256 usa JSON
canônico: ordem de chaves e formatação não alteram o hash; qualquer alteração
de conteúdo, inclusive orçamento, revisão ou inputs, invalida a aprovação anterior.

## Autorização futura de um lote pequeno

1. Preparar um manifesto privado em `runs/`, com um EA permitido e um ou dois
   testes curtos, somente locais e sem otimização/forward.
2. Auditar EA compilado/hash, cenário, inputs efetivos, histórico, custos e
   recursos disponíveis. Os bloqueios de rastreabilidade da Fase 2.5 continuam
   relevantes; aprovar um manifesto não confirma essas evidências.
3. Validar e apresentar ao usuário o manifesto, seu SHA256, orçamento, IDs e
   tentativas exatas, prazo de validade e limitações.
4. Aguardar aprovação humana explícita vinculada ao conteúdo. A frase registrada
   segue `AUTORIZO LOTE TESTER <batch_id> SHA256 <hash>`.
5. **Somente depois** registrar a intenção pela API, por exemplo:

```python
record = controller.authorization(
    batch_id,
    approval=frase_explicitamente_aprovada,
    approved_by="operador",
    expires_at=prazo_iso_com_fuso,
    permitted_attempts={"run-a": [1], "run-b": [1]},
)
```

O registro inclui identificador único, hash, emissor, horários com fuso e escopo
`strategy_tester_backtests_only`. Não autoriza negociação em conta real ou demo
fora do Tester. Tentativa 2 não é autorizada por um teto de 2: precisa constar
explicitamente em nova aprovação, após revisão da falha e do estado persistido.

`check_authorization` exige registro local inalterado, manifest hash correto,
validade, tentativa permitida e ainda não consumida. Cancelamento revoga os
registros existentes; retomada não ressuscita aprovações revogadas. Não há
aprovação real registrada pelos exemplos desta fase; testes usam registros
sintéticos em diretórios temporários.

Esses registros auditam a intenção do chamador, não são assinatura digital nem
prova criptográfica de aprovação humana. O processo que registra a aprovação
precisa respeitar a conversa e as permissões do operador. SQLite e filesystem
devem permanecer sob controle do usuário; um administrador local pode alterá-los.
Credenciais MCP/DPAPI não são lidas, duplicadas ou armazenadas por esse fluxo.

**Nesta versão a autorização não desbloqueia execução real.** O resultado do
check é `valid_for_planning=true`, `live_execution_enabled=false`. Ainda faltam
um adaptador de lote real, preflight auditado, controle/cancelamento do Tester e
limites físicos testados; implementar e habilitar isso exige uma etapa autorizada
posterior. Não converter um registro de planejamento em chamada ao Tester.

## Estados, falhas e retomada

O SQLite grava estados e eventos em transações, com sincronização completa.
Lotes podem ficar `planned`, `simulating`, `simulated`, `cancel_requested`,
`cancelled`, `failed`, `blocked`, `paused` ou `interrupted`. Cada item mantém
`pending`, `simulating`, `simulated`, `cancelled`, `failed` ou `interrupted` e
o histórico de tentativas. `simulated` não significa backtest concluído.

A reserva da tentativa é gravada **antes** de seus artefatos. Depois de falha
ou interrupção, esse número nunca é reaproveitado. Arquivos anteriores ficam
em `runs/<run_id>/attempt_N/`, sem sobrescrita. A simulação para na primeira falha;
não tenta novamente e não avança para o próximo item silenciosamente.

```powershell
python -m strategy_factory.batch --root runs/lote_exemplo cancel batch-demo-001
python -m strategy_factory.batch --root runs/lote_exemplo resume-plan batch-demo-001 --attempt run-a:2 --output runs/retomada.json
python -m strategy_factory.batch --root runs/lote_exemplo simulate runs/manifesto_privado.json --resume-plan runs/retomada.json
```

O exemplo de retomada exige que `run-a` exista, a tentativa 1 esteja consumida,
o manifesto reserve tentativa 2 e o orçamento comporte essa seleção. Não se
aplica diretamente ao exemplo público, que permite somente uma tentativa.
Itens cancelados antes de começar podem ser selecionados explicitamente como
tentativa 1; itens concluídos são rejeitados. O plano de retomada tem ID e hash
do manifesto e é **somente de simulação**, nunca uma autorização live.

Cancelamento é persistente e cooperativo: impede o próximo item no ponto seguro.
Não mata processos nem invoca ferramentas MT5. Se todos os itens já terminaram,
cancelar não reescreve seus resultados. Resultados parciais permanecem preservados.

Um lock exclusivo no root impede workers cooperantes simultâneos, inclusive de
lotes diferentes. Use um root compartilhado por controlador/terminal. Não é lock
distribuído nem bloqueia outro root, outro usuário ou a interface do MT5.
Lock remanescente após crash não é removido automaticamente. Sua reconciliação
manual exige verificar que não há worker ativo. `recover` só marca reservas
incertas como interrompidas quando consegue adquirir o lock; não repete nada.
Falha durante a preparação pode deixar um diretório órfão preservado; ele não é
sobrescrito. Recuperação não restaura espaço, permissões ou um banco danificado.

## Resumo 1.1 e validação

Cada tentativa de simulação concluída ou com falha sintética gera resumo 1.1,
identificado como `evidence_kind=simulation`, com contexto do lote, estratégia,
versão, hash do manifesto, tentativa e hashes **declarados** do EA. Sem relatório
nativo, métricas, custos, inputs efetivos e histórico permanecem não verificáveis.
Uma falha de armazenamento pode impedir a escrita do resumo; estado e artefatos
parciais existentes ficam no ledger para inspeção, sem inventar resultado.

**139 testes Python aprovados**, incluindo os 115 anteriores e testes de manifesto,
limites, aprovação expirada/alterada, revogação persistente, duplicação, timeout,
cancelamento, retomada, recuperação de reserva, quotas, locks e CLI offline.

```powershell
python -m unittest discover -s tests -v
```

O schema, o manifesto fictício, código, testes e documentação podem ir ao Git.
SQLite, autorizações, estados, resultados e resumos gerados ficam em `runs/`,
fora do Git. Nenhuma execução real foi autorizada ou iniciada nesta fase.
