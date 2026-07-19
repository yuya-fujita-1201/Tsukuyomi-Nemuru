# character-v11 生成・整列契約

## 変更範囲

- v10の正面、口、左右の自然向き、右25/50/80%、左右3/4終点を保持する。
- 母音I / いはユーザー作成サンプル待ちのため変更しない。
- `headTurn` と `turn` を、それぞれ左右16キーへ展開する。
- 左体の長い補間区間を分割するため、33%・66%の専用アンカーを追加する。
- 首・体の全キーへ、可動虹彩、瞬き、小開口を追加する。

## ImageGen左体アンカー

採用原本:

- `assets/character-v11/raw/imagegen/body-left-step-33-chroma-v1.png`
- `assets/character-v11/raw/imagegen/body-left-step-66-chroma-v1.png`

共通生成条件:

- 同一キャラクター、同じ顔、衣装、三日月マイク、星飾り、長髪、色、塗り、線密度を維持
- 1086×1448の上半身立ち絵、単色グリーン背景、影なし、文字なし
- 顔だけでなく胸郭、肩線、ケープ、ペンダントまで同じ方向へ自然に回す
- 33%は正面と左3/4の約1/3、66%は約2/3の大きな体向き
- 首だけを折る、肩幅を潰す、腕やアクセサリーを増減する、髪を別デザインへ変えることを禁止
- 左3/4終点を置き換えず、中間アンカーとしてだけ使う

クロマキー除去後、アルファbboxが上半身の想定範囲にあることを検査する。生成画像を終点として
採用せず、正面・33%・66%・評価済み左3/4の4アンカーを結ぶ。

## 16キー

### 首

- 右: `front → right-step-25 → right-step-50 → natural-right`、各区間5分割
- 左: `front → natural-left`、15分割

### 体

- 右: `front → right-step-25 → right-step-50 → right-step-80 → full-right`
- 右区間数: `4 / 4 / 4 / 3`
- 左: `front → generated-left-33 → generated-left-66 → full-left`
- 左区間数: `5 / 5 / 5`

原画を768×1024へ縮小し、隣接アンカーごとに双方向DIS optical flowを計算する。同じフローを
ニュートラル、瞬き、小開口へ共用し、状態間で髪・衣装・輪郭がずれないようにする。

## 横向きの眼球

正面の分離虹彩alphaを各方向へフロー伝播し、フレームごとに次の2パッチを作る。

1. 伝播した虹彩領域をinpaintした `eye-base`
2. 元フレームから同領域を切り出す `irises`

Webでは `eye-base` の上で `irises` だけを移動する。瞬き中は虹彩を消し、閉眼パッチを表示する。
視線の最大移動は正面と同じX ±12px、Y ±7pxとする。

## atlas

首・体、左右それぞれに次の5 WebPを生成する。

- `neutral`: 768×1024×16、4×4 atlas
- `eye-base`: 目ROIパッチ×16
- `irises`: 目ROIパッチ×16
- `blink`: 目ROI差分×16
- `mouth-small`: 口ROI差分×16

瞬き＋小開口は2パッチを同時表示し、複合全画面画像は作らない。

## 再構築

```bash
.venv/bin/python scripts/build_character_v11.py
npm test
npm run build

python3 /Users/yuyafujita/Projects/.agents/skills/webapp-testing/scripts/with_server.py \
  --server "npm run preview -- --port 4173" \
  --port 4173 \
  -- python3 test/e2e_smoke.py
```

## Cubismとの境界

この素材は動画レビュー用のラスターキーで、CubismのArtMesh、回転デフォーマ、拡張補間、物理演算
ではない。首角×体角×髪物理×母音を任意に直積合成する要件では、髪、顔、首、胴、衣装の隠し塗り
を含む分割素材を再生成してCubismへ移行する。
