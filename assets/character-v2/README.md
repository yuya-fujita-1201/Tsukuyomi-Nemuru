# Character v2 assets

元画像を切り抜かず、キャラクター参照としてImageGenで再生成した可動素材です。

## 正本

- 正面: `master/front-master-v2.png`
- 左3/4: `poses/view-left-3q-v1.png`
- 右3/4: `poses/view-right-3q-v1.png`
- 最終レイヤー構成: `manifest-live2d-poc-v1.json`
- 正面合成: `previews/live2d-neutral-v1.png`
- PSD: `exports/tsukuyomi-nemuri-live2d-poc-v1.psd`

## 採用パーツ

```text
hair_back
arm_r_base
arm_l_base
body_torso
face_base
eye_base_open
irises
eyes_closed
brows_neutral
mouth_closed
mouth_open_small
mouth_open_wide
hair_front
earring_r
earring_l
accessory_head
```

全パーツは1086×1448の共通キャンバス、RGBA PNGです。表情差分の `eyes_closed`, `mouth_open_small`, `mouth_open_wide` はPSDでは非表示レイヤーとして保持しています。

`alignment/` と `parts/candidates/` は採用判断の履歴、`guides/` はImageGen出力を正座標へ戻すためのbboxガイドです。

PSDはレイヤー素材であり、CubismのArtMesh、デフォーマ、パラメータ、物理演算は含みません。
