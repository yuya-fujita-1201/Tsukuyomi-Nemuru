# character-v5 生成・整列契約

## 正本の優先順位

1. `models/ChatGPT Image 2026年7月17日 23_03_43 (1).png`
   - 正面座標、顔幅、前髪、アクセサリー位置の基準
2. `models/ChatGPT Image 2026年7月17日 22_59_20.png`
   - 高精細な髪、三日月ASMRマイク、衣装、閉じた本のペンダント
3. `models/ChatGPT Image 2026年7月17日 22_59_24.png`
   - 正面の色とキャラクター同一性
4. `23_03_43 (2)` / `23_03_44 (3)`
   - 左右3/4ポーズ
5. `23_03_44 (4)` / `23_03_44 (5)`
   - 閉眼、開口の表情参照
6. 横長の一覧画像
   - 体型とポーズの補助のみ。小さい旧三日月アクセサリーは採用しない

## 識別要素

- ミッドナイトパープルの長髪
- 淡い藤色の一房
- 画面右側の大きな三日月型ASMRマイク
- 紺のショートケープと金の縁取り
- 白いハイネックブラウス
- 閉じた本のペンダント

## 顔パーツ生成ルール

- 各出力は一種類のパーツだけを描く。
- 背景は均一な `#00FF00`。ラベル、ガイド、肌、髪を混ぜない。
- 開眼は正面を向き、外形・大きさ・上下位置を左右で揃えた完成目。横長の落ち着いたアーモンド形とし、丸く見開かない。
- 眉とまつ毛は暗い藤色の細い線。太い黒帯、塊状の外まつ毛を避ける。
- 虹彩は意図的に左右別とする。画面左（キャラクター右）は暗い藤黒の瞳、画面右（キャラクター左）は淡い藤白の単一月輪を持つ発光瞳にする。
- 開眼の外形は揃えるが、虹彩を水平反転コピーして同一化しない。金色の多重リングや記号状の月を加えない。
- 虹彩は白目を圧迫しない大きさへ抑え、円形を保つ。左右の虹彩中心を同じ高さにして正面一点を見る。
- 眉は目の上辺に沿う緩やかなカーブとし、目から離しすぎない。
- 口は閉じ、小開口、大開口を別々に生成する。ASMR・朗読の自動再生では閉じ口と小開口だけを使い、大開口は手動QA・将来の別演技用に残す。

## 採用出力

- `assets/character-v5/raw/imagegen/front-faceless-chroma-v1.png`
- `assets/character-v5/raw/imagegen/eyes-open-chroma-v6-awake-calm.png`
- `assets/character-v5/raw/imagegen/eyes-closed-chroma-v1.png`
- `assets/character-v5/raw/imagegen/brows-neutral-chroma-v1.png`
- `assets/character-v5/raw/imagegen/mouth-closed-chroma-v1.png`
- `assets/character-v5/raw/imagegen/mouth-open-small-chroma-v1.png`
- `assets/character-v5/raw/imagegen/mouth-open-wide-chroma-v1.png`
- `assets/character-v5/raw/imagegen/side-left-blink-chroma-v1.png`
- `assets/character-v5/raw/imagegen/side-left-mouth-small-chroma-v1.png`
- `assets/character-v5/raw/imagegen/side-left-blink-mouth-small-chroma-v1.png`
- `assets/character-v5/raw/imagegen/side-right-blink-chroma-v1.png`
- `assets/character-v5/raw/imagegen/side-right-mouth-small-chroma-v1.png`
- `assets/character-v5/raw/imagegen/side-right-blink-mouth-small-chroma-v1.png`

## 横向き表情の固定ROI契約

横向きの座標正本は次の2枚で、どちらも1086×1448とする。

- `assets/character-v5/raw/source/view-left-reference.png`
- `assets/character-v5/raw/source/view-right-reference.png`

ImageGenには左右を別々に編集させ、ミラー流用しない。髪、顔輪郭、眉、鼻、衣装、
大きな三日月ASMRマイク、リボン、イヤリング、身体、構図、緑背景は変更せず、
目または口だけを編集する。口は静かな朗読用の小さな縦開きだけとし、大開口を作らない。

生成結果は全身の完成画像として直接採用しない。`scripts/build_character_v5.py` が
次の固定ROIだけを元サンプルへソフト合成し、ROI外を元サンプルと完全一致させる。

- left eyes: `(312, 402, 620, 527)`
- left mouth: `(392, 570, 469, 620)`
- right eyes: `(462, 402, 763, 527)`
- right mouth: `(610, 575, 699, 628)`

ROIの外周8pxはガウスぼかしマスクで元画像へ戻す。ビルド時にROI外差分が1画素でも
残れば失敗させる。ImageGenが1085×1450を返した場合は、全キャンバス編集として
1086×1448へ直接リサイズしてランドマークを合わせる。

各方向のランタイム状態は `neutral / blink / mouth-small /
blink-mouth-small` の4枚。瞬き量 `b` と小開口量 `m` から
`(1-b)(1-m) / b(1-m) / (1-b)m / bm` を計算し、常に総和1で表示する。
実描画では `neutral` を不透明な土台として保持し、残る3状態は上層からsource-over
alphaを逆算したうえで、上記の目・口ROI内だけへ合成する。これによりアンチエイリアス
された髪・衣装・輪郭を複数の完成PNGで重ねて濃くすることを防ぐ。
正面で手動大開口を確認している場合も、横向き側は `mouth-small` へ写像する。

## 座標補正

ImageGenの「同じキャンバス、同じ座標」は厳密な保証にならない。採用生出力では、
開眼が基準より約100px下に出て、口も状態ごとに上下位置が変わった。このため
`scripts/build_character_v5.py` がクロマ除去後に左右パーツを分割し、次の実測座標へ
数値で再配置する。

- 開眼: 画面左 `(388, 446, 498, 507)`、画面右 `(588, 446, 698, 507)`
- 閉眼: 画面左 `(391, 478, 495, 498)`、画面右 `(591, 478, 695, 498)`
- 眉: 画面左 `(403, 400, 483, 413)`、画面右 `(603, 400, 683, 413)`
- 閉じ口: `(505, 598, 581, 609)`
- 小開口: `(508, 586, 578, 627)`
- 大開口: `(494, 569, 592, 644)`

開眼v2は横128×縦82pxで大きすぎ、右目も外側へ寄って不気味に見えたため不採用。
採用v5は丸く幼く見えたv4を基準に、横幅91.7%、縦幅82.9%の横110×縦58pxへ
変更した。追加調整v6では横幅を維持したまま縦を61px（+5.2%）へ広げ、上まぶたの
かかりを弱めた。登録範囲を上へ1px、下へ2px広げて中心Yを `476.5` とし、半目感を
抑えつつ視線が上向きにならないようにする。
鼻中心 `x=543` に対し、開眼中心を画面左 `x=443`、画面右 `x=643` として、
中心間隔を222pxから200pxへ約10%狭める。開眼は左右別の生素材を使い、画面左の
暗色瞳と画面右の淡い月輪を保持する。閉眼と眉には虹彩差がないため、採用した
画面右素材を反転して対称配置する。眉はv5位置から3px上げ、驚き眉にならない範囲で
目との余白を増やす。

口はユーザー評価が良かったv1生素材を維持する。v6では閉じ口を76×11px、小開口を
70×41px、大開口を98×75pxとする。前版から発話口の縦開きを7〜9%抑え、中心位置を
変えずに明るい笑顔より静かな朗読中の形へ寄せる。再生成した
`mouth-open-small-chroma-v2-quiet.png` は輪郭と上歯が
強く貼り付け感が出たため、比較用に保存するがランタイムでは不採用とする。

`irises.png` と `irisAnchor` は既存ランタイム互換の1pxプレースホルダーであり、見える
虹彩は `eye_base_open.png` に焼き込み済みである。したがって虹彩の見た目を変える場合は
座標値だけでなく、採用開眼素材そのものを更新する。

ランタイムの自動台本と音声RMSは `QUIET_MOUTH_OPEN_LIMIT = 0.4` を上限とする。
`selectMouthWeights` の大開口遷移は0.42から始まるため、自動ASMR・朗読中の
`mouth_open_wide` alphaは0になる。再生停止中にユーザーが手動で0.40超を指定した場合だけ、
素材確認用の大開口を許可する。

## 再生成

```bash
python3 scripts/build_character_v5.py
```

このコマンドは採用生出力を変更せず、1086×1448への正規化、透過化、整列、
ガイド、マニフェスト、表情プレビューを再構築する。
