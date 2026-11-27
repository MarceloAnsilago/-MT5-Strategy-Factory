# Catálogo de candidatos offline

`build_catalog(specifications, *, limit=32)` aceita um iterável de especificações e devolve uma lista de metadados do gerador. A lista preserva a ordem da primeira ocorrência e elimina candidatos com o mesmo ID, hash da especificação ou hash da fonte. Cada registro inclui `status="source_only"`, o nome e o SHA-256 da fonte MQL5 e `compiled_sha256=None`.

`expand_grid(base, axes, *, limit=32)` devolve especificações normalizadas e validadas. Cada eixo é um caminho pontuado para um campo existente na base, com índices de lista começando em zero. Por exemplo, `entries.long.1.slow` seleciona o período lento da segunda regra de entrada compradora. Um eixo também pode substituir uma cláusula inteira. Use listas de valores não vazias e caminhos sem sobreposição.

A grade percorre os eixos em ordem lexicográfica e mantém a ordem dos valores de cada eixo. Os índices referem-se à ordem das regras na base fornecida. Valores JSON idênticos dentro de um eixo contam uma vez. O produto deve caber no limite antes da expansão, e as especificações equivalentes após normalização aparecem uma vez. Uma grade sem eixos valida e devolve a base. No catálogo, o limite se aplica aos registros distintos.

Ambas as APIs exigem um limite inteiro entre 1 e 32 e rejeitam especificações inválidas pelo validador do gerador. O gerador mantém o limite de cinco regras por cláusula e 16 handles por candidato, o volume mínimo fixo e as restrições de risco. A normalização do gerador preserva o ID e a fonte ao reordenar chaves e regras equivalentes.

```python
import json
from pathlib import Path

from strategy_factory.research.candidate_catalog import build_catalog, expand_grid

example = json.loads(
    Path("config/research/candidate_grid.example.json").read_text(encoding="utf-8")
)
catalog = build_catalog(expand_grid(**example))
```

O exemplo combina MA, RSI e ADX em oito candidatos. As APIs operam em memória. Se um consumidor autorizado persistir os dados de pesquisa, deve usar um novo diretório em `artifacts/offline/`.
