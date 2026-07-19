# character-v10 生成・整列契約

## 変更範囲

- `character-v9` の評価済み正面、自然左右、全身3/4、右25/50/80%完成カットを保持する。
- 「閉じ口」と「小開口」の間に62×18pxの `mouth_open_micro` を追加する。
- I / いは58×20pxとし、白い歯面を禁止する。中央12px程度の淡い反射以外はピンク主体にする。
- `headTurn` は左右それぞれ16キーへ展開し、Webでは隣接2キーを連続補間する。

## 首キーの作り方

- 右は `front → right-step-25 → right-step-50 → natural-right` をアンカーにし、各区間5分割で合計16キーにする。
- 左は `front → natural-left` を16キーにする。
- 1086×1448の原画を768×1024へ縮小して補間し、ニュートラルは4×4の3072×4096 WebP atlasへ格納する。
- ニュートラルで算出した双方向DIS optical flowを、瞬き・小開口・複合状態にも共用する。これにより表情以外の動きを状態間で一致させる。
- 首atlasはWebレビュー用近似であり、CubismのArtMesh、デフォーマ、拡張補間ではない。

## 表情

- 各方向は `neutral / blink / mouth-small` の3 atlasを持つ。瞬き＋小開口は2つの非重複パッチを同時表示する。
- `blink / mouth-small` atlasは固定広域ROIだけを切り出して格納し、顔以外のメモリとsource-over二重化を避ける。
- 正面復帰時は分離虹彩と母音口へ戻る。首向き中の眼球と母音は完成ラスター内の描画を使う。

## 口

- `mouth_open_micro` は既存 `mouth_open_small` を62×18pxへ圧縮し、中心 `(543,605)` に配置する。
- 自動口形は `closed → micro → small → wide` の4キー。通常の音声駆動は従来どおり0.40上限なのでwideへ入らない。
- I / いのImageGen原本はクロマキー背景で保存し、白に近い広域画素をローズ色へ置換してから中央にごく短い淡色グリントだけを残す。

## 再構築

```bash
.venv/bin/python scripts/build_character_v10.py

.venv/bin/python /Users/yuyafujita/.codex/skills/live2d-psd-standing/scripts/validate_live2d_layers.py \
  assets/character-v10/manifest-live2d-poc-v1.json

.venv/bin/python /Users/yuyafujita/.codex/skills/live2d-psd-standing/scripts/assemble_psd.py \
  assets/character-v10/manifest-live2d-poc-v1.json \
  --out assets/character-v10/exports/tsukuyomi-nemuri-faceless-poc-v10.psd \
  --force

.venv/bin/python scripts/verify_v10_psd.py
```
