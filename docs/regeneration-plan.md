# 再生成版アセット計画

## 実績

P0〜P3のPoC範囲は完了。正面、左3/4、右3/4、大パーツ、開眼、虹彩、眉、閉じ目、3段階口、装飾を生成し、透過PNG、16レイヤーPSD、Webランタイム、MP4まで作成した。

採用ファイルと現在の制約は [../CONTEXT.md](../CONTEXT.md) を正本とする。

## 結論

元画像から直接切り抜いたり、元画像全体を歪ませたりしない。

元画像は以下の参照だけに使う。

- キャラクターの顔立ち
- ラベンダー系の髪と瞳
- 月、星、リボンの装飾
- ナイトドレスとニットカーディガン
- 柔らかく眠たげな雰囲気

構図、ポーズ、背景、小物は新規設計する。

## フェーズ

### P0: 正面マスター

- 頭頂から腰まで
- 完全な正面向き
- 顔と肩を傾けない
- 両腕を胴体から少し離す
- 両手を画面内へ収める
- 髪は大きな房に整理する
- 本、マイク、猫、家具、背景を入れない
- 単色クロマキー背景

### P1: 姿勢ベース

- front
- left_3q
- right_3q

横顔1枚を正面のメッシュ変形には使わず、正面を短くフェードアウトしてから3/4をフェードインする姿勢セットとして扱う。

### P2: 大パーツ

最初から細い髪やまつ毛を個別生成しない。次の大きな塊を共通キャンバスで作る。

- back_hair
- torso_and_costume
- neck
- face_base
- ear_left / ear_right
- front_hair
- side_lock_left / side_lock_right
- arm_left_base / arm_right_base
- hand_left_base / hand_right_base
- accessories

各パーツは隠れる領域まで描く。合成時に穴が出ないよう、境界の内側へ十分な重なりを持たせる。

### P3: 表情と発話

- eye_open
- eye_half
- eye_closed
- iris_center
- iris_left / iris_right
- brow_neutral
- brow_happy
- brow_worried
- mouth_closed
- mouth_small
- mouth_mid
- mouth_open
- mouth_smile

既存の「アイ」方式と同様、表情パーツは共通の顔ベース上へ機械的に配置する。

### P4: ジェスチャー

- relaxed
- explain
- emphasize
- point
- hands_together

腕全体を無理に変形するより、肩から先の差分を切り替え、切り替え区間だけ補間する。

## AI駆動

AIは座標を毎フレーム生成しない。以下の意味キューを出す。

- speech: 発話量
- emotion: neutral / happy / sleepy / concerned / excited
- gaze: camera / left / right / down
- head: front / left_3q / right_3q
- gesture: relaxed / explain / emphasize / point
- emphasis: 0.0 - 1.0

描画側が値を制限し、補間、自動瞬き、呼吸、髪揺れを決定する。

## 合格条件

- 元画像とは異なる正面構図として成立する
- 月詠ねむりと認識できる
- 左右の目、口、輪郭、衣装の位置が差分間で揺れない
- 腕や髪を動かしても透明な穴が出ない
- 9:16と16:9の両方で肩から上が安全領域に収まる
- 30秒動画で目立つ破綻フレームが1%未満
