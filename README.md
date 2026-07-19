# 月詠ねむり Faceless-base AI Puppet

カメラ追従や演者を使わず、AIの意味キューと音声から動くYouTube向けキャラクターPoCです。

現在のランタイムは `character-v14` の39素材です。ブラウザの
`連続首・体キー実験室` で、首、体、視線、口、瞬きを操作できます。首と体はそれぞれ
移動中だけ左右16キーを隣接補間し、入力停止から約80ms後は最寄りの単一キーへ固定します。
横向きでも眼球、瞬き、静かな小開口が追従します。横向きの目は、焼き付いた元の虹彩を消す
lossless eye-base、参照画像から再描画した可動虹彩、固定した上下まぶたの3レイヤーへ再分離しました。
中央視線から常にこのclean splitを使うため、視線を動かし始めた瞬間にもneutral眼との半透明な
二重表示が起きません。

髪・身体を一枚の正面PNGごと引っ張るメッシュ補正は、歪みを避けるため推奨モードから
外しています。髪は首・体の各キーに描かれた形ごと動きます。左右3/4の評価済み絵は
体キーの終点として保持しています。

## 現在の到達点

- `headTurn`: 左右16キー、追従率12/s。60fps換算12フレームで入力の90%以上へ到達
- `turn`: 左右16キー、追従率9/s。大きな肩・上半身の動きを離散カットなしで表示
- 停止時は隣接ラスターの二重表示を解除し、横向き全体のidle/breath変形も固定
- `headTurn / turn` の絶対値0.035以下は正面として扱い、微小入力で横向きatlasへ誤切替しない
- 左体33%・66%の専用アンカーを追加し、正面から左3/4までの長い補間区間を分割
- 正面虹彩を承認済みv5基準へ戻し、重心を画面左 `(455, 478)`・画面右 `(630, 478)` に配置して外向き視線を補正
- 正面虹彩を下まぶた近くまで延ばし、画面右＝キャラクター左眼の白い月輪を復元
- 首・体×左右の全64フレームで、旧虹彩を白目色へ置換し、同じdark / luminous参照ペアで虹彩を再描画
- `eye-base / irises / eye-line` をすべてlossless PNG化し、固定上まつ毛を可動虹彩から分離
- 横向きは中央視線からclean splitを常時表示し、旧neutral虹彩との0.02〜0.10 cross-fadeを廃止
- 正面視線はX±12px・Y±7px、横向きは眼裂からはみ出しにくいX±5px・Y±2pxの楕円へ制限
- 旧虹彩下縁を下まぶたと誤認していた固定点を除去し、実際の上まつ毛だけを固定
- 右体3/4の遠眼は、虹彩の丸みに沿う判定を水平な上まつ毛帯へ修正し、切れ目3pxと縦の固定ノイズを除去
- 左右体3/4のeye-baseは頬の肌色を拾わず、各眼に隣接する低彩度白目で塗り、視線端の桃色リムを除去
- 横向き虹彩の欠けた下半分を眼裂内で補完し、白目消去を横方向へ限定して、虹彩と下まぶたの白い隙間を解消
- 正面の画面右上まぶたを画面左の鏡像へ微調整し、虹彩の月輪・固有模様・中心位置は維持
- 正面瞬きを `open / half / closed` の3キーへ変更し、4つの目頭・目尻アンカー、下まぶた、虹彩座標を固定
- 正面口9種を形状不変のまま右へ4px移動し、元の正面基準画像の顔軸へ整列
- 横向きの瞬きと小開口を独立パッチ化し、視線と同時使用
- 正面の `closed → micro → small → wide` と中開き母音5種を保持
- A/U/E/Oは現状維持。I / いは今回のサンプルを基準に52×15pxの浅いピンク口へ更新
- 旧28ポーズPNGを起動時ロードから外し、URL更新を90msデバウンス
- 同一フレームのTexture再代入を避け、rendererのdevice pixel ratioを最大1.5へ制限
- 正面、視線、首左右、体左右3/4のプリセットと共有URL復元を保持
- AI演技、音声RMS、9:16 / 16:9、旧 `soft / head-only` 比較モードを保持

## 評価用成果物

- 正面中央視線: [output/screenshots/faceless-v14-front-gaze-center.png](output/screenshots/faceless-v14-front-gaze-center.png)
- 左体neutral: [output/screenshots/faceless-v14-body-left-neutral.png](output/screenshots/faceless-v14-body-left-neutral.png)
- 首右neutral: [output/screenshots/faceless-v14-neck-right-neutral.png](output/screenshots/faceless-v14-neck-right-neutral.png)
- 横向き視線5方向×首・体: [assets/character-v14/previews/side-gaze-clean-v2.png](assets/character-v14/previews/side-gaze-clean-v2.png)
- 左右体終端×視線3方向の下まぶた拡大: [assets/character-v14/previews/body-side-lower-lid-v1.png](assets/character-v14/previews/body-side-lower-lid-v1.png)
- 正面open / half / closed: [assets/character-v14/previews/front-blink-keys-v1.png](assets/character-v14/previews/front-blink-keys-v1.png)
- 正面・首・体5ポーズ×中央・微小・最大4方向: [output/screenshots/eye-motion-matrix-v14.png](output/screenshots/eye-motion-matrix-v14.png)
- 右体3/4・右視線の上まつ毛拡大: [output/screenshots/body-right-right-eye-closeup-v14.png](output/screenshots/body-right-right-eye-closeup-v14.png)
- 左右体3/4・左右視線端の白目縁拡大: [output/screenshots/body-side-sclera-rim-fixed-v14.png](output/screenshots/body-side-sclera-rim-fixed-v14.png)
- 首右の虹彩なしclean eye-base: [output/screenshots/faceless-v14-neck-right-eye-base-clean.png](output/screenshots/faceless-v14-neck-right-eye-base-clean.png)
- 体左の虹彩なしclean eye-base: [output/screenshots/faceless-v14-body-left-eye-base-clean.png](output/screenshots/faceless-v14-body-left-eye-base-clean.png)
- 首右中間・視線・小開口: [output/screenshots/faceless-v14-neck-right-gaze-mouth.png](output/screenshots/faceless-v14-neck-right-gaze-mouth.png)
- 左体中間・視線・小開口: [output/screenshots/faceless-v14-body-left-gaze-mouth.png](output/screenshots/faceless-v14-body-left-gaze-mouth.png)
- 静止ロックした左体: [output/screenshots/faceless-v14-body-left-static-a.png](output/screenshots/faceless-v14-body-left-static-a.png)
- I / いのWeb表示: [output/screenshots/faceless-v14-front-mouth-i-reference.png](output/screenshots/faceless-v14-front-mouth-i-reference.png)
- Web上の正面半閉じ: [output/screenshots/faceless-v14-front-blink-half.png](output/screenshots/faceless-v14-front-blink-half.png)
- Web上の正面閉眼: [output/screenshots/faceless-v14-front-blink-closed.png](output/screenshots/faceless-v14-front-blink-closed.png)
- 新旧I / い比較: [assets/character-v12/previews/mouth-i-user-reference-v11-v12.png](assets/character-v12/previews/mouth-i-user-reference-v11-v12.png)
- Webレビュー全体: [output/screenshots/parameter-review-v14-final.png](output/screenshots/parameter-review-v14-final.png)
- 16:9レビュー全体: [output/screenshots/parameter-review-v14-wide.png](output/screenshots/parameter-review-v14-wide.png)
- v14眼修正契約: [prompts/parts-v14/generation-contract.md](prompts/parts-v14/generation-contract.md)
- v14正面15レイヤーPSD: [assets/character-v14/exports/tsukuyomi-nemuri-faceless-poc-v14.psd](assets/character-v14/exports/tsukuyomi-nemuri-faceless-poc-v14.psd)
- Webパラメータ仕様: [docs/parameter-review.md](docs/parameter-review.md)
- Cubismとの境界を含む技術方針: [docs/architecture.md](docs/architecture.md)

### 保持した旧成果物

- v10首16キー一覧: [output/review/tsukuyomi-v10-neck-keyframes.png](output/review/tsukuyomi-v10-neck-keyframes.png)
- v10閉じ口・微開き・小開口・I: [output/review/tsukuyomi-v10-mouth-keys.png](output/review/tsukuyomi-v10-mouth-keys.png)
- 既存横向きレビュー動画: [output/video/tsukuyomi-side-motion-review-v1.mp4](output/video/tsukuyomi-side-motion-review-v1.mp4)
- 自然向きレビュー動画: [output/video/tsukuyomi-natural-motion-review-v1.mp4](output/video/tsukuyomi-natural-motion-review-v1.mp4)
- v10 PSD: [assets/character-v10/exports/tsukuyomi-nemuri-faceless-poc-v10.psd](assets/character-v10/exports/tsukuyomi-nemuri-faceless-poc-v10.psd)
- 過去版の詳細は [CONTEXT.md](CONTEXT.md) に保存

## 起動

```bash
npm install
npm run dev
```

本番ビルドをローカル確認する場合:

```bash
npm run build
npm run preview
```

## 素材の再構築と検証

```bash
.venv/bin/python scripts/build_character_v14.py
.venv/bin/python test/test_eye_quality_v14.py -v
.venv/bin/python test/test_side_eye_assets.py
.venv/bin/python /Users/yuyafujita/.codex/skills/live2d-psd-standing/scripts/validate_live2d_layers.py \
  assets/character-v14/manifest-live2d-poc-v1.json
.venv/bin/python /Users/yuyafujita/.codex/skills/live2d-psd-standing/scripts/render_preview.py \
  assets/character-v14/manifest-live2d-poc-v1.json \
  --out assets/character-v14/previews/live2d-manifest-preview-v14.png --force
.venv/bin/python /Users/yuyafujita/.codex/skills/live2d-psd-standing/scripts/assemble_psd.py \
  assets/character-v14/manifest-live2d-poc-v1.json \
  --out assets/character-v14/exports/tsukuyomi-nemuri-faceless-poc-v14.psd \
  --flat --force
.venv/bin/python scripts/verify_v14_psd.py
npm test
npm run test:coverage
npm run build

python3 /Users/yuyafujita/Projects/.codex/skills/webapp-testing/scripts/with_server.py \
  --server "npm run preview -- --port 4173" \
  --port 4173 \
  -- python3 test/e2e_smoke.py
```

`build_character_v14.py` はv13を非破壊コピーし、承認済みのgreen / hero基準画像から正面の
dark / luminous虹彩を再構築します。横向きは首・体×左右の各16フレーム、計64フレームについて、
旧虹彩を眼ごとの白目色で消すeye-base、参照ペアを姿勢別silhouetteへ収めた可動irises、固定上下まぶたへ
再分離します。3種の眼atlasはlossless PNGです。正面は上まぶた鏡像、半閉じキー、閉眼線、口X位置を
パーツ限定で更新し、15レイヤーのv14 PSDへ同期します。顔、髪、輪郭、眉、鼻、服、アクセサリー、
評価済み向き終点はv13から保持します。

## AI Director

AIには毎フレームの座標を作らせず、数秒ごとに `emotion`、`speech`、`look`、`turn`、
`gesture`、`emphasis` をJSONで返させます。契約は
[docs/ai-director-contract.md](docs/ai-director-contract.md) と
[public/data/director-schema.json](public/data/director-schema.json) にあります。

## Cubismは必要か

現在の用途が生配信ではなく、決めた角度を動画内で自然に動かすことなら、今すぐCubismへ移る
必要はありません。16キーのキャッシュ方式は、完成絵の品質を保ちながらオフライン動画素材を
作る用途に向いています。

次の要件を同時に満たす段階ではCubismが有利です。

- 任意の首角と体角を完全に独立して組み合わせる
- 横向きでも「あ・い・う・え・お」と大開口を全角度で使う
- 前髪、横髪、後ろ髪を束別に揺らし、慣性・衝突を設定する
- 低メモリで連続角度をリアルタイム配信する

その場合は、髪、顔、首、胴、服の隠し塗りを含むパーツ分けを再制作し、ArtMesh、回転デフォーマ、
拡張補間、物理演算を組む必要があります。

## 重要な制約

- 16キーは完成ラスターの光学補間で、CubismのArtMeshやデフォーマではない
- `parameter` は体系列を表示中、別の `headTurn` を同時合成せず体角を優先する
- 横向き口は閉じ口〜小開口。母音5種と大開口は正面専用
- 髪束別の物理演算は未実装。現在は各キー内の髪形を使用
- PSDのCubism読み込み、ArtMesh、パラメータ、物理演算は未確認
- 公開、アップロード、配信は行っていない

## 構成

```text
.
├── assets/character-v10/       # 保持した正面・口・PSD・旧首キー
├── assets/character-v11/       # 保持した首・体16キー版
├── assets/character-v12/       # 保持した静止ロック・I口版
├── assets/character-v13/       # 保持した旧虹彩分離版
├── assets/character-v14/
│   ├── raw/imagegen/           # 採用ImageGen原本
│   ├── work/                   # クロマキー除去前の正規化素材
│   ├── master/                 # 正面のっぺらぼうベース
│   ├── parts/                  # 整列済み正面顔差分
│   ├── poses/                  # v11から保持した評価済み向き素材
│   ├── neck-atlases/           # 左右16キー、眼3状態をlosslessで再生成
│   ├── body-atlases/           # 左右16キー、眼3状態をlosslessで再生成
│   └── previews/               # 視線5方向を含む合成確認
├── prompts/parts-v14/          # v14の正面・横向き眼修正契約
├── src/                        # AI演技・音声RMS・PixiJSランタイム
├── scripts/                    # 素材構築、PSD検証、動画生成
├── test/                       # 単体・ブラウザE2E
├── output/                     # 評価用画像・音声・動画
└── CONTEXT.md                  # 継続作業用ステータスと履歴
```
