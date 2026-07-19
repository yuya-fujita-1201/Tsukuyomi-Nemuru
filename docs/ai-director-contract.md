# AI Director JSON契約

## 方針

AIは毎フレームの座標を生成しない。数秒ごとの意味キューだけを生成し、描画側が安全な可動値、補間、自動瞬き、呼吸、髪遅延へ変換する。

JSON Schemaは [public/data/director-schema.json](../public/data/director-schema.json) にある。

## 例

```json
{
  "version": 1,
  "title": "短い解説",
  "cues": [
    {
      "at": 0,
      "duration": 3,
      "emotion": "gentle",
      "speech": 0.6,
      "look": [0.1, -0.1],
      "turn": 0,
      "gesture": "present",
      "emphasis": 0.4,
      "note": "視聴者に語りかける"
    },
    {
      "at": 3,
      "duration": 3,
      "emotion": "focused",
      "speech": 0.75,
      "look": [-0.2, 0],
      "turn": -0.62,
      "gesture": "nod",
      "emphasis": 0.7,
      "note": "左3/4のカットへ切り替える"
    }
  ]
}
```

## フィールド

| フィールド | 必須 | 制約 | 意味 |
|---|---|---|---|
| `version` | 必須 | `1` | 契約バージョン |
| `title` | 任意 | 文字列 | シナリオ名 |
| `cues` | 必須 | 1件以上 | 時系列キュー |
| `at` | 必須 | 0以上の秒 | キュー開始 |
| `duration` | 必須 | 0より大きい秒 | 継続時間 |
| `emotion` | 任意 | 列挙 | 表情と呼吸の基調 |
| `speech` | 任意 | 0..1 | 音声未入力時の発話量 |
| `look` | 任意 | `[-1..1, -1..1]` | 視線X/Y |
| `turn` | 任意 | -1..1 | 負数は左3/4、0は正面、正数は右3/4 |
| `gesture` | 任意 | 列挙 | 意味ジェスチャー |
| `emphasis` | 任意 | 0..1 | 強調度 |
| `note` | 任意 | 文字列 | 字幕・演出メモ |

キューは時刻順に並べ、重ねない。

### emotion

- `calm`
- `gentle`
- `sleepy`
- `focused`
- `surprised`

### gesture

- `none`
- `present`
- `nod`
- `book`
- `settle`

## AIへの推奨指示

```text
台本を3〜5秒単位の演技キューへ変換してください。
出力はdirector-schema v1に適合するJSONだけにしてください。
emotion、speech、look、turn、gesture、emphasisを指定してください。
座標、フレーム列、関節角度は生成しないでください。
キューを重ねず、急な姿勢切替を連続させないでください。
```

## 音声連動

任意の音声ファイルを読み込むと、Web Audio APIでRMSを計算し、AIキューの `speech` より優先して口開度へ使う。

音声がない場合も、`speech` から再現可能な疑似発話波形を作るため、JSONだけでPoCを再生できる。
