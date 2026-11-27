# Pesquisa sintética offline

Na raiz do checkout ou do espelho, execute com Python 3.11. O exemplo usa
somente as fixtures sintéticas versionadas e dispensa aplicativos MCP.

```console
python -B -m examples.research_offline
```

O mesmo exemplo pode ser executado diretamente com
`python -B examples/research_offline.py`.

O exemplo usa um trabalhador, expande a grade de oito candidatos com teto
de 32 e cria uma pasta nova em `artifacts/offline/sf-o06-example-<id>`.
A saída JSON no terminal informa a pasta, o hash do plano, o tempo em
segundos medido durante o pipeline e os tamanhos em bytes por arquivo.
Uma execução registrou 0,093 s e 97.062 bytes em 20 arquivos, incluindo o
arquivo de bloqueio vazio. São medidas dessa execução.

A CLI pública também gera uma pasta nova automaticamente. A configuração
padrão adota o limite de oito candidatos.

```console
python -m strategy_factory.research.cli
```

Para executar a mesma CLI com a gravação de bytecode desabilitada, use
`python -B -m strategy_factory.research.cli`. O teste de ponta a ponta
pode ser executado na raiz do espelho com:

```console
python -B -m unittest discover -s tests -p test_research_offline_e2e.py -v
```

| Saída | Origem e verificação |
| --- | --- |
| `*.spec.json` | Especificação normalizada de cada candidato derivado de `config/research/candidate_grid.example.json`. O catálogo vincula ID, arquivo e SHA-256. |
| `*.mq5` | Fonte MQL5 renderizada da especificação pelo gerador público. O candidato registra hashes da fonte e do template, status `source_only` e `compiled_sha256: null`. |
| `report.json` | Auditoria de `local_bars_synthetic.csv`, catálogo e comparação de `summaries_synthetic.json`, ambas as fixtures em `tests/fixtures/research/`. Os resultados da comparação pertencem aos resumos sintéticos preexistentes. |
| `checkpoint.json` | Plano inicial com entradas, limites, catálogo e hashes previstos. Seu status `incomplete` identifica a etapa de preparação, inclusive após a publicação do manifesto final. |
| `manifest.json` | Confirma a conclusão da geração offline. `input_sha256` cobre configuração canônica, grade e fixtures. `artifact_sha256` cobre especificações, fontes e relatório. `content_sha256` cobre o plano canônico. O horário de auditoria fica fora desse hash. |
| `.run.lock` | Arquivo de coordenação local para escrita e retomada. A trava é liberada quando o descritor fecha. |

Com as mesmas entradas e configuração, repita o exemplo e compare
`content_sha256` e os hashes dos artefatos. O E2E recalcula esses hashes,
reproduz as fontes pelo gerador e testa a recusa de uma fonte adulterada.
O E2E chama o ponto de entrada real `examples.research_offline.main(output_root=...)`
no mesmo processo Python, captura o JSON e usa diret?rios tempor?rios exclusivos
em `artifacts/offline/`, removidos ao terminar. N?o abre subprocessos nem usa mocks.
As duas execu??es verificam a reprodu??o do conte?do.
Consulte [RESEARCH_STATUS.md](RESEARCH_STATUS.md) para o estado da validação.
