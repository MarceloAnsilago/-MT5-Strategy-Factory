# Fase 3.1 — gerador determinístico de candidatos MQL5

O módulo `strategy_factory/generator.py` transforma especificações JSON em EAs
independentes. Não chama compilador, Tester, rede ou serviços externos. Uma
linguagem restrita de regras e um template MQL5 revisável substituem qualquer
entrada de código livre. Os módulos anteriores e os EAs existentes não foram alterados.

## Arquitetura e identidade

1. Validar todos os candidatos de uma solicitação antes de gravar artefatos.
2. Normalizar números e ordenar regras AND, removendo dependência da ordem das
   chaves/condições para a identidade.
3. Gerar `candidate_id=g1_<16 primeiros hex do SHA256 da especificação canônica>`.
4. Renderizar `templates/candidate_v1.mq5.in`, versão de gerador **1.0.0**.
5. Registrar SHA256 completo da especificação, do template e dos bytes do fonte.
6. Reservar identidades em SQLite e criar diretório/arquivos exclusivamente,
   sem sobrescrever geração ou histórico existente.

Não há datas, nomes de usuário ou caminhos locais no fonte gerado. Bytes do EA
são UTF-8/LF; `.gitattributes` mantém LF nos fontes gerados e no template mesmo
em checkouts Windows. O código é reprodutível com a mesma especificação,
template e versão; isso não promete EX5 idêntico entre builds/ambientes do compilador.

Cada diretório contém `spec.json`, `candidate.json` e um `.mq5`. O registro padrão
fica em `runs/candidate_registry.sqlite`, fora do Git, com reservas, conclusões e
falhas. A geração grava o fonte em bytes e depois verifica seu conteúdo integral.
Uma falha preserva os parciais e reservas; não há retry, limpeza ou reparação
automática que possa substituir provas anteriores.

Duplicação é detectada por especificação canônica no registro compartilhado e
na solicitação. Não é um provador de equivalência matemática: regras diferentes
que produzam sinais equivalentes não são necessariamente detectadas. Colisões
do identificador curto são bloqueadas pela unicidade do registro; o hash completo
permanece nos metadados. Usar outro registro remove a deduplicação entre registros,
por isso mantenha o registro padrão para o histórico real do projeto.

## Especificação 1.0

Raiz: `schema_version`, `symbol`, `timeframe`, `entries`, `exits` e `risk`.
`entries`/`exits` contêm listas `long` e `short`. Todas as regras de uma lista
devem ser verdadeiras (AND). Lista de entrada vazia desabilita o lado; lista
de saída vazia deixa SL/TP e limite de barras como saídas. Um lado inativo não
pode ter regras de saída. Consulte `config/generator/demo_specs.json` para exemplos completos.

| Regra | Parâmetros e significado |
|---|---|
| `ma_cross` | `fast`, `slow`, `method`, `direction=above/below`: cruzamento nos dois candles fechados |
| `price_ma` | `period`, `method`, `relation=above/below`: fechamento contra a média do último candle fechado |
| `ma_trend` | `fast`, `slow`, `method`, `direction=up/down`: alinhamento das médias e inclinação da média lenta |
| `rsi_level` | `period`, `level`, `relation=above/below`: condição de nível, incluindo sobrecompra/sobrevenda |
| `rsi_cross` | `period`, `level`, `relation=above/below`: cruzamento de nível nos candles fechados |
| `adx_strength` | `period`, `minimum`, `maximum`: ADX dentro de intervalo inclusivo |
| `adx_direction` | `period`, `minimum`, `direction=up/down`: força mínima e relação entre +DI/−DI |

Métodos MA suportados: EMA e SMA, sempre `PRICE_CLOSE`. RSI usa `PRICE_CLOSE`.
ADX usa buffer principal, +DI e −DI. Os dados vêm de shifts 1 e 2: fisicamente o
elemento `[0]` é o mais antigo e `[1]` o mais recente. O candle aberto só agenda
a avaliação por `iTime(...,0)`; seu preço não entra no sinal.
Referências: [iADX](https://www.mql5.com/en/docs/indicators/iadx),
[CopyClose](https://www.mql5.com/en/docs/series/copyclose).

Os parâmetros ficam como **constantes compiladas**, não inputs MQL5 ajustáveis.
Assim, modificar períodos/limiares/risco gera nova identidade, novo fonte e exige
nova compilação. O manifesto usa `inputs={}`; a especificação completa é o registro
dos parâmetros. Logs `FACTORY INIT` incluem ID e hash da especificação, mas não
são automaticamente promovidos a confirmação nativa pela análise da Factory.

## Limites e validação

- Até **32 candidatos por solicitação**, padrão 16; `--limit` pode reduzir o teto.
- Até cinco regras por lista, 16 handles únicos; handles de indicadores iguais
  são reutilizados dentro do EA.
- MA: períodos inteiros de 2 a 500, `fast < slow`; RSI/ADX: 2 a 100.
- RSI: níveis de 1 a 99; ADX: 0 a 100, intervalo mínimo menor que máximo.
- Valores reais limitados a seis casas decimais, sem NaN/Infinity ou booleanos numéricos.
- SL: maior que zero e até 20%; TP: maior que zero e até 50%.
- Spread máximo: 0 a 1000 pontos; `null` desativa o filtro, não declara custo zero.
- Até 1000 entradas e 1000 barras avaliadas por posição; desvio de 0 a 100 pontos.

Rejeita campos/regras desconhecidos, código arbitrário, regras duplicadas,
direções incompatíveis, intervalos RSI/ADX impossíveis e entradas long/short
idênticas. Combinações parcialmente sobrepostas podem gerar ambos os sinais;
o EA ignora esse conflito em runtime. A validação não garante relevância econômica,
frequência de operações, rentabilidade ou ausência de redundâncias mais complexas.

## Restrições do EA

`OnInit` verifica `MQL_TESTER` e recusa `MQL_OPTIMIZATION` antes de criar indicadores
ou configurar CTrade. Os mesmos bloqueios são repetidos no `OnTick` e em todas
as funções que podem enviar requisições. Exige símbolo/timeframe do JSON.
O EA não deve ser anexado ao terminal operacional, mesmo com os bloqueios.

Volume sempre `SYMBOL_VOLUME_MIN`, sem progressão, martingale, grid, posições
simultâneas, pirâmide ou ordens pendentes intencionais. Valida passo/volume,
cotação positiva, spread, tick size, distância de stops, margem e tipo de filling.
Usa SL/TP ajustados para fora ao tick. Não fecha e abre no mesmo candle.
Confere símbolo/magic antes de fechar uma posição. Não negocia no `OnDeinit`.

Rejeição, execução parcial ou estado inesperado interrompe novas requisições,
sem retry. Uma exposição residual pode permanecer protegida apenas por SL/TP e
pelo encerramento final do Tester. Stops não garantem perda máxima em gaps.
O limite de duração conta barras avaliadas com buffers disponíveis; falhas de
dados podem atrasar saídas de sinal e essa contagem. O código não substitui um
watchdog independente. Vendas de PETR4 dependem de permissões, margem e regras
do ambiente; compilar não comprova que serão executáveis.

## Gerar, verificar e integrar

```powershell
python -m strategy_factory.generator generate config/generator/demo_specs.json --limit 3
python -m strategy_factory.generator verify MQL5/Experts/MT5StrategyFactory/Generated/ID
python -m unittest discover -s tests -v
```

Os três demos já estão registrados no workspace; repetir sua geração no mesmo
registro será bloqueado, como previsto. Para outro candidato, crie uma nova
especificação. Em um clone novo, os fontes versionados já existem e não serão
sobrescritos; verifique-os antes de planejar uma nova geração. Registros SQLite
locais não são distribuídos pelo Git.

`audit_candidate` executa verificação estática após a verificação integral dos
bytes. É um checklist da forma fixa do template, não uma prova formal de segurança.
Compilar pelo MCP é uma ação separada que requer a revisão do código/guardas.
O gerador não compila nem inicia testes implicitamente.

`manifest_strategy` liga ID, versão e hash do fonte ao manifesto 1.0 existente;
o hash do EX5 é argumento separado, nunca inferido do fonte. `attach_candidate`
acrescenta identidade ao resumo 1.1 preservando métricas e estados desconhecidos,
com proveniência explícita `generated_artifacts_not_runtime_confirmation`.
O contexto de lote existente também mantém ID/versão/hashes declarados.

`config/generator/demo_manifest.json` contém os três IDs/fontes/hashes compilados,
com caminhos **fictícios** `C:\MT5-LAB` e orçamento para planejamento. Validar esse
arquivo não comprova caminhos existentes, histórico ou custos e não concede
autorização. O backend real de lotes continua desabilitado.

## Três candidatos produzidos

| ID | Regras | Fonte |
|---|---|---|
| `g1_ff2190c4549a31aa` | Compra no cruzamento EMA 9/21, ADX 14 entre 20 e 60; saída no cruzamento inverso; SL 1%, TP 2% | `MT5SF_G_ff2190c4549a31aa.mq5` |
| `g1_fcb7f99b53c86641` | RSI 14 cruza acima de 30 para compra ou abaixo de 70 para venda, com ADX até 25; saídas RSI acima de 60/abaixo de 40; SL 1%, TP 1,5% | `MT5SF_G_fcb7f99b53c86641.mq5` |
| `g1_a7e690b3b483dde0` | Preço/EMA 20, alinhamento e inclinação EMA 20/50, RSI acima de 55/abaixo de 45 e ADX direcional ≥25; saída por preço/EMA; SL 1,2%, TP 2,4% | `MT5SF_G_a7e690b3b483dde0.mq5` |

Todos são PETR4/M5, com volume mínimo e spread máximo de 10 pontos. Os fontes,
especificações e metadados ficam em `MQL5/Experts/MT5StrategyFactory/Generated/ID/`.

Compilações separadas pelo MetaEditor Rico, build 6230, AVX2 + FMA3:
**0 erros e 0 avisos nos três candidatos**. Tempos observados: tendência 518 ms,
RSI 487 ms, cruzamento 491 ms. Fontes copiados foram relidos antes da compilação.
Os EX5 e logs completos ficam somente na instalação MT5/`runs/phase31_compilation/`.
Hashes binários foram calculados em leitura local, restrita aos novos diretórios
permitidos pelo workspace MCP, pois `read_file` retornou apenas cabeçalho textual
do binário. Não foram acessadas credenciais ou outros executáveis.

Os metadados imutáveis da geração conservam `compiled_sha256=null`, pois representam
o estágio de geração. As evidências posteriores de compilação e hashes binários
são registros separados; o manifesto de demonstração recebe os hashes disponíveis.
Um EX5 recompilado pode mudar de hash: atualizar o plano exigirá novo hash e nova
aprovação, sem sobrescrever evidência anterior.

Validação: **158 testes Python aprovados**, incluindo determinismo, normalização,
duplicações, limites, contradições, criação exclusiva, falhas parciais, hashes,
guardas, candles fechados e integração com manifesto/resumo. Nenhum backtest,
otimização ou ordem foi executado. Não existem resultados de desempenho desses EAs.

## Antes dos primeiros backtests

Selecionar cenário e candidato, conferir o EX5/hash, capacidades do ativo
(especialmente vendas), parâmetros compilados, histórico, custos, agentes locais
e orçamento. Apresentar manifesto/hash e limitações para autorização explícita
de uma tentativa controlada. O backend real de lotes e a coleta completa de
rastreabilidade continuam pendentes. Esta entrega não inicia a Fase 3.2 e não
autoriza nenhum teste das estratégias geradas. Um primeiro teste individual
poderá reutilizar `TesterRunner` após preflight e autorização; não é necessário
habilitar lotes para isso, e nenhum caminho automático novo até o Tester foi criado.
