# Fase 2.4 — resumos e comparação offline

Esta etapa não executa backtests, otimizações, ordens ou chamadas MCP. Não altera
os EAs, o inicializador ou credenciais. Reutiliza `reports.analyze_report` e
`financial.validate_financial`; não cria outro cálculo financeiro independente.
Não há geração de estratégias, busca de parâmetros ou executor de lotes.

## Resumo padronizado por execução

`strategy_factory/analysis.py` produz JSON `run_summary`, versão `1.0`, com:

- `run_id` remoto e `local_run_id` para execuções sem identificador remoto;
- estado de execução e tempos disponíveis; simulação e falha ficam explícitas;
- nome do EA, inputs fornecidos e parâmetros do cenário solicitado;
- métricas com valor, disponibilidade, origem e todos os candidatos reconhecidos;
- métricas calculadas identificadas por origem, fórmula e operandos;
- qualidade dos dados, integridade da reconciliação e avisos sobre lacunas;
- contexto fornecido: build, agentes e fingerprints de histórico/custos.

Os campos financeiros continuam incluindo lucro líquido, saldos, lucro/perda
brutos, Profit Factor, drawdowns de saldo/patrimônio, operações, negócios, ordens,
posições, vencedoras/perdedoras, acerto, expectativa e qualidade declarada do histórico.
Contagens diferentes não são convertidas entre si. Períodos só aparecem quando
publicados explicitamente pelo analisador existente.

Em caso de conflito, o valor selecionado fica `null`; os candidatos são preservados.
O resumo prefere relatório, journal vinculado, referência nativa e cálculo nativo,
nessa ordem, quando disponíveis e consistentes dentro das tolerâncias existentes.
Um valor disponível só no journal fica identificado como `journal`; isso não muda
o campo original do relatório. Estados `infinite`, `undefined`, `not_applicable`
e `inconclusive` continuam explícitos. Valor zero conhecido não vira dado ausente.

Metadados são limitados a campos conhecidos. O caminho absoluto do EA não é
repetido no resumo: mantém-se o nome do arquivo. Inputs aceitam apenas escalares
finitos, e chaves com indicação de credenciais são rejeitadas. Isso não torna
um resumo público: valores de inputs, IDs e métricas podem ser privados.

## Duas classificações independentes

| Qualidade dos dados | Significado |
|---|---|
| `complete` | Cobertura das métricas financeiras centrais, parâmetros e inputs fornecidos; execução concluída |
| `partial` | Lacunas, metadados desconhecidos, fonte incompleta/truncada ou ambiguidade de parsing |
| `unavailable` | Nenhuma métrica numérica utilizável |
| `invalid` | Divergência ou inconsistência entre execução, símbolo ou depósito solicitado e reportado |

A cobertura central inclui todas as métricas canônicas, exceto ordens e posições,
que frequentemente não são publicadas. Estados matematicamente não aplicáveis
não exigem um número inventado. Ausência de ordens, posições e períodos sempre
gera aviso, mesmo quando a cobertura financeira central é completa.

| Integridade da reconciliação | Significado |
|---|---|
| `verified` | O validador financeiro confirmou os campos comparados com evidência externa completa |
| `partial` | Existe evidência externa, mas faltam comparações ou fontes completas |
| `not_reconciled` | Somente verificações internas; sem journal ou referência externa |
| `divergent` | Há conflito financeiro, de contagem ou de identidade/proveniência |

Qualidade completa não significa reconciliação completa. Histórico declarado
como 100% não comprova independentemente cobertura, ticks reais, custos ou
ausência de vieses. Nenhuma classificação avalia rentabilidade, robustez ou
aprovação para negociação; `profitability_assessed` é sempre `false`.

## Analisar arquivos existentes sem alterar evidências

```powershell
python -m strategy_factory.analysis summarize runs/EXECUCAO --output runs/resumo_EXECUCAO.json
```

O diretório contém os artefatos já produzidos pela Factory: `request.json`,
`remote_run.json`, `report.json`, `result.json` ou `failure.json`. São lidos apenas
nomes conhecidos. Não percorre logs, não lê credenciais nem segue `inputs_path`
remoto. A saída é nova; não sobrescreve resumos ou evidências anteriores.

Para complementar com evidências locais e inputs conhecidos:

```powershell
python -m strategy_factory.analysis summarize runs/EXECUCAO --journal runs/journal_EXECUCAO.json --journal-run-id ID --inputs runs/inputs_EXECUCAO.json --context runs/contexto_EXECUCAO.json --output runs/resumo_completo_EXECUCAO.json
```

`inputs` é um objeto JSON com os inputs do EA. `context` aceita `terminal_build`
inteiro positivo, `agents="local_only"`, `history_fingerprint` e
`costs_fingerprint` como SHA256 hexadecimal de 64 caracteres. Fingerprints
devem vir de evidências auditadas, com procedimento de hashing consistente.
O fingerprint de custos deve representar também spread, comissões, swap e a
política de execução efetiva; igualdade de depósito/moeda não substitui esse controle.
Não criar hashes fictícios para preencher um resultado observado.

O chamador precisa recortar e vincular o journal ao único teste correto. IDs e
fingerprints são declarações do chamador, não assinaturas nem prova independente.
O resumo marca `parameter_provenance="requested_not_verified"`: parâmetros do
`request.json` não comprovam sozinhos o INI efetivamente usado no MT5.
Envelope MCP JSON, UTF-8 e UTF-16 são aceitos; erros MCP, JSON com chaves duplicadas
e números não finitos são rejeitados.

Para futuras execuções já autorizadas, `TesterRunner` grava automaticamente
`run_summary.json` para conclusão, simulação e falhas tratadas após aquisição do
lock. Inputs e contexto não verificados ficam desconhecidos. Depois da captura
do journal, pode-se gerar uma versão enriquecida em outro arquivo.
Falhas anteriores à aquisição do lock ou um crash abrupto não garantem resumo;
`summarize` pode analisar posteriormente os artefatos existentes. Essa integração
não autoriza nem dispara novas execuções.

## Comparar resultados existentes

```powershell
python -m strategy_factory.analysis compare runs/resumo_A.json runs/resumo_B.json --output runs/comparacao_AB.json
```

A coleção contém cópias dos resumos e comparações par a par. Não agrega médias
de estratégias, não escolhe vencedor e não usa valores ausentes como zero.
IDs duplicados e schemas incompatíveis são rejeitados. A ordem dos resumos é
preservada; não há ordenação por lucro nem ranking (`ranking=null`).

São confrontados símbolo, timeframe, datas, modelo de ticks, depósito, moeda,
alavancagem e atraso. Build, histórico, custos e agentes são avaliados à parte.
EAs e inputs podem variar intencionalmente: a coleção mantém essas diferenças
para revisão, sem tratá-las como cenários idênticos de uma mesma estratégia.

| Comparabilidade | Regra |
|---|---|
| `comparable` | Cenário/contexto fornecidos coincidem; dados completos e reconciliação verificada |
| `conditional` | Mesmo cenário conhecido, mas contexto, inputs ou evidências são parciais |
| `insufficient_context` | Falta parâmetro essencial do cenário |
| `not_comparable` | Cenário/contexto diferentes ou mistura de dados sintéticos e observados |
| `excluded` | Execução não concluída ou evidências inválidas/indisponíveis |

Deltas `direita - esquerda` só são calculados para pares `comparable`, por
métrica disponível. Nos demais casos ficam `null`; os valores individuais
continuam visíveis. Comparabilidade é uma triagem das declarações recebidas,
não prova de equivalência entre ambientes nem recomendação de investimento.

## Exemplo inteiramente sintético e testes

```powershell
python examples/analyze_synthetic.py
python -m unittest discover -s tests -v
```

O exemplo reutiliza a fixture sintética existente, cria duas variantes e gera
dois resumos e uma comparação em `runs/synthetic_phase24/`. Todos são marcados
`evidence_kind="synthetic"`. O diretório precisa ser novo; para repetir, escolha
outro com `--output-dir runs/outro_exemplo_sintetico`. Não confundir esses números
ou fingerprints de demonstração com resultados observados.

Validação: **94 testes Python aprovados**, incluindo os contratos anteriores,
resumos de falha/simulação, conflitos, referências de outra execução, candidatos
derivados, cenários/custos incompatíveis, falta de contexto, não sobrescrita,
isolamento, CLI offline e separação entre qualidade e lucro/prejuízo.

Os novos artefatos de análise ficam em `runs/`, ignorado pelo Git. Somente código,
exemplo sintético, testes e documentação devem ser publicados.

## Próximas etapas

Padronizar captura auditada dos inputs efetivos, ambiente, histórico e custos;
enriquecer resumos de resultados existentes; definir um manifesto de experimentos
com orçamento e autorizações antes de criar qualquer executor de lote.
A coleção de comparação é a infraestrutura de análise desse futuro fluxo,
sem agendamento, backtests, otimizações ou ordens nesta fase.
