# Estado da pesquisa offline

| Tarefa | Estado | Evidência |
| --- | --- | --- |
| SF-O01 | Concluída no bloco offline | Ingestão e auditoria de dados sintéticos com proveniência local. [Dados locais](LOCAL_DATASETS.md) |
| SF-O02 | Concluída no bloco offline | Grade limitada e catálogo de especificações e fontes. [Catálogo](CANDIDATE_CATALOG.md) |
| SF-O03 | Concluída no bloco offline | Comparação conservadora de resumos sintéticos. [Comparação](EXPERIMENT_COMPARISON.md) |
| SF-O04 | Concluída no bloco offline | Referência de indicador ATR e fonte para futura validação nativa. [Indicador](INDICATOR_REFERENCE.md) |
| SF-O05 | Concluída no bloco offline | Pipeline de fixtures, manifesto e retomada verificável. [Pipeline](OFFLINE_PIPELINE.md) |
| SF-O06 | Aceita independentemente em 27/11/2026 | E2E real no mesmo processo: duas chamadas do exemplo em pastas temporarias, fontes, hashes, manifesto, checkpoint, retomada e recusas. [Teste](../../tests/test_research_offline_e2e.py) |
| Regression e acceptance | Aprovadas no espelho protegido MXC | 540 produto + 81 compatibilidade + 18 acceptance existente = 639; SF-O06: 640, sem pulos. Controlador: 173 aprovados. Evidencia: `C:/CodexAutoDev/reports/sf-o06-direct-acceptance.json`, incluindo espelho e hashes dos quatro arquivos. Execucao direta no Codex; AutoDev e checkpoint historico preservados. |
| Validação nativa | Bloqueada neste escopo, `native_validation_pending` | Fontes MQL5 geradas e verificadas como texto, sem compilação ou backtest. |
| Homologação MCP | Bloqueada, gate sem aprovação nesta tarefa | O diagnóstico prévio registra impedimento operacional. Os testes offline verificam somente o pipeline sintético. [Diagnóstico](AUTODEV_START_OFFLINE.md#mcp--diagnóstico-separado-concluído) |

Os dados sintéticos são não certificados. O manifesto registra
`evidence_kind="simulation"`, `live_execution_enabled=false` e
`backtest_performed=false`. Permanecem desconhecidos a compatibilidade
das fontes com o compilador nativo, a paridade do indicador na plataforma
e o comportamento com dados certificados e condições reais de execução.
