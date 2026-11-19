# MT5 Strategy Factory — diagnóstico da instalação Rico

Data: 18/11/2026, contexto America/Sao_Paulo. Investigação local de leitura; única gravação desta etapa: este relatório. Resultados de processos e portas são fotografias do momento da consulta.

## Conclusão

Terminal e MetaEditor da Rico existem, ambos na versão **5.0.0.6230 (build 6230)**. O build supera o piso de introdução do MCP nativo (6060). A pasta de dados associada à instalação foi identificada por `origin.txt`. Nenhum processo Terminal/MetaEditor foi encontrado nas consultas atuais, nem listener TCP em 22345/22346. Não houve conexão MCP, descoberta de ferramentas ou autenticação.

A configuração global inspecionada do Codex contém apenas as seções MCP de `node_repl`; não foi encontrada seção MCP para MT5/MetaEditor. Não existe configuração local `.codex/config.toml` em `C:\estrategia`.

**Próxima etapa depende de autorização:** abrir a instalação correta, confirmar manualmente conta demo e controles de segurança, conferir a configuração MCP e preparar uma conexão limitada à leitura. Nada disso foi ativado aqui.

## Documentos consultados e limites

- Lido `C:\estrategia\INTEGRACAO_MCP_MT5.md`.
- `PESQUISA_ARQUITETURA.md` e `AGENTS.md` não encontrados na busca recursiva, incluindo ocultos, em `C:\estrategia`.
- Reconfirmadas as páginas oficiais de [release do build 6060](https://www.metatrader5.com/en/releasenotes/terminal/2447) e [configuração MCP](https://www.metatrader5.com/en/terminal/help/mcp_and_ai/configuration).
- Conta demo Rico e conta real não habilitada: informações fornecidas pelo usuário. Não foram verificadas por leitura de contas, senhas ou arquivos de configuração.
- Não foram abertos arquivos de contas, configurações internas do MT5, journals ou históricos de ordens. Podem conter dados sensíveis. A inspeção do Codex projetou somente cabeçalhos de seções MCP; não exibiu valores, variáveis de ambiente ou credenciais.

## 1. Caminhos e versões

| Componente | Caminho | Resultado |
|---|---|---|
| Terminal escolhido | `C:\Program Files\Rico - MetaTrader 5\terminal64.exe` | Existe; FileVersion e ProductVersion `5.0.0.6230` |
| MetaEditor correspondente | `C:\Program Files\Rico - MetaTrader 5\metaeditor64.exe` | Existe; FileVersion e ProductVersion `5.0.0.6230` |
| Dados associados | `C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\38FF261A42172F3478E54D3A1A8FE02B` | Existe; `origin.txt` aponta exatamente para a instalação Rico |
| MQL5 da pasta de dados | `C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\38FF261A42172F3478E54D3A1A8FE02B\MQL5` | Diretório identificado; fontes não inspecionados |
| Template da etapa 2 | `C:\estrategia\config\mt5-codex.config.example.toml` | Existe; 1400 bytes; não é configuração ativa do Codex |

Metadados dos executáveis:

| Arquivo | Tamanho em bytes | LastWriteTime retornado pelo Windows |
|---|---:|---|
| terminal64.exe | 121825368 | 30/10/2026 15:54:17 |
| metaeditor64.exe | 116198368 | 30/10/2026 15:54:17 |

O número 6230 aparece no quarto componente da versão, `FilePrivatePart`. `FileBuildPart` retorna 0 e não deve ser confundido com o build comercial do MT5. A identificação foi feita pelos recursos de versão dos arquivos, sem executá-los. Não foi feita auditoria de assinatura/autenticidade nem consulta ao About de aplicativos em execução.

A MetaQuotes documenta a introdução do MCP nativo no **build 6060, de 23/07/2026**. Assim, 6230 é compatível pelo critério de versão de introdução. Isso não comprova permissões, servidor habilitado ou presença de cada ferramenta do catálogo atual. A fonte não fornece mínimo independente do MetaEditor; aqui os dois arquivos têm versão coincidente. [Release oficial](https://www.metatrader5.com/en/releasenotes/terminal/2447)

## 2. Pasta de dados

Evidência direta: o arquivo não sensível `origin.txt` da pasta `38FF261A42172F3478E54D3A1A8FE02B` contém:

```text
C:\Program Files\Rico - MetaTrader 5
```

Foram listados somente os nomes dos subdiretórios: `bases`, `config`, `liveupdate`, `llm-agent`, `logs`, `MQL5`, `temp`, `Tester`. A existência de `llm-agent` não comprova MCP configurado ou ativo. Não há diretório `MQL5` diretamente na pasta de instalação Rico, segundo `Test-Path`.

**Grau de certeza:** associação persistida da instalação à pasta de dados confirmada; uso por uma instância atual não verificável porque nenhum processo foi encontrado. Em futura abertura autorizada, confirmar por `File > Open Data Folder` na janela Rico, sem alterar modo de execução. Um lançamento com modo/caminho diferente pode usar outros dados; não presumir que o mapeamento histórico prova todos os lançamentos futuros.

## 3. Processos, listeners e servidores MCP

| Verificação | Resultado atual |
|---|---|
| Win32_Process: terminal64.exe, terminal.exe, metaeditor64.exe, metaeditor.exe | Nenhuma instância retornada |
| Get-Process para os mesmos nomes | Nenhuma instância retornada |
| Get-NetTCPConnection em estado Listen, portas 22345/22346 | Nenhuma linha retornada, sem erro de acesso |
| netstat TCP filtrado por 22345/22346 | Nenhuma linha retornada |
| Listeners associados aos PIDs de Terminal/MetaEditor encontrados | Nenhum; não havia PIDs correspondentes |
| Servidor MCP habilitado na configuração salva | Pendente de verificação manual |
| Endereço salvo, autenticação exigida e permissões de trading/web/shell | Pendentes de verificação manual |
| Conectividade HTTP/MCP, catálogo e schemas | Não testados |

Não existe listener observado cuja propriedade possa ser atribuída à Rico nesta etapa. Não foi feita requisição HTTP nem tentativa de obter token. A ausência de listener com os aplicativos fechados **não significa** que o MCP esteja desabilitado nas configurações persistidas. Também não descarta um proxy/outro processo em porta alternativa; não foi feito scan de rede.

Os endereços `http://127.0.0.1:22345/mcp` (MetaEditor) e `http://127.0.0.1:22346/mcp` (Terminal) são exemplos oficiais, não valores confirmados da Rico. A MetaQuotes exige endereço exclusivo por aplicativo e documenta autenticação Bearer. [Configuração oficial](https://www.metatrader5.com/en/terminal/help/mcp_and_ai/configuration)

## 4. Configuração atual do Codex

| Caminho/estado | Constatação |
|---|---|
| `C:\Users\User\.codex\config.toml` | Existe |
| Cabeçalhos MCP detectados nesse arquivo | `[mcp_servers.node_repl]`, `[mcp_servers.node_repl.env]` |
| Seção MT5/MetaEditor no arquivo global inspecionado | Não encontrada |
| `C:\estrategia\.codex\config.toml` | Não existe |
| `C:\.codex\config.toml` | Não existe |
| CODEX_HOME alternativo | Nenhum caminho adicional resultou da consulta condicional |
| Catálogo desta sessão | Nenhuma ferramenta MT5/MetaEditor exposta |

Não foi executado `codex mcp list/get`, pois a saída pode incluir configuração sensível. Não foram lidos valores de `.env`, autenticação, `http_headers`, bearer tokens ou conteúdo de tabelas `env`. A projeção de cabeçalhos não revela configurações injetadas por argumentos, política gerenciada, plugins ou outro host da extensão. Por isso a conclusão se limita aos arquivos e ao catálogo desta sessão, sem afirmar ausência universal de configuração em todos os clientes.

O template da etapa 2 permanece um exemplo fora de `.codex`. Não foi copiado, habilitado ou mesclado. Não foi alterado o arquivo global.

## 5. Outras instalações e possíveis conflitos

Verificações de existência encontraram ambos os executáveis `terminal64.exe` e `metaeditor64.exe` nestes caminhos adicionais, sem executá-los ou alterar arquivos:

- `C:\Program Files\MetaTrader 5`
- `C:\Program Files\MetaTrader 5 Terminal`
- `C:\Program Files\Infinox MetaTrader 5 Terminal`
- `C:\estrategia\MT5StrategyFactoryPOC\terminal`

Isso excede as duas outras instalações informadas, pois inclui cópias/variantes; não foi determinado quais duas o usuário considera instalações principais. Todas foram preservadas. Não é necessário resolver essa classificação para manter o alvo Rico inequívoco.

Os registros `origin.txt` também apontam para os hashes de dados `D0E8209F77C8CF37AD8BF550E51FF075` (MetaTrader 5), `FB9A56D617EDDDFE29EE54EBEFFE96C1` (MetaTrader 5 Terminal), `9DE44EFC77A6A3ABBD348AFCCFB49D70` (Infinox) e `2C86162F6CBEDE4F61D93181519680C8` (POC). Existem ainda mapeamentos históricos de runtime de teste e de caminho em D:. Esses registros não provam instâncias ativas ou instalações atuais. A unidade D: não está disponível nesta sessão; nenhuma investigação adicional foi feita nela.

Riscos para a futura conexão:

1. Duas instâncias podem disputar 22345/22346. **Não há conflito ativo observado agora**, mas é necessário repetir a identificação de PID e ExecutablePath imediatamente antes da conexão.
2. Um endpoint configurado no Codex pode apontar para a instância errada se outro aplicativo ocupar a mesma porta. Validar propriedade do listener e, depois, workspace retornado; nome do servidor no Codex não autentica a instalação.
3. Abrir `metaeditor64.exe` pelo PATH, associação de arquivos ou atalho genérico pode selecionar outra distribuição. Usar somente o caminho absoluto Rico, quando houver autorização para abrir.
4. Configuração global do Codex pode disponibilizar ferramentas em outros projetos. Preferir configuração de projeto dedicada na futura ativação, começando apenas com consulta de workspace.
5. Conta demo não isola arquivos MQL5. Não habilitar ferramentas de escrita, compilação ou teste na primeira conexão.

## 6. Procedimento mais seguro para a primeira conexão — não executado

1. Obter autorização específica para abrir Terminal/MetaEditor Rico e para as alterações de configuração que forem necessárias. Não iniciar ou encerrar outras instalações.
2. Abrir somente os executáveis pelos caminhos absolutos confirmados. Conferir manualmente conta demo Rico, ausência de conta real e pasta de dados. Não registrar números de conta ou capturas com credenciais.
3. Conferir `Tools > Options > AI Assistant`: trading proibido, web bloqueado, shell perigoso desabilitado. Se algo precisar mudar, aplicar somente com autorização. Não confiar apenas em Algo Trading desativado.
4. Conferir `Tools > Options > MCP` em cada aplicativo, sem exportar tokens para a conversa. Confirmar loopback, endereço exclusivo e autenticação exigida. Ativar/alterar servidor apenas sob autorização. Não criar regras de firewall, proxies ou túneis.
5. Repetir consulta de listeners e resolver cada PID com `Get-Process -Id <PID> | Select-Object Id,ProcessName,Path` ou `Win32_Process`. Exigir caminho exato Rico para cada processo. Se a porta pertencer a outro aplicativo, parar e relatar; não encerrar o outro aplicativo nem escolher porta automaticamente.
6. Preparar configuração Codex **somente após aprovação**, por projeto, sem sobrescrever configurações existentes. Usar URL realmente conferida e permitir inicialmente só `get_workspace_info`, com os tokens inseridos privadamente pelo usuário. O agente não deve acessar os tokens nesta etapa de diagnóstico.
7. Autorizar separadamente a primeira conexão e consulta de workspace. Confirmar que os caminhos retornados correspondem à Rico e ao hash de dados identificado. Se houver divergência, interromper a conexão; não compilar, escrever ou negociar para testar identidade.
8. Somente depois considerar etapa separada de descoberta de catálogo e homologação. O presente relatório não autoriza backtests, otimizações, modificações MQL5 nem ordens demo/reais.

Pendências manuais: conta demo atual, About dos aplicativos, pasta de dados da futura execução, estado/configuração MCP persistida, controles de segurança, autenticação e configuração efetiva do cliente escolhido. Não se justifica atualizar o software apenas para atingir o piso MCP: o build dos arquivos já supera 6060.

## 7. Comandos utilizados e resultados relevantes

Os comandos foram executados sem elevação. Abaixo estão as consultas realizadas, com agrupamentos e projeções equivalentes às usadas na sessão; não há comandos de ativação. Variáveis representam apenas caminhos e metadados não sensíveis.

```powershell
Get-Content -LiteralPath C:/estrategia/INTEGRACAO_MCP_MT5.md
Get-ChildItem -LiteralPath C:/estrategia -Filter PESQUISA_ARQUITETURA.md -File -Recurse -Force
Get-ChildItem -LiteralPath C:/estrategia -Filter AGENTS.md -File -Recurse -Force
```

Resultado: guia disponível; os dois nomes pesquisados não retornaram arquivos. A leitura inicial do guia pelo Windows PowerShell apresentou caracteres UTF-8 como mojibake na saída; isso não indica modificação do documento.

```powershell
$paths = @(
  'C:\Program Files\Rico - MetaTrader 5\terminal64.exe',
  'C:\Program Files\Rico - MetaTrader 5\metaeditor64.exe'
)
foreach ($p in $paths) {
  Test-Path -LiteralPath $p
  $f = Get-Item -LiteralPath $p
  $f.VersionInfo | Select-Object FileVersion,ProductVersion,FileMajorPart,
    FileMinorPart,FileBuildPart,FilePrivatePart
}
Get-CimInstance Win32_Process -Filter "Name='terminal64.exe' OR Name='metaeditor64.exe' OR Name='terminal.exe' OR Name='metaeditor.exe'" |
  Select-Object ProcessId,Name,ExecutablePath
Get-Process -Name terminal64,metaeditor64,terminal,metaeditor -ErrorAction SilentlyContinue |
  Select-Object Id,ProcessName,Path
```

Resultado: ambos arquivos presentes, versão 5.0.0.6230; nenhuma instância correspondente retornada. A consulta composta que terminava em `Get-Process` retornou código 1 por não encontrar esses nomes, sem solicitar elevação.

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 22345,22346 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
$ps = Get-Process -Name terminal64,metaeditor64,terminal,metaeditor -ErrorAction SilentlyContinue
$ids = @($ps.Id)
Get-NetTCPConnection -State Listen |
  Where-Object { $_.OwningProcess -in $ids } |
  Select-Object LocalAddress,LocalPort,OwningProcess
netstat -ano -p tcp | Select-String -Pattern ':22345\s',':22346\s'
```

Resultado: nenhuma linha relevante; não houve erro de acesso na consulta de sockets.

```powershell
$base = Join-Path $env:APPDATA 'MetaQuotes\Terminal'
Get-ChildItem -LiteralPath $base -Directory | ForEach-Object {
  $o = Join-Path $_.FullName 'origin.txt'
  if (Test-Path -LiteralPath $o) {
    [pscustomobject]@{
      DataDirectory = $_.FullName
      Origin = (Get-Content -LiteralPath $o -Raw).Trim()
    }
  }
} | ConvertTo-Json
$d = Join-Path $base '38FF261A42172F3478E54D3A1A8FE02B'
Get-Item -LiteralPath $d | Select-Object FullName,LastWriteTime
Get-ChildItem -LiteralPath $d -Directory | Select-Object -ExpandProperty Name
Test-Path -LiteralPath 'C:\Program Files\Rico - MetaTrader 5\MQL5'
```

Resultado: origem Rico confirmada, oito subdiretórios listados; último `Test-Path` retornou False. Foram feitas consultas adicionais de existência dos executáveis nos quatro caminhos relacionados na seção 5. Uma tentativa de pipeline após `foreach` teve erro de sintaxe antes da execução; foi corrigida armazenando os resultados em variável. A consulta ao caminho histórico D: retornou unidade inexistente; não foi tratada como instalação ausente comprovada.

```powershell
$paths = @(
  'C:\Users\User\.codex\config.toml',
  'C:\estrategia\.codex\config.toml',
  'C:\.codex\config.toml'
)
if ($env:CODEX_HOME) { $paths += Join-Path $env:CODEX_HOME 'config.toml' }
foreach ($p in ($paths | Select-Object -Unique)) {
  [pscustomobject]@{ConfigPath=$p; Exists=(Test-Path -LiteralPath $p)}
  if (Test-Path -LiteralPath $p) {
    Select-String -LiteralPath $p -Pattern '^\s*\[.*mcp_servers.*\]\s*$' |
      ForEach-Object { $_.Line.Trim() }
  }
}
Get-Item -LiteralPath C:/estrategia/config/mt5-codex.config.example.toml |
  Select-Object FullName,Length
```

Resultado: somente global existente; cabeçalhos node_repl e node_repl.env. Nenhum valor sensível foi incluído na saída ou neste relatório. Não houve leitura de conteúdo de configurações MT5 para descobrir MCP.

## Estado final

Diagnóstico concluído. Nenhum processo MT5/MetaEditor iniciado ou encerrado; nenhuma configuração alterada; nenhum programa instalado; nenhuma compilação, backtest, chamada MCP ou envio de ordem. As demais instalações e todos os arquivos MQL5 foram preservados. Aguardar autorização antes da ativação/conexão.
