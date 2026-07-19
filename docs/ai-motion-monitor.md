# AI演技・実時間モーション監視

## 目的

既存の画像品質E2EはPixi tickerを止めて `1/60` 秒ずつ進めるため、眼・レイヤー・補間の
決定論的な回帰には強い一方、実際のChromeで起きるコマ落ち、GPU待ち、目標角への追従遅れは
検出できない。この監視は実時間でAI演技を再生し、処理落ち、モーション補間の急変、滑らかだが
遅い追従ラグを分けて記録する。

## 測定契約

- System Chromeをheadlessで起動し、WebGL rendererがApple Metalであることを確認する
- SwiftShader / llvmpipeは無効な環境として停止し、コードを修正しない
- `whisper` の13秒演技を2周し、1周目coldと2周目warmを分ける
- 音声OFFと追跡済みWAVによる音声ONをfresh pageで別々に測る
- 計測中は動画録画や連続スクリーンショットを行わない
- rAF p50 / p95 / p99 / 最大値、33ms超、50ms超、Long Taskを記録する
- body / head atlasの符号付き位置、1画面更新で1キー超の移動、settle、blackout、NaNを記録する
- body / headごとに `abs(target-current)` のp95 / 最大値（turn単位）と、cue・target変化から
  settleまでのp95 / 最大時間（ms）を記録する
- 39 texture sourceの推定RGBA展開量、Chrome、GPU、viewport、DPRをfingerprintへ含める
- Chromeの完全versionを比較条件に含める。rAFから推定したrefresh rateは診断値に留め、
  環境一致判定には使わない

ポリシー正本は `test/perf/motion-policy.v1.json`。raw frame traceは
`output/perf/runs/` に保存するがGitでは追跡しない。現在基準、最新集計、短い履歴だけを
`output/perf/baselines/current.json`、`output/perf/latest.json`、
`output/perf/history.jsonl` に残す。

## 手動実行

初回基準は同条件を3回ずつ測る。

```bash
npm run perf:motion:baseline
```

通常巡回は1回ずつ。警告を再現確認するときは追加2回測る。

```bash
npm run perf:motion
npm run perf:motion:confirm
```

runnerはproduction buildを作り、レビュー用4173とは別の4174で一時previewを起動する。
checkout単位のlockを取り、buildは5分、probeは10分で打ち切る。previewと子processは終了時に
process groupごと停止する。予期しないdirty worktree、基準欠損、ポート競合、無効GPU、
ブラウザエラーでは停止する。無効・fatalな計測結果はbaselineへ書き込まない。

修正直後の再測定では、変更したsource/testを完全一致のallowlistとして明示する。

```bash
npm run perf:motion:confirm -- \
  --repair-applied \
  --expected-dirty-path src/rig/puppet-engine.js \
  --expected-dirty-path test/puppet-engine.test.js
```

`--expected-dirty-path` は `--repair-applied` と同時にだけ有効。列挙していない差分が1つでも
あれば停止する。修正を検証後は意図したsource/testだけをローカルcommitし、計測履歴は混ぜない。

## 30分ループの判断

- `pass`: baselineと同等。変更しない。2回連続でキャンペーンを終了する
- `warn`: 20%以上、実用最小差、基準の3×MADをすべて超える悪化。変更せず、次回またはconfirmで再測定する
- `fail`: 40%以上かつ基準の5×MADを超える悪化、複数の大きなキー飛び。まず2回の
  confirmationで再現させ、修正可能なコード回帰だけを一度に一原因ずつ直す
- `invalid`: Chrome/GPU/viewport/音声条件が基準と異なる。コードを修正せず人へ報告する

音声probe不成立、browser error、blackout、短すぎるcaptureなど `repairEligible=false` の失敗は
コード修正へ進めず、`stop-human` とする。履歴と停止回数はbaselineのcampaign ID単位で分離する。

キャンペーンは30分間隔で最大6チェック（3時間）。自動修正は最大3回。次の場合は停止する。

- 2回続けて有意改善がない
- 既存の眼・画像品質・Web回帰が悪化する
- headlessと目視で結論が食い違う
- Cubism移行や素材再生成へ範囲が広がる
- 主観判断なしでは良否を決められない
- 予期しないdirty worktreeがある
- 6チェックを終えた

修正した巡では上記の明示allowlistと `--repair-applied` を付け、Web 69件、coverage、build、smoke、eye matrix、
眼品質13件、side-eye 14件を再実行する。自動pushやmainへのmergeは行わない。

## Scheduledの設定

Codex / ChatGPTデスクトップアプリの現在チャット内で30分間隔にする。対象はこのローカルproject、
実行先は履歴と修正を同じbranchへ保持できる **Local** を選ぶ。PCを起動し、アプリを実行中にしておく。
CLIやIDEにはScheduled管理画面がないため、作成・停止・実行履歴の確認はデスクトップアプリの
**Scheduled** で行う。

## Scheduled taskへ貼るプロンプト

この既存チャットを30分ごとに再開し、ローカルproject
`/Users/yuyafujita/Projects/Tsukuyomi-nemuri` の現在branchで、
`/Users/yuyafujita/Projects/Tsukuyomi-nemuri/docs/ai-motion-monitor.md` と
`CONTEXT.md` を読んでから `npm run perf:motion` を実行する。

`output/perf/latest.json` の `nextAction` に従う。`observe` は変更せず次回まで待つ。`confirm` は
`npm run perf:motion:confirm` を実行する。`repair` は同一環境で再現した原因を一つに限定し、先に
失敗する回帰テストを追加してから最小修正する。画像、PSD、atlasを再生成しない。修正後は文書記載の
全回帰を実行し、変更したsource/testだけを `--expected-dirty-path` に列挙してconfirmationを行う。
すべて成功したときだけ意図したsource/testと `CONTEXT.md` をローカルcommitする。計測出力を同じ
commitへ混ぜない。自動push、mainへのmergeはしない。

最大6チェック、自動修正最大3回。改善なし2回、品質回帰、環境不一致、主観判断、
予期しないdirty worktree、範囲拡大のいずれか、または `nextAction` が `stop-*` になったら
Scheduledを停止し、このチャットでユーザーへ確認する。
