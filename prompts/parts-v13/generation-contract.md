# character-v13 横向き眼球分離契約

## 目的

`character-v12` の口、首・体16キー、瞬き、小開口、静止ロック、評価済み終点を保持したまま、
正面の目頭に残った旧虹彩片と、横向きで視線を移動した際の二重表示・まつ毛欠けを解消する。
修正対象は正面 `eye_base_open.png` の目頭側白目2領域と、首・体×左右の
`eye-base / irises / eye-line` atlasとし、Webランタイム38素材を `character-v13` から読み込む。

## 入力と保持条件

- 入力正本: `assets/character-v12/`
- 出力: `assets/character-v13/`
- v12を上書きせず、全ファイルをv13へ非破壊コピーしてから対象atlasだけを再生成する
- 正面開眼ベースは目頭側2領域のRGBだけを虹彩なし参照から補修し、alphaと領域外は変更しない
- ほかの正面13素材、母音I / い、blink、mouth-small、首・体アンカー、静止ロックは変更しない
- neutralは同じ生成系列を使い、右体中間2コマの灰色頬パッチだけ局所補修する
- v12のPSDを保持し、Cubism用の新規リギングは行わない

## 対象フレーム

| 系列 | 方向 | フレーム数 |
|---|---|---:|
| neck | left | 16 |
| neck | right | 16 |
| body | left | 16 |
| body | right | 16 |

合計64フレームについて、各系列の `eye-base-v1.webp`、`irises-v1.webp`、
lossless `eye-line-v1.png` を再生成する。

## 虹彩マスクの再整列

1. v11/v12と同じアンカー・光学フローからneutralフレームと虹彩マスクを再構成する
2. 伝播マスクを連結成分へ分ける
3. 各成分を実画像の紫・暗色虹彩へ合わせ、X±12px・Y±6pxの探索範囲で再整列する
4. 距離ペナルティを加え、虹彩らしい画素への一致度が最大の位置を採用する

強い横角度で光学フローの伝播先がずれても、実際に描かれた虹彩を消去・抽出の中心にする。

## レイヤー分離

### 可動虹彩と固定アイライン

- 再整列した伝播成分は最終マスクではなく、局所探索窓にだけ使う
- 強い紫seedを開演算・最大連結成分で整理し、実際に塗られた虹彩へtight maskを作る
- 白目・肌色の露出境界を可動irisから剥がし、左右2つの主虹彩を保持する
- 独立したHSV・凸包参照で下35%側の虹彩色を回収し、細い正当フリンジを欠けさせない
- 虹彩上端プロファイルの上10px以内にある暗色線と外側まつ毛を固定eye-line候補にする
- 8px以上の小成分が独立虹彩内部に属さない場合は、離れたまつ毛片として固定eye-lineへ戻す
- 虹彩内部、淡い白目、肌色は固定eye-lineへ含めず、可動irisとのalpha重複を0にする

### clean eye-base・可動iris・固定eye-line

- 可動irisはtight maskから元のRGBAを切り出す
- clean eye-baseは可動irisを包含し、その外側1pxのうち有彩色の虹彩フリンジだけを加えた安全領域を塗る
- darkなまつ毛・アイラインへ消去領域を拡張しない
- fixed eye-lineは元画像のRGBAをlossless PNGへ切り出し、移動後のirisより前面に固定表示する
- 中央視線はWebP再合成を避け、neutral完成眼だけを表示する
- 視線半径0.02以下では分離眼を非表示、0.10までsmoothstepで有効化する

## 数値検査

64フレームすべてに次を適用する。

- eye-base alpha面積 > 0
- iris alpha面積 > 0
- eye-base alphaがiris alphaを全画素で包含する
- eye-lineとirisのalpha重複が0
- 面積300px以上の主連結成分が左右2眼ちょうど存在
- 面積8px以上の全小成分が独立虹彩内部と交差し、離れたまつ毛片を含まない
- clean eye-baseは可動irisの1px近傍外を変更しない
- 虹彩上端プロファイルより下の内部に固定eye-line画素が0
- 独立下側虹彩参照のeye-base / iris欠落が0、eye-lineとの重複が0
- 独立上まつ毛参照のeye-line欠落が0、eye-base / irisとの重複が0
- 上下左右4移動で固定eye-lineのRGBAが元画像と完全一致
- 可動iris境界に含まれる淡い白目の比率が各眼35%以下
- 合成テストでは、8pxずれた伝播マスクも実虹彩へ再整列し、移動元に虹彩色を残さない
- 正面目頭ROIの旧虹彩片が左右とも0
- 正面開眼ベースのalphaと補修ROI外はv12と一致し、ほかの正面13素材はファイルバイト・RGBAとも一致

Web表示では正面をX±12px・Y±7px、横向きをX±5px・Y±2pxの楕円可動域とする。
横向きは完成ラスター由来のため、正面より可動域を狭めて眼裂からのはみ出しを抑える。
`headTurn / turn` の絶対値0.035以下は正面として扱い、微小入力で横向きatlasへ切り替えない。

## 再構築と検証

```bash
.venv/bin/python scripts/build_character_v13.py
.venv/bin/python test/test_side_eye_assets.py
npm test
npm run test:coverage
npm run build
python3 test/e2e_smoke.py
python3 test/e2e_eye_matrix.py
```

## 非対象

- 正面の目頭側白目以外の再生成
- 横向き用の母音5種と大開口
- 首角と体角の完全な直積合成
- 髪束別ArtMesh、デフォーマ、慣性、衝突、物理演算
- Live2D Cubismへの実インポートとリギング
