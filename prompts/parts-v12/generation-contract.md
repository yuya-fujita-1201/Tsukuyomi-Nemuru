# character-v12 生成・整列契約

## 目的

`character-v11` の承認済み正面絵、首・体16キー、横向き表情パッチを保持したまま、
ユーザー提供サンプルに合わせて正面の母音 `I / い` だけを更新する。Webランタイムは
動作中の隣接補間を維持し、停止時は単一キーへ固定して二重像と周期的な揺れを残さない。

## I / いの形状

- 正本原画: `assets/character-v12/raw/imagegen/mouth-vowel-i-user-reference-chroma-v1.png`
- 整列先: `assets/character-v12/parts/aligned-v1/mouth_vowel_i.png`
- full canvas: 1086×1448 RGBA
- alpha bbox: `[517, 598, 569, 613]`
- サイズ: 52×15px
- 中心: x=543
- 浅い葉／カプセル形。上辺はほぼ水平、下辺は浅いU字
- 中央は柔らかいピンク、輪郭は細いくすみ赤紫
- 白い歯面、個別の歯、黒い口腔、舌の分割線、強い笑顔カーブは禁止
- クロマキー残りと高彩度緑画素は0、白系低彩度画素も0を検査する

## 静止ロック

- 首・体とも移動中だけ `abs(value) × 15` の前後2キーを補間する
- 目標値不変かつ現在値との差が0.004以下の状態を80ms保持したら停止扱い
- 停止時は `round(abs(value) × 15)` の単一キーをalpha=1で表示する
- 隣接する上側キーはalpha=0にする
- 停止中の横向き全体は平行移動0、回転0、scale=1へ固定する
- 視線、瞬き、口パッチは固定中も独立操作できる
- 目標値が0.0005を超えて変化した最初のフレームでロックを解除する

## 再構築

```bash
.venv/bin/python scripts/build_character_v12.py
.venv/bin/python scripts/verify_v12_psd.py
npm test
npm run test:coverage
npm run build
python3 test/e2e_smoke.py
```

## 非対象

- v11の首・体atlasの再生成
- 横向き専用の母音Iパッチ
- 髪束別ArtMesh、デフォーマ、物理演算
- Live2D Cubismへの実インポートとリギング
