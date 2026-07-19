# character-v6 生成・整列契約

## 目的

`character-v5` の正面と既存の左右全身3/4を保持したまま、頭部が先に向きを変え、
肩と上半身は少しだけ追従する会話向け左右ポーズを追加する。正面の閉じ口だけは、
顔中心へ揃えた短く細いリップへ差し替える。

## ImageGenで使った構図契約

生成モードは組み込みImageGen。ニュートラル左右は新規生成、瞬きと小開口は採用した
各ニュートラルを基準にした編集として作成した。指示の中心は次のとおり。

> 月詠ねむりと同一人物の1086×1448向け全身透過素材。ミッドナイトパープルの長髪、
> 淡い藤色の一房、画面右の大きな三日月型ASMRマイク、藤色リボン、紺の金縁ケープ、
> 白いハイネックブラウス、閉じた本のペンダントを厳密に保持する。正面に近い上半身から、
> 首と頭を先行して画面左または画面右へ自然に向け、肩は同方向へごく軽く追従させる。
> 既存3/4のように肩を完全な横向きにしない。落ち着いた会話中の姿勢、均一な緑背景、
> 文字・影・追加アクセサリーなし。

表情編集では構図、顔輪郭、髪、衣装、マイク、身体、キャンバス位置を変えず、次の一点だけを
変更するよう指示した。

- `blink`: 両目を自然に閉じる。口はニュートラルのまま。
- `mouth-small`: 目は開いたまま。口だけを静かな朗読用の小さな縦開きへ変更し、歯を強調しない。

## 採用ImageGen出力

- `assets/character-v6/raw/imagegen/natural-left-neutral-chroma-v1.png`
- `assets/character-v6/raw/imagegen/natural-left-blink-chroma-v1.png`
- `assets/character-v6/raw/imagegen/natural-left-mouth-small-chroma-v1.png`
- `assets/character-v6/raw/imagegen/natural-right-neutral-chroma-v1.png`
- `assets/character-v6/raw/imagegen/natural-right-blink-chroma-v1.png`
- `assets/character-v6/raw/imagegen/natural-right-mouth-small-chroma-v1.png`

最初の右向き案は左右方向が逆だったため不採用とし、プロジェクト配下へはコピーしていない。

## 自然向き表情の固定ROI

生成結果は1086×1448へ正規化してクロマ除去する。表情差分は完成画像全体を採用せず、
次の固定ROIだけをニュートラルへ合成する。ROI外に1画素でも差分があればビルドを失敗させる。

- natural left eyes: `(330, 412, 620, 526)`
- natural left mouth: `(414, 560, 500, 620)`
- natural right eyes: `(474, 412, 770, 526)`
- natural right mouth: `(604, 566, 690, 628)`

各方向は `neutral / blink / mouth-small / blink-mouth-small` の4状態。既存の全身3/4も
同じ4状態をそのまま `character-v6` へコピーし、削除・上書きしない。

## 正面の閉じ口

閉じ口はImageGenで再生成せず、ユーザー評価済みのv5素材を決定的に縮小・再着色する。

- 配置: `(513, 599, 573, 606)`
- 中心: `x=543`（1086pxキャンバスの厳密な中央）
- 可視最大寸法: 60×7px
- 線alpha: 元素材の72%
- 基本色: 薄い藤褐色
- 中央下部: ピンクのガウス状アクセントを重ね、細いリップの芯を残す

## 再生成

```bash
.venv/bin/python scripts/build_character_v6.py
```

この処理は `character-v5` を読み取り元として保持し、`character-v6` の24ランタイム素材、
レビュー画像、マニフェストを再構築する。
