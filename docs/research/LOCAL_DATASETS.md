# Dados locais de pesquisa

`load_dataset(path, *, symbol="PETR4", period="M5", timezone_label="unknown", expected_sha256=None)`
carrega um snapshot sintético PETR4 M1 ou M5 autorizado pelo chamador.
O manifesto de entrada `ApprovedDataset` declara o arquivo, o SHA-256 aprovado
dos bytes originais, a origem sintética, o período e o fuso. Use o contexto
`approved_dataset` para limitar a autorização a uma chamada ou bloco.

```python
from strategy_factory.research import ApprovedDataset, approved_dataset, load_dataset

source = ApprovedDataset(
    path=approved_path,
    sha256=approved_sha256,
    origin="fixture sintética PETR4",
)
with approved_dataset(source):
    result = load_dataset(source.path)
```

Os caminhos relativos partem da raiz do projeto. A entrada deve estar em
`tests/fixtures/research` ou `artifacts/offline`. Cada leitura requer
correspondência de caminho com o manifesto e com o destino resolvido. A
verificação do SHA-256 usa os mesmos bytes que o carregador interpreta.

- CSV UTF-8, com BOM opcional, cabeçalho exato
  `time,open,high,low,close,tick_volume,volume,spread`, vírgula como separador
  e ponto decimal. Os campos numéricos usam dígitos com fração opcional.
- JSON UTF-8, com BOM opcional, no formato snapshot, com `ok: true`,
  `symbol`, `period` e `history`. Cada barra tem os campos do CSV como
  propriedades, com valores numéricos JSON. Origem ou fuso declarados
  no JSON devem coincidir com o manifesto de entrada.
- `time` usa ISO 8601 com segundos e alinhamento à grade M1 ou M5.
  `unknown` preserva o relógio declarado pela fonte. `UTC` exige offset
  zero e `explicit_offsets` exige offset em cada barra. Cada arquivo
  usa um único offset ou timestamps sem offset.

O retorno contém `snapshot`, `audit` e `manifest`. O snapshot mantém a
ordem das barras e os timestamps de entrada. A auditoria rejeita reversões
e duplicatas conflitantes e registra lacunas observadas. O manifesto de
saída registra a exposição sintética do primeiro ao último dia observado
na base temporal da auditoria, com limite final exclusivo e vínculo ao
SHA-256 da fonte. O horário de revisão corresponde à geração do
manifesto. A cobertura permanece `observed_partial`, a certificação
`unverified` e a execução desabilitada.
