# 可動パーツ構成 v1

## 方針

元画像の切り抜きではなく、正面マスターを基準にImageGenで大パーツと表情パーツを再生成する。

完成素材はすべて1086×1448の共通キャンバス、透過PNG。ローカルマスクは位置ガイド、隠し領域除去、虹彩クリップに限定する。

## 採用レイヤー

PSDの下から上:

1. `hair_back`
2. `arm_r_base`
3. `arm_l_base`
4. `body_torso`
5. `face_base`
6. `eye_base_open`
7. `irises`
8. `eyes_closed`（初期非表示）
9. `brows_neutral`
10. `mouth_closed`
11. `mouth_open_small`（初期非表示）
12. `mouth_open_wide`（初期非表示）
13. `hair_front`
14. `earring_r`
15. `earring_l`
16. `accessory_head`

`_l` と `_r` はキャラクター本人から見た左右。

## 動作との対応

- 顔: `face_base`、目、眉、口、前髪、装飾を含む頭コンテナの微動
- 瞬き: `eye_base_open` + `irises` と `eyes_closed` の切替
- 視線: `irises` を左右の白目マスク内で移動
- 発話: `mouth_closed`、`mouth_open_small`、`mouth_open_wide`
- 呼吸: `body_torso` の微小Yスケールと上下移動
- 肩: `arm_l_base` / `arm_r_base` の肩支点回転
- 髪: `hair_back` と `hair_front` の異なる遅延揺れ
- 顔向き: `front` をフェードアウト後、`view-left-3q` / `view-right-3q` をフェードイン

## 検証結果

- `validate_live2d_layers.py`: 0エラー。非表示表情レイヤーに関する意図的な警告3件
- 正面合成: `assets/character-v2/previews/live2d-neutral-v1.png`
- PSD: `assets/character-v2/exports/tsukuyomi-nemuri-live2d-poc-v1.psd`
- PSD再オープン: 1086×1448、16レイヤー確認

PSDはCubism素材であり、ArtMesh、デフォーマ、パラメータ、物理演算は含まない。
