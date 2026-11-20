# Fase 2.5 — evidências e parâmetros efetivos

Implementação offline: `strategy_factory/traceability.py`, integrada ao resumo e
à comparação existentes. Nenhum backtest, otimização, ordem ou acesso às
credenciais é necessário para enriquecer arquivos já salvos. Não modifica
relatórios, EAs, configurações de negociação ou o inicializador.

## Registro por campo

O resumo `run_summary` passa à versão **1.1**, mantendo os campos financeiros
e de cenário da versão anterior e acrescentando `traceability`. Cada campo tem:

```json
{
  "requested": 9,
  "confirmed": "9",
  "status": "confirmed",
  "matches_requested": true,
  "evidence": [{
    "source": "journal",
    "locator": "records[12].message",
    "artifact_sha256": "SHA256_DO_PAYLOAD_CANONICO",
    "value": "9"
  }]
}
```

O exemplo é ilustrativo, não uma evidência real. Os estados são:

| Estado | Significado |
|---|---|
| `confirmed` | Existe evidência vinculada ao teste; se solicitado, o valor coincide |
| `mismatch` | Solicitado e confirmado diferem; ambos ficam preservados |
| `conflicting` | Duas evidências discordam ou há duplicidade ambígua |
| `unverifiable` | Não há confirmação utilizável; `confirmed=null` |

Zero e `false` explicitamente fornecidos são valores conhecidos. Ausência nunca
vira zero, comissão gratuita ou swap inexistente. A igualdade numérica preserva
inteiros grandes e distingue booleanos de números. Strings de identificadores
como `001` não são convertidas silenciosamente em `1`.

## Fontes e limites da confirmação

- **Report com `run_id` correspondente:** campos nativos disponíveis, como símbolo,
  depósito, barras e ticks gerados. Campos que não existem continuam desconhecidos.
- **Journal recortado e vinculado:** cabeçalho do teste confirma EA, símbolo,
  timeframe e datas; linhas nativas identificadas confirmam depósito, moeda,
  alavancagem, modelo de ticks, qualidade declarada e sincronização do histórico.
- **Inputs efetivos:** somente o bloco nativo `started with inputs:` e suas linhas
  contíguas são aceitos. Logs arbitrários do EA contendo `InpX=...` não bastam.
  Blocos múltiplos, duplicados, incompletos ou journal truncado não habilitam
  confirmação completa do inventário de inputs.
- **INI e SET:** são snapshots **solicitados**, nunca prova de uso efetivo.
  Divergências entre JSON solicitado e esses snapshots também são registradas.
  Apenas `[Tester]` é extraído do INI; outras seções não são copiadas para o resumo.
  Ranges `||` de SET têm apenas o valor-base lido, sem autorizar otimização.
- **Snapshots de ativo/histórico:** ficam em `observations`, como
  `not_execution_confirmed`. Especificação de swap, volume mínimo ou disponibilidade
  histórica atual não comprova custos ou dados efetivamente usados no teste.

Para SET sem informação de tipos, diferenças de formatação entre strings podem
ser sinalizadas conservadoramente. Use `--inputs` com JSON tipado quando os tipos
do EA forem conhecidos, preservando também o SET original como evidência solicitada.

IDs e recorte do journal ainda precisam de auditoria do chamador. SHA256 do JSON
canônico vincula o campo ao payload usado, não autentica o servidor e não equivale
ao hash dos bytes do arquivo original. Esse hash tampouco identifica todo o
histórico carregado pelo agente ou o modelo de custos. Nenhum token, cabeçalho de
autenticação ou conteúdo bruto do journal é copiado para `traceability`.

O EA é identificado pelo nome do arquivo encontrado nas evidências. Isso não
comprova a identidade binária do EX5 nem sua equivalência a um fonte/versionamento.
Essas identidades precisarão de captura auditada própria antes dos lotes.

## Tester, custos e histórico

`parameters` registra EA, ativo, timeframe, período, depósito, moeda, alavancagem,
modelo e atraso. `tester_settings` registra o que estiver confirmado sobre
otimização, forward, visualização, agentes e builds. Observar um agente local
**não** comprova `use_remote=false`; build do agente **não** vira build do terminal.

`costs` distingue moeda dos custos, spread em pontos, modelo de spread, totais e modelos de comissão,
swap e fees, slippage total e fingerprint da configuração. Não calcula comissão
como resíduo de lucro/perda brutos nem extrai spread efetivo de bid/ask atuais.
Totais financeiros iguais não comprovam configurações de custos iguais.

`history` distingue barras/ticks gerados, modelo de geração, qualidade declarada,
origem, disponibilidade, cobertura, sincronização e hash do conteúdo completo.
Datas de sincronização do cache são separadas das datas de disponibilidade de uma
consulta. Uma amostra de barras e um histórico declarado 100% não comprovam
cobertura integral, ticks reais ou igualdade do dataset entre testes.

O JSON mínimo Rico atualmente observado não fornece todos esses dados. Não foram
inventadas ferramentas MCP nem novos campos nativos. O leitor também aceita um
**contrato normalizado de exportação auditada**, identificado pelo `run_id`:

- `inputs`: objeto com nomes/valores efetivos;
- `tester_settings`: campos canônicos de `parameters` e flags do Tester;
- `costs`: `currency`, `spread_points`, `spread_model`, `commission_total`, `commission_model`,
  `swap_total`, `swap_model`, `fees_total`, `fee_model`, `slippage_total`,
  `configuration_sha256`;
- `history`: `origin`, `available_from`, `available_to`, `quality_percent`,
  `generated_bars`, `generated_ticks`, `tick_source`, `coverage_complete`,
  `content_sha256`.

Esse contrato é da Factory para dados exportados e conferidos pelo chamador;
não significa que `tester_get_report` já publique essas estruturas. Não preencher
campos ausentes com valores presumidos. Fingerprints declarados na exportação
também exigem auditoria do processo que os produziu.

## Uso sem alterar relatórios originais

```powershell
python -m strategy_factory.analysis summarize runs/EXECUCAO --journal runs/journal_EXECUCAO.json --journal-run-id ID --tester-ini runs/tester_solicitado.ini --inputs-set runs/inputs_solicitados.set --history-snapshot runs/historico_consultado.json --symbol-snapshot runs/especificacao_ativo.json --output runs/resumo_enriquecido.json
```

INI/SET aceitam UTF-8 e UTF-16; JSON e envelopes MCP usam o leitor estrito já
existente. Os argumentos de snapshot são opcionais. O código não segue caminhos
remotos de INI/SET encontrados em logs ou configurações e não chama o MT5.
Os arquivos de entrada são lidos; a saída é exclusiva e nunca sobrescreve um
arquivo existente. Relatórios antigos continuam sendo interpretados pelo mesmo
analisador financeiro, sem migração destrutiva.

Para futuras execuções autorizadas, o resumo automático do executor já incorpora
o ledger das evidências disponíveis no relatório. O enriquecimento posterior
acrescenta journal e snapshots explícitos, sem alterar os resultados originais.
Não há coleta MCP adicional automática nesta etapa.

## Comparação e compatibilidade

`compare` aceita resumos **1.0 e 1.1**. Resumos 1.0 continuam visíveis, mas ficam
condicionais por falta de rastreabilidade. Eles não são reescritos nem promovidos
a confirmados com base em hashes opacos fornecidos pelo usuário.

Para resumos 1.1, a comparação acrescenta `traceability_comparison` por campo:
`same`, `different` ou `unverifiable`. Dois valores ausentes são **não verificáveis**,
não iguais. A coleção mantém as diferenças de inputs entre estratégias e as
divergências entre solicitado/efetivo em cada execução.

Além das regras financeiras anteriores, deltas só são habilitados quando cenário,
inventário de inputs, configurações locais do Tester, conteúdo histórico e
configuração de custos estão confirmados, e os fingerprints/build efetivos
comparáveis coincidem. Custos totais podem variar com as operações; isso não é
automaticamente uma diferença de política de custos. A classificação de dados e
integridade continua separada de rentabilidade.

## Validação e resultado da reanálise local

**115 testes Python aprovados**, incluindo compatibilidade 1.0, dados incompletos,
inputs divergentes, duplicados e tipados, zero conhecido versus ausente,
snapshots não efetivos, custos desconhecidos, qualidade histórica declarada,
fingerprints, comparação condicional e exportação sintética completa.

`examples/analyze_synthetic.py` foi atualizado com o contrato de exportação
normalizado, integralmente sintético. Use um diretório novo:

```powershell
python examples/analyze_synthetic.py --output-dir runs/exemplo_sintetico_25
python -m unittest discover -s tests -v
```

A reanálise offline de evidências já existentes confirmou os seis inputs do EA
de homologação e os campos de cenário presentes no journal. Confirmou também
qualidade declarada, contagens geradas e sincronização. Custos efetivos, dataset
completo e parte das flags do Tester continuam indisponíveis. Os hashes dos bytes
das evidências de entrada foram verificados antes/depois e permaneceram iguais.
Os resultados detalhados e esse registro de preservação ficam apenas em
`runs/phase25_enrichment/`, fora do Git. Nenhum novo backtest foi executado.

## O que ainda falta antes de lotes

Captura auditada e vinculada à execução de configurações/inputs efetivos,
identidade binária do EA, versão do terminal, conteúdo histórico completo e
políticas de spread/comissão/swap/fees. Depois, definir manifesto, limites de
recursos, autorizações e tratamento de falhas antes de implementar o executor
de lotes. Esta fase não inicia a Fase 2.6 nem autoriza execuções adicionais.
