# Evaluation freeze: C1 strong-matrix run (DEV-015)

**Frozen** on 2026-10-04 (UTC). These records are the scored result of EXPERIMENT_PLAN §5–§6 for C1 and
for the two baselines on the same episodes. They were never re-scored after the results were seen.

- **Run:** `20261003-2323_claude_strong` (`manifest.json` `created_at` 2026-10-03T23:23:51+00:00), merged in
  #53 (commit `7d39f2e`).
- **Configuration:** `claude-opus-5-5`, effort `high`, `prompt-v2`
  (`prompt_sha256` `dc07da980883558de995de94ed9c3affc1c8982f31fc5f149f9bfcacda1d91d1`), strong matrix,
  seeds 500,000–500,029, 15 BP and 15 MA, ≤ 12 turns, budget 6, no model fallback.
- **Hashes:**
  - `matrix_sha256` `5d10b4d2239919f3a5065e3f04921b333506bb5cda5c66a7c66b313292bb134c`;
  - `scenario_sha256` `5291e69c061fa42973cf541bd84b78a90770dc971227f32f052acfc404c0ce08`;
  - `gate0_summary_sha256` `b933a089f3b792c7ae6baef8b0763d7ad4d8c83b9871b707f771ff8ac8f740ca`.
- **Completion:** all 30 episodes `DIAGNOSED`. No `API_FAILURE` and no `REFUSED`, so no re-runs
  (`manifest.json` `reruns` is empty). 136 API calls are logged in `usage.jsonl`.
- **Baselines:** `20261003-2333_good_scientist_strong` and `20261003-2333_passive_bayes_strong`, on the same 30 episodes.

## Rules after the freeze

- The files listed below are not edited, re-run or re-scored. Generated outputs (`results.md`,
  `results.png`, `replay/`) can be regenerated from them, and that never changes a metric.
- Construct-validity findings from this run go into OPEN_RULINGS (§H) and apply only to a new prompt, scenario or
  record version, run as a new experiment.
- `manifest.json` has no freeze field: DEV-015 asked for the freeze to be declared there, but this run
  was committed before that was added. Declaring it in this file instead keeps the scored records
  byte-identical.

## Frozen files (SHA-256)

Check them with `sha256sum` from `experiments/results/`.

| File | SHA-256 |
|---|---|
| `20261003-2323_claude_strong/manifest.json` | `a56291a6c8e195163e37deb712e55515c81ceeea0a77472c991a2b4eb4ee0240` |
| `20261003-2323_claude_strong/summary.json` | `f87eb4ba6f05159a87aedfb3b1468447b93619909b5869f9ef4f084389a08747` |
| `20261003-2323_claude_strong/usage.jsonl` | `816dc64d005baef32ed8846ba123adb98bce10adf36b2dce7dfbf3d852e20415` |
| `20261003-2323_claude_strong/episodes/s500000-BP.json` | `312ca0eedeabe95a2f38a319f2347b12ecef7e8ccb1836c85e10f9e305142e50` |
| `20261003-2323_claude_strong/episodes/s500001-MA.json` | `8b8a74aa833002c9e3b111001417cb99295d7d170be4e7358e82c6177e339a61` |
| `20261003-2323_claude_strong/episodes/s500002-BP.json` | `26661964af57de42460c623556a55e178b22ba862cc8884463b4124464f9aa8b` |
| `20261003-2323_claude_strong/episodes/s500003-MA.json` | `dece531fb179f9b66e67e30fcc11bd7a8a660335c399fb6a669c67d1d5a36e3f` |
| `20261003-2323_claude_strong/episodes/s500004-BP.json` | `b7039cc802fb1cb78cc1e6e4813b6b39867bc678567049012261574479a0f34c` |
| `20261003-2323_claude_strong/episodes/s500005-MA.json` | `30a6811d901ac176303d4204cc3c585a9b3acfe87c2cbc40396361ae340f5d28` |
| `20261003-2323_claude_strong/episodes/s500006-BP.json` | `fb5bdfa61f0499bdd22f791a49d67359ffaa15f25b458dcf2c18a61daf2a0a42` |
| `20261003-2323_claude_strong/episodes/s500007-MA.json` | `05ab160a3c7c31b96ea9526dfa0a7adf16acc6822633d53276cc6adbf952b800` |
| `20261003-2323_claude_strong/episodes/s500008-BP.json` | `5b461967f4b18dfcad2ed5aea3c20f96206617886173a144e5c95c036e309fc1` |
| `20261003-2323_claude_strong/episodes/s500009-MA.json` | `f5aad52a8c609bcf662b0736ff80126c5d96cdbfbff5705603996d56c0d396e3` |
| `20261003-2323_claude_strong/episodes/s500010-BP.json` | `23a017194fec65810a7a3da7ea439b5c93d933a9a0f4430ad817b21d9f77581d` |
| `20261003-2323_claude_strong/episodes/s500011-MA.json` | `235a8d7990f459bd8489df6ea8bc3c2c90f50b48a666f5cedd47e665bfe85b9c` |
| `20261003-2323_claude_strong/episodes/s500012-BP.json` | `f082bade77c676d3c3c0e1c7c9ba2a686dbbbb1d698a6a45702b82da07c50e93` |
| `20261003-2323_claude_strong/episodes/s500013-MA.json` | `96439e24705c2aae54acb0133fdb7c5a250e545a56a8f2e393a08cd651dd1043` |
| `20261003-2323_claude_strong/episodes/s500014-BP.json` | `bb305be22c7beace2edf39490b5dce9e816a5c2599632632307444610abacb67` |
| `20261003-2323_claude_strong/episodes/s500015-MA.json` | `55dff9a5c1cc37016c51dc4295c168d8b21f21fcdb793113bf7b8e353cac9a89` |
| `20261003-2323_claude_strong/episodes/s500016-BP.json` | `f6f93facef3cb74558ec94ad259b7014331d6497fd633c20035c7eb6a8a0c8c3` |
| `20261003-2323_claude_strong/episodes/s500017-MA.json` | `b68737685e5b7a6a3f4e5c238bcda69a5ebed30fb68cda47463ce30fb615723e` |
| `20261003-2323_claude_strong/episodes/s500018-BP.json` | `9694ab3aaef3755ebd7c3889cbcf135ed39193bdfbfcaaea7969d389ee3410f3` |
| `20261003-2323_claude_strong/episodes/s500019-MA.json` | `d37c9ca4b6a0f6f9ca8051e34855712259290fd6fe7a8dd2640ccd2ee3d08c9f` |
| `20261003-2323_claude_strong/episodes/s500020-BP.json` | `6a7085b05872556e501fc5c693ca0f77b3ead97473e7f63f1a8dce615f82c9ea` |
| `20261003-2323_claude_strong/episodes/s500021-MA.json` | `d62ccecfbfa05ac620a87339d7faa4b91407e99940636548373f5dbdb1d1f5a3` |
| `20261003-2323_claude_strong/episodes/s500022-BP.json` | `792d23ded0520249a4d7afa8c3a9a94c5ebfa359ddcaa6682e80e0c1384bc276` |
| `20261003-2323_claude_strong/episodes/s500023-MA.json` | `e4ec74086bf7439923a815e8efd2238eedfb0f33d3d5c5c780028b5bcc84bccd` |
| `20261003-2323_claude_strong/episodes/s500024-BP.json` | `fe17037704d8d5429d09fcf11d56022b822d5d18a2c804ff1fcf71cbb5acc35f` |
| `20261003-2323_claude_strong/episodes/s500025-MA.json` | `e8c62f8d8f3b2cba59883439ed11c75174144f0f6edfc6d71b03d997dfe260ff` |
| `20261003-2323_claude_strong/episodes/s500026-BP.json` | `9c0f328bb3a719c9bf7af59b23ae47cfb3dfc9ea38ea5d80990ec8800f22545c` |
| `20261003-2323_claude_strong/episodes/s500027-MA.json` | `72a66af4face91f5b342f47047cde057bb8d56716a64836904aa0a0be57c9491` |
| `20261003-2323_claude_strong/episodes/s500028-BP.json` | `eedcab899e6888b2754d01b5c46978c99e11a3f439de57c6d50c02e3e2d9b275` |
| `20261003-2323_claude_strong/episodes/s500029-MA.json` | `fb6548b36790c578558f7b6d0c33b8231bfbb2b4817272d5b7e2303f281191e0` |
| `20261003-2333_good_scientist_strong/manifest.json` | `6a111a751f022bb40e5b85c858746ab948606a07107a08a82819ac5de10db77c` |
| `20261003-2333_good_scientist_strong/summary.json` | `fedbbe2e08239c29d8dad03c3b48f6c9fa94f76bdee27de9fc4065caf806cf8f` |
| `20261003-2333_good_scientist_strong/episodes/s500000-BP.json` | `0d05fafce2bbac93545bfc33646c92c64f9b067c17dc0e368bb15c466889ead4` |
| `20261003-2333_good_scientist_strong/episodes/s500001-MA.json` | `1977c50205e93ea7c19f0c5e7c71b0e611337c85d5810dd2e5cb436d3e1a54f0` |
| `20261003-2333_good_scientist_strong/episodes/s500002-BP.json` | `116a704a3d0899086b769918be76d373c2a097dc2f032ee2621b3d94bd510e38` |
| `20261003-2333_good_scientist_strong/episodes/s500003-MA.json` | `dceafb82cf610f4ad2ee315da6441bd66a6ff50c7d42c4432f0ac85eafc48126` |
| `20261003-2333_good_scientist_strong/episodes/s500004-BP.json` | `79ba6b41b69a660138f87b5b284afd3cf9942c5d19efccc04c568e43f4f89a97` |
| `20261003-2333_good_scientist_strong/episodes/s500005-MA.json` | `aa57d3eb6c215e0adc4ba524ba27b2832141c2a8f15120e31347d3fd4f76ecad` |
| `20261003-2333_good_scientist_strong/episodes/s500006-BP.json` | `d752c1ddc150d06ed80e10fbc2ab033efe4f8001db5297ed412d0ad0ae126f30` |
| `20261003-2333_good_scientist_strong/episodes/s500007-MA.json` | `371c1927731b307560a9c632b29af5a33f44a818535a385924906cdbf09217c6` |
| `20261003-2333_good_scientist_strong/episodes/s500008-BP.json` | `039d3c6abc92bcca229ea7cc06ca34e7083365b7902f4e641bb6facda50e53cb` |
| `20261003-2333_good_scientist_strong/episodes/s500009-MA.json` | `3946077e4ef19e2dbac7506cc57f7a6a0c7d373181176ee23e3877a0378ccf26` |
| `20261003-2333_good_scientist_strong/episodes/s500010-BP.json` | `959d62251414ad4776bb4a3a19482ea97818f51fdec34eca1a3e3e009f70e0fd` |
| `20261003-2333_good_scientist_strong/episodes/s500011-MA.json` | `c770ba34f3c7d6eee2a750c4a55c8ddbb64148c7c0fc2062bc87d6614cd761bc` |
| `20261003-2333_good_scientist_strong/episodes/s500012-BP.json` | `5698d3fbbedb16cbed240c70df471692986a409e420c62a5c0205a2fe9af90ae` |
| `20261003-2333_good_scientist_strong/episodes/s500013-MA.json` | `1bff0453b1c7ea9a86e3c66b2e43b49eb30a12bf1fef99c1f3df469c5b4c8442` |
| `20261003-2333_good_scientist_strong/episodes/s500014-BP.json` | `a3071fb290bbb2f67e57cfadee584b1ce51e2a3a10459233649db30084a285dc` |
| `20261003-2333_good_scientist_strong/episodes/s500015-MA.json` | `bb5c609cb7df447edfc33bc761421609cf24ef675456bedc950d56d9b77f7f77` |
| `20261003-2333_good_scientist_strong/episodes/s500016-BP.json` | `1428fb7189044ed26b8201ad023a652b89d7b46a3b12da77c8628af5956561ea` |
| `20261003-2333_good_scientist_strong/episodes/s500017-MA.json` | `fa35da6bacae5fc5477b3c2ddca547a85f12e7c799c5897e4541971eccef7a0e` |
| `20261003-2333_good_scientist_strong/episodes/s500018-BP.json` | `d8079113cc8f26251a5ca574d51154181eccd2b1231645555471ab4b5c450fe4` |
| `20261003-2333_good_scientist_strong/episodes/s500019-MA.json` | `44e1cb36e539f4d342e81ebb09e02cf7789be9556928a0a09f8ef2f290d39c01` |
| `20261003-2333_good_scientist_strong/episodes/s500020-BP.json` | `5636c53445ffd5c4feaf83b760472dfa88c3feab90babbaf6803edcc48ac8cce` |
| `20261003-2333_good_scientist_strong/episodes/s500021-MA.json` | `1613853534dc0ead928056e4a18656860be3ff6c6660a7aa159f2b61ad2325a8` |
| `20261003-2333_good_scientist_strong/episodes/s500022-BP.json` | `d0f2817d8c4f15769bb5c435c88d78030a3708f2a194df42d5f95ecf433d1a32` |
| `20261003-2333_good_scientist_strong/episodes/s500023-MA.json` | `1f0dcc3154dd1ac95b243630a5fb4f3b6f443285f67df42d67ffa4d5298c9f74` |
| `20261003-2333_good_scientist_strong/episodes/s500024-BP.json` | `7c796d587acd565bb379b9b3bb680db1556504e43a528d19175f56b4efe7a8f0` |
| `20261003-2333_good_scientist_strong/episodes/s500025-MA.json` | `b46d2c9b43ce8e0d50f18c9ae0c2aae93f06477df2887b40f6c6eae4133e01fd` |
| `20261003-2333_good_scientist_strong/episodes/s500026-BP.json` | `d1db5dd5516e07f63e70081a337631d41aeba729ac0a69519e118f7b9393187b` |
| `20261003-2333_good_scientist_strong/episodes/s500027-MA.json` | `40d0afa5c71282078d9068101c224c87c5e1dd630fe4e68f736e837d37171b31` |
| `20261003-2333_good_scientist_strong/episodes/s500028-BP.json` | `526e57e8a231f989b8adcec49d9535d9cba93f9e5777e9935d6dc5e6db275c30` |
| `20261003-2333_good_scientist_strong/episodes/s500029-MA.json` | `6cf3865a313557bfd03c413c6f93af0081b37459d9959ce35d948cde3f211d9f` |
| `20261003-2333_passive_bayes_strong/manifest.json` | `18f8338560716c42e470436a592f9ad56aa0a8b6ee744a32b8c4a6ea2cc7f9d2` |
| `20261003-2333_passive_bayes_strong/summary.json` | `59c06453665382030e37567c0f9917e61b330d3a11c365c8277badc776e8ea82` |
| `20261003-2333_passive_bayes_strong/episodes/s500000-BP.json` | `b26b8fb2a4c65d655eb962390800891a56edb8b12e1b84c22e0cdeac9b0eda29` |
| `20261003-2333_passive_bayes_strong/episodes/s500001-MA.json` | `54ad40e692bf90d260b4c0dcd7f55e704034caf75ba914865b502cd23487944d` |
| `20261003-2333_passive_bayes_strong/episodes/s500002-BP.json` | `cae56fa8b267809d4ce018b95196945f77fb1a25f6b4415a9d257f7d3d273126` |
| `20261003-2333_passive_bayes_strong/episodes/s500003-MA.json` | `b7ee91645e0b43ed00c45949691c055506d975fad2daf711edbfefeb1e9f5372` |
| `20261003-2333_passive_bayes_strong/episodes/s500004-BP.json` | `7b8f67274ecf9e9f1acb3efdb479084311013588d17a582f144d0bd4b1adad41` |
| `20261003-2333_passive_bayes_strong/episodes/s500005-MA.json` | `cf7eb2f00c56a47ec906845189fd48dff52b65966a20903acfea43716db6d9df` |
| `20261003-2333_passive_bayes_strong/episodes/s500006-BP.json` | `2af186d83ba1ab99a33547b153445db23bf8cb8dfec7754ef392a7976e612583` |
| `20261003-2333_passive_bayes_strong/episodes/s500007-MA.json` | `daf7aa045b9ebfd769a73aad4ab89b05312ac3b1bc4f2571fca1cb1545c56cad` |
| `20261003-2333_passive_bayes_strong/episodes/s500008-BP.json` | `57846108eae6153be267119c0a3107a0db22f34133a8f52690fd9deb88ead673` |
| `20261003-2333_passive_bayes_strong/episodes/s500009-MA.json` | `a4f815633719d32ab1f4971b40f2af27375d3e462e541a6d19f7fd165903688d` |
| `20261003-2333_passive_bayes_strong/episodes/s500010-BP.json` | `bdbfb055797167b825605f089e8f6f7a5079a54a61c2834818c1e9a4ff0634f6` |
| `20261003-2333_passive_bayes_strong/episodes/s500011-MA.json` | `e0fa9811aa753a2a3d70182a89a674005b9ef14c19195a32dc6bbc588fc0449e` |
| `20261003-2333_passive_bayes_strong/episodes/s500012-BP.json` | `4c53c473369abfbd4b879093970ca5e89d98138f636395c4faed5a0bf993aefb` |
| `20261003-2333_passive_bayes_strong/episodes/s500013-MA.json` | `48b10351cc49fce16f81b92109ee5bf98810c0df9e1f83f3a949f6bc9a50d1a1` |
| `20261003-2333_passive_bayes_strong/episodes/s500014-BP.json` | `36a77408202d9ca5700bc846ab7c4d02fb290675d04b168d91a496e2a4bfe317` |
| `20261003-2333_passive_bayes_strong/episodes/s500015-MA.json` | `cddc2e7f2e477d35b5a40d434cf432fb242efbab499ac4b6b70bf3747028b7c3` |
| `20261003-2333_passive_bayes_strong/episodes/s500016-BP.json` | `2805c506904384a024a06d5e6ee26c237cd987e2228287d3a4b861dadedc4800` |
| `20261003-2333_passive_bayes_strong/episodes/s500017-MA.json` | `1853fd1b99c413736c9b59181651678311738563c8484ca465c95197bec8b479` |
| `20261003-2333_passive_bayes_strong/episodes/s500018-BP.json` | `e121cb5c44830f84a3c51d2574d0b0b343753a4b3e8c9fd8dd1750a396f28b81` |
| `20261003-2333_passive_bayes_strong/episodes/s500019-MA.json` | `a7ebb767c1dfa02ae78cb001fa1ac2c50815b8352adb03fbb977c358cb13ad89` |
| `20261003-2333_passive_bayes_strong/episodes/s500020-BP.json` | `47fbef3c122aa99b5f8d88cfd0689a43dd3c7486d54da6713cba8d6a94f3f5d7` |
| `20261003-2333_passive_bayes_strong/episodes/s500021-MA.json` | `4fb900dc7347e5074b40628d2d8e31629999bb4087967067aa2a061ffcec3ce2` |
| `20261003-2333_passive_bayes_strong/episodes/s500022-BP.json` | `b7e39ec99f57208d1da413a2f350f5feb437b8799f251b265e6eee27d25c42f3` |
| `20261003-2333_passive_bayes_strong/episodes/s500023-MA.json` | `6fc5b2d3bd651705204dd679f9869e5f540220e0e92ceb25cc8ecdf89d67e809` |
| `20261003-2333_passive_bayes_strong/episodes/s500024-BP.json` | `0577187616eb1f5ef36f8b2e4bf56d52ffb0d6eb6a426f23a721d8ac328c2335` |
| `20261003-2333_passive_bayes_strong/episodes/s500025-MA.json` | `f7fe98e65fc4183d1814eb3d82d87b4c01373f1d51e8411bd04d8e0773110c52` |
| `20261003-2333_passive_bayes_strong/episodes/s500026-BP.json` | `bcef0345e6fe4630fc2093637ad1c6e985ab176589b88be01ca6565490cf04cf` |
| `20261003-2333_passive_bayes_strong/episodes/s500027-MA.json` | `eb6ccae877e99ce2f89becbfc3d8d18184475cc76d26f1a827453c2d90d8b9f3` |
| `20261003-2333_passive_bayes_strong/episodes/s500028-BP.json` | `ce911b2100935801186067747121b3b62bc3c0e00c244e876da330e44d4bef40` |
| `20261003-2333_passive_bayes_strong/episodes/s500029-MA.json` | `de31ec91c9c366afc3af6fa5aa3ea728413ab6b2633af0bc43cc1ae4ca88f27b` |
