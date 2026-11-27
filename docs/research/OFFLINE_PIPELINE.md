# Pipeline sintético offline

Execute na raiz do checkout ou do espelho:

```console
python -B -m strategy_factory.research.cli --config config/research/pipeline.example.json --output-root artifacts/offline/meu-run-novo
```

Sem argumentos, o comando usa a configuração de exemplo e gera um ID único.
A API recebe o dicionário da configuração ou o caminho do JSON em
`run_pipeline(config, output_root=...)`. O exemplo declara os caminhos
das fixtures versionadas e da grade em relação à raiz do checkout.
O diretório é criado de forma
exclusiva e o manifesto concluído também é retornado como dicionário.

O pipeline audita a fixture de barras, expande a grade de exemplo e grava
especificações normalizadas e fontes de candidatos `source_only`. O
`report.json` explica a auditoria e apresenta a comparação de resumos
sintéticos preexistentes. Esses resumos ilustram os critérios de comparação.
Nenhum resultado é atribuído aos candidatos gerados. O manifesto registra
`evidence_kind="simulation"`, `live_execution_enabled=false` e
`backtest_performed=false`, além dos metadados dos candidatos e do nome
do relatório.

O plano usa um trabalhador, limita os arquivos de entrada a 128 KiB por
arquivo e respeita o teto do gerador de 32 candidatos. A configuração de
exemplo gera oito candidatos. O SHA-256 das fixtures é validado com
quebras de linha normalizadas. O manifesto registra o hash dos bytes
efetivamente lidos, além dos hashes da configuração canônica, da grade,
das especificações, das fontes e do relatório. O campo `content_sha256`
reproduz o mesmo valor para as mesmas entradas. O horário de conclusão
fica em `audit`, fora do conteúdo determinístico.

A ausência de `manifest.json` identifica uma execução incompleta. Depois
de publicado, `checkpoint.json` fixa as entradas e os hashes previstos.
Para retomar, use a mesma configuração e o diretório original:

```console
python -B -m strategy_factory.research.cli --resume --config config/research/pipeline.example.json --output-root artifacts/offline/meu-run-novo
```

A retomada verifica o checkpoint e os artefatos publicados antes de gravar
os arquivos faltantes. Um bloqueio local impede duas gravações simultâneas
no mesmo run e é liberado quando o processo encerra. Uma nova chamada com
`--resume` verifica também um run concluído. Arquivos de preparação
deixados por encerramento abrupto ficam fora do manifesto. Se a interrupção
ocorrer antes da publicação do checkpoint, use um novo ID para preservar
o diretório incompleto.
