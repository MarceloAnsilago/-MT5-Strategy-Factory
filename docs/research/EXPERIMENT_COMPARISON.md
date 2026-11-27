# Comparação offline de experimentos

`strategy_factory.research.experiment_comparison.compare_experiments(summaries)`
recebe resumos `run_summary` 1.1 e devolve um dicionário com `ranked`,
`criteria`, `excluded`, `pairs` e `live_execution_enabled` (sempre falso).
Uma coleção vazia devolve `ranked=[]`. Resumos malformados, identidades
duplicadas e números não finitos causam `ValueError` ou `TypeError`.

A elegibilidade exige execução concluída, reconciliação verificada,
contexto completo e rastreabilidade confirmada. A comparação entre
experimentos reutiliza `analysis.compare_runs`. Se algum par elegível
divergir em cenário, dados, período, modelo, custos ou tipo de evidência,
a coleção elegível fica sem ranking. Veja `pairs` e `excluded` para os
motivos.

O ranking usa o lucro líquido explicitamente atribuído a `out_of_sample`
em `period_results`, com pelo menos uma negociação informada. Maior valor
vem primeiro e a identidade do resumo desempata em ordem crescente.
O rótulo de período vem do resumo. O esquema 1.1 não fornece limites
independentes para cada linha de período. Resultados agregados e
`final_test` ficam fora dos critérios. Campos opcionais desconhecidos
mantêm o valor nulo.

A comparação é descritiva. Cada linha preserva seu `evidence_kind`.
Margem permanece desconhecida neste contrato e a promoção fica
desabilitada. Os resumos da fixture são sintéticos, inclusive os marcados
como concluídos.
