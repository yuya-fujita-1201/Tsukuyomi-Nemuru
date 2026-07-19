# character-v14 眼修正契約

## 正本

- キャラクター正面: `assets/character-v5/raw/source/identity-green-reference.png`
- 発光する月輪の補助基準: `assets/character-v5/raw/source/identity-hero-reference.png`
- 白い月輪を持つ眼は、画面右＝キャラクター左眼
- v14はv13を非破壊コピーし、顔・髪・輪郭・眉・鼻・服・アクセサリーと向き終点を保持する

## 正面

- 虹彩重心は画面左 `(455, 478)`、画面右 `(630, 478)`。v13の外向き位置へ戻さない
- 虹彩は下まぶた近くまで届かせ、下側に太い白目帯を残さない
- 画面左はdark iris、画面右は白い月輪を持つluminous iris
- 虹彩2成分以外の画素を可動レイヤーへ追加しない
- 画面左の開眼上半分を正本とし、画面右の上まぶたを鏡像化する。下まぶた、眼の外接枠、間隔は変えない
- dark / luminous虹彩はコピーせず、月輪を含む左右固有テクスチャと重心を維持する

## 正面瞬き・口

- 開眼・半閉じ・閉眼は、画面左の目尻 `(389, 471)`・目頭 `(496, 474)` とその鏡像4点を固定する
- `eyes_half_closed` は元の顔下地で上側だけを覆い、上まぶた線だけを50%位置へ下げる。下まぶたは描き直さない
- 半閉じ中も `irises` の座標とtransformを変えず、上まぶたカバーで隠す
- 閉眼線は画面左を正本に完全鏡像化し、左右の高さ・長さ・角度を揃える
- 正面口9種は形・RGBA・解像度を変えず、すべてX方向へ `+4px` 平行移動する

## 横向き

- 首・体×左右の各16フレームすべてを対象とする
- 旧虹彩は `eye-base` で完全に白目色へ置換する
- `eye-base` の色は各眼に隣接する低彩度白目から採り、露出縁のp90彩度18以下へ中性化する。頬やまぶたの肌色を白目下地へ使わない
- 視線X±5pxで露出する虹彩外周と外周フェザーに、肌色の縁取りを残さない
- 可動 `irises` はdark / luminous参照ペアを姿勢別silhouetteへ収める
- 上まつ毛は固定 `eye-line` に置き、可動虹彩とalphaを重複させない
- 上まつ毛の抽出帯は列ごとの虹彩上端へ追従させず、虹彩全体の上端を基準に水平へ保つ
- 虹彩輪郭と重なる画素は、水平帯内のnear-blackなまつ毛芯だけを固定し、中間色の虹彩を固定しない
- 固定線候補の6px未満の孤立成分は、視線移動時の浮遊ノイズになるため除外する
- 遠眼で欠けた虹彩下半分だけを既存bbox内接楕円で補い、下まぶた直前まで延ばす
- 旧虹彩の消去は横方向だけへ拡張し、下方向4pxの白塗りを行わない
- `_sclera_fill` は実際の消去領域だけを塗り、下まぶた・頬へ再膨張しない
- 完成した虹彩の直下にある非白目画素は固定下まぶたとして前面へ復元する。可動虹彩側へ穴を焼き込まない
- `eye-base / irises / eye-line` はlossless PNG。眼レイヤーへlossy WebPを使わない
- 虹彩の所有画素は不透明にし、白目を透過させない。外側にだけ少なくとも4pxのsoft-alpha画素を残す

## ランタイム

- 描画順は `neutral → eye-base → shifted irises → fixed eye-line → blink → mouth`
- 横向きは中央視線を含めclean splitを常時alpha 1で使う
- neutral眼とsplit眼の半透明cross-fadeを行わない
- 可動範囲は正面X±12px・Y±7px、横向きX±5px・Y±2pxの楕円内
- 正面瞬きは `open → half → closed` の3キー。`blink=0.5` では半閉じをalpha 1、虹彩を同じ座標でalpha 1にする
- 横向き瞬きは可動虹彩と固定線を隠し、姿勢別閉眼パッチを表示する
- 起動時素材数は39点

## PSD

- `manifest-live2d-poc-v1.json` は半閉じを含む正面15レイヤーを持つ
- 出力は `assets/character-v14/exports/tsukuyomi-nemuri-faceless-poc-v14.psd`
- standalone PNG 15枚とPSD内レイヤーのRGBA一致、1086×1448、neutral合成を再読込検証する
- これはCubismインポート用の素材PSDであり、ArtMesh・デフォーマ・パラメータ・物理演算は含まない

## 必須検証

- `test/test_eye_quality_v14.py`: 正面上まぶた鏡像、虹彩重心・下端・月輪、半閉じ・固定角、口+4px、64フレーム、左右終端の所有と消去、`body/right` 終端遠眼の視線X±5px時の上まつ毛RGBA不変、両体終端の露出白目縁p90彩度18以下、下側白隙間median 0 / p90 1px以下
- `scripts/verify_v14_psd.py`: 正面15レイヤーの埋込RGBA一致とneutral合成
- `npm test` と `npm run test:coverage`
- `npm run build` 後の `test/e2e_smoke.py`
- 正面・首左右終端・体左右終端について、中央、微小移動、上下左右最大の実ブラウザ撮影
- 生成成功や修正完了は、上記テストと撮影画像の目視確認後にだけ報告する
