# Revisão do primeiro backup — 19/11/2026

Proposta para revisão, sem stage, commit ou push. Visibilidade remota consultada: pública. As listagens correspondem aos arquivos existentes nesta inspeção; repetir a revisão se houver mudanças.

Foram conferidos os hashes de todos os arquivos preexistentes do workspace fora de `.git/` e `.codex/`: nenhum foi alterado. Fontes e configurações copiados da Rico foram comparados por SHA256 com seus originais. Os detalhes de origem e a lista completa dos arquivos excluídos ficam em `auditoria-local/REVISAO_COMPLETA.md`, somente local, pois os caminhos excluídos podem revelar identificadores de conta.

Os candidatos textuais foram decodificados incluindo UTF-16 e examinados para tokens GitHub/OpenAI/AWS, chaves privadas, credenciais literais, Bearer literal, emails e identificadores de conta encontrados no ambiente excluído. Nenhuma ocorrência desses padrões foi identificada. Referências documentais a tokens e nomes de variáveis não são valores de autenticação. Os oito PNGs foram inspecionados visualmente e mostram gráficos dos testes, sem identificador de conta visível. Os HTMLs contêm transações simuladas dos testes, símbolos e nomes de empresas/servidores demo; esses dados fazem parte das evidências propostas. Permanecem caminhos locais de instalação na documentação histórica. Revisão por padrões não garante ausência universal de segredos.

## Lista exata proposta para envio

- `.gitignore` — 1865 bytes; SHA256 `84a895e0b9a574a59396d2ef98d7263d2a4962387e18d206ec895b2e0ef4990e`
- `DIAGNOSTICO_MT5_RICO.md` — 16580 bytes; SHA256 `9255b9103de7fd7c5be90fb3fead293e3d1d8f3e0fee19af11347fd532191a69`
- `ESTADO_DO_PROJETO.md` — 4622 bytes; SHA256 `4edc7bbeb5e01ef061e34416093533ea5e4b796a091434588a3f0deeef3297bf`
- `INTEGRACAO_MCP_MT5.md` — 24944 bytes; SHA256 `b5ef0db354c1da10c8da54b1b2d937f33621459b868e8352325cbd9061bed362`
- `MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.mq5` — 84249 bytes; SHA256 `d98154e180c1e707469003fffd85357aa7ac10cfa510a4990da13a3ea7eae9af`
- `MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.v1.00_pre_protecoes_20261118_001.mq5.bak` — 16172 bytes; SHA256 `1a8db8052d4ea6b6736198e4ba3a941c68e5d16ad3f47f0ae28d9e79f91c1807`
- `MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.v1.10_pre_v1.20_001.mq5.bak` — 35323 bytes; SHA256 `aada1be8171caf1e946645f7155ee4b141be74dc8241e79a752bf40e4099f5ad`
- `MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.v1.20_pre_v1.21_001.mq5.bak` — 55880 bytes; SHA256 `4b76f8c4106d1d38ec729b3b3b2ab1601842af0b38969e8a9256efdc26ab60df`
- `MQL5/Experts/MT5StrategyFactory/Estrategia_001/MT5SF_Estrategia_001.v1.21_pre_v1.22_001.mq5.bak` — 59920 bytes; SHA256 `28149581515aaaea57a974bcaff7e33b55de1d30a18020a152f522d78ce4960e`
- `MQL5/Experts/MT5StrategyFactory/Homologacao_001/MT5SF_Homologacao_001.mq5` — 386 bytes; SHA256 `78bd1d4b04ebe2805738081a193148df2a8bc2777820f27fc27b7a2eb3f6d22c`
- `MT5StrategyFactoryPOC/CONTINUACAO.md` — 2689 bytes; SHA256 `283484cba83f9dc77147bf43dd62b4d1aa64207d79471d19afd0cab27ed9c771`
- `MT5StrategyFactoryPOC/PETR4/PETR4_EMA_M15_POC.mq5` — 2943 bytes; SHA256 `8013b104a75ce663dc08d03159499f7f9a016fcaa68803b85d36c70f51aa4966`
- `MT5StrategyFactoryPOC/PETR4/RESULTADO_PETR4.md` — 2468 bytes; SHA256 `9a355c4cd7bd264722dc7ae217c5c1858b0d4fc1964adfe72e30eec0b6bd025b`
- `MT5StrategyFactoryPOC/PETR4/reports/PETR4_EMA_M15_2025Q1_Rico-holding.png` — 11401 bytes; SHA256 `32e379cbd835ab52007a20d261f8d920281ceba9472a0c35f1829b0e946931b0`
- `MT5StrategyFactoryPOC/PETR4/reports/PETR4_EMA_M15_2025Q1_Rico-hst.png` — 26400 bytes; SHA256 `d69a716db455a21cf72b14afc81dd79f496e43afa6e4f6bd5a2c51ff85fa0e2e`
- `MT5StrategyFactoryPOC/PETR4/reports/PETR4_EMA_M15_2025Q1_Rico-mfemae.png` — 26249 bytes; SHA256 `4f4ea82d9adf0f07ccc24957a5ad378e914f655f37b526c7fb5379aeb38fa361`
- `MT5StrategyFactoryPOC/PETR4/reports/PETR4_EMA_M15_2025Q1_Rico.html` — 188806 bytes; SHA256 `e031982e20af6612a1ea4c53c0926ec4df44e5085795c61de34e77e30e8a67f1`
- `MT5StrategyFactoryPOC/PETR4/reports/PETR4_EMA_M15_2025Q1_Rico.png` — 8682 bytes; SHA256 `323f669fd391f1c01b59680632b231e9eef3baad4ccd35c38a90bacf4e64b775`
- `MT5StrategyFactoryPOC/PETR4/tester-petr4.ini` — 556 bytes; SHA256 `eb33ca3bf67c03c7e5aebdf8cb8793e99a142b316dd2f9b3e4854a3d465dc5ad`
- `MT5StrategyFactoryPOC/RESULTADO.md` — 3178 bytes; SHA256 `ec8ae6ec121d179ceb9a423bf6b0a9efe1e30ccd96797b2279c3db679f5fd393`
- `MT5StrategyFactoryPOC/reports/EMA_EURUSD_M15_2025Q1-holding.png` — 15999 bytes; SHA256 `911f9f6853108298218c43de811489907e4dd0a8fd5390790c39b1030bc8e8e6`
- `MT5StrategyFactoryPOC/reports/EMA_EURUSD_M15_2025Q1-hst.png` — 32514 bytes; SHA256 `00a689f4f186bbf097121cbff5cd7b30eb7f93805b3a7b13c21eed55e8f9d292`
- `MT5StrategyFactoryPOC/reports/EMA_EURUSD_M15_2025Q1-mfemae.png` — 32776 bytes; SHA256 `f04ebeb9e849762350813aa2575a6902021e5b6064f70f9596a427b20e555bb0`
- `MT5StrategyFactoryPOC/reports/EMA_EURUSD_M15_2025Q1.html` — 531738 bytes; SHA256 `db2959874c8e52df7cf617dc6e1ec33f3518ea65f9d9fbf96d55d91b443dd3cb`
- `MT5StrategyFactoryPOC/reports/EMA_EURUSD_M15_2025Q1.png` — 10046 bytes; SHA256 `eadf9ddca3eadc88c0fb835480eacc57ffdba37667d584c25971adbf4f6d8781`
- `MT5StrategyFactoryPOC/terminal/MQL5/Experts/EMA_Cross_POC.mq5` — 2937 bytes; SHA256 `6cf155e3507636dca9def9ac408aa16b81851d08b0df7843558e527e23c9582a`
- `MT5StrategyFactoryPOC/tester-ui.ini` — 710 bytes; SHA256 `d5d116318a47ba9e89ead89e04ffa4b690bc13d7c8946289066048587ffca9d8`
- `README.md` — 1915 bytes; SHA256 `239103704e1a71801f88cbc4bbd099a812521276e6f1979c8391557b939408c0`
- `REVISAO_DO_BACKUP.md` — este manifesto; hash disponível na revisão local
- `config/mt5-codex.config.example.toml` — 1400 bytes; SHA256 `823e73cb52f897321d6396bd27343ef0d7cb21cd2b3dabc1a08de21fd053ca5b`
- `config/tester/MT5SF_Estrategia_001.PETR4.M5.20261116_20261118.000.ini` — 2324 bytes; SHA256 `161b1b65a363e3ff9c15eb3c10e43125be2dc188ee739a78917b62a6be5f4357`
- `config/tester/MT5SF_Estrategia_001.PETR4.M5.20261116_20261118.400.ini` — 1580 bytes; SHA256 `b511984c4ae4aa213fc75e17d45db79c836b3bcaf280d557409841a9638ed9b1`
- `config/tester/MT5SF_Estrategia_001.set` — 1838 bytes; SHA256 `c19cf15df4a1f49253af584267650724b048994d1cae21c4cdd679b96c00f283`
- `config/tester/MT5SF_Estrategia_001_v110_PETR4_M5_20261116_20261118_real.ini` — 590 bytes; SHA256 `c98513361981121b49f9916e86a78a7f688602fc79acf64948e51fe9609b9042`
- `config/tester/MT5SF_Estrategia_001_v120_PETR4_M5_20261116_20261118_everytick.ini` — 590 bytes; SHA256 `a32a11f1d39df7b767ba1aa8191ac9064290ff2488b5ff27111bce32abf63481`
- `config/tester/MT5SF_Estrategia_001_v121_PETR4_M5_20261116_20261118_everytick.ini` — 590 bytes; SHA256 `a32a11f1d39df7b767ba1aa8191ac9064290ff2488b5ff27111bce32abf63481`
- `config/tester/MT5SF_Estrategia_001_v122_PETR4_M5_20261116_20261118_everytick.ini` — 590 bytes; SHA256 `a32a11f1d39df7b767ba1aa8191ac9064290ff2488b5ff27111bce32abf63481`
- `config/tester/MT5SF_Homologacao_001.PETR4.M1.20261117_20261118.200.ini` — 816 bytes; SHA256 `9eaca07a30f8d8a46e226d85fe134e3b8caee942d03ed88671570e079ded717e`
- `config/tester/MT5SF_Homologacao_001_PETR4_M1_20261117.ini` — 594 bytes; SHA256 `98670470c10c0f0db88390f462b9fdbfcc61ff1d7cded3e34078eee84b6f920e`
