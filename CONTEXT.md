# CONTEXT

最終更新: 2026-07-19

## 2026-07-19 GitHub退避・AI演技の実時間30分監視基盤

ユーザー指定の `https://github.com/yuya-fujita-1201/Tsukuyomi-Nemuru.git` は、修正着手前の
承認済みv14一式を `main` の `6290235036c05ca4cfea4815f466f2ec48ac4e77`
（`chore: preserve reviewed v14 baseline`）としてpushし、local / `git ls-remote` / GitHub APIの
SHA一致を確認した。その後の監視実装は `agent/motion-performance-loop` で行い、
`54c4a07`（監視基盤）と `4712343`（断続warning保持）へ分けてlocal commitした。

`test/e2e_ai_motion_perf.py` はSystem Chromeの実tickerを止めず、`whisper` 13秒演技を2周する。
音声OFF/ONはfresh pageへ分離し、rAF、Long Task、body/head atlas step、target-current追従誤差、
cue/target変化からsettleまでの時間、blackout、非有限state、実音声再生/RMSを記録する。
SwiftShader / llvmpipe、Chrome完全version・viewport・GPU・音声条件の不一致はコード回帰として
扱わない。測定中のvideo/trace recordingは行わず、終了後の静止画とraw NDJSONだけを残す。

`scripts/run_ai_motion_monitor.py` はproduction buildと一時preview 4174を使う。checkout lock、
build 5分/probe 10分timeout、子process groupのTERM→KILL、予期しないdirty path停止、修正後に
明示した `--expected-dirty-path` のみ許可、対象contentのbuild前/後/probe後SHA-256不変確認を持つ。
履歴はbaselineのcampaign IDごとに分離し、初回warn/failはconfirmation、fatal/invalidは
`stop-human`、自動修正最大3回、改善なし2回、最大6チェック、pass 2回で停止する。無効・fatalな
計測はbaselineへ書かない。運用正本とScheduled用promptは `docs/ai-motion-monitor.md`。

正式baseline `20260719T133009.338997Z` はcommit `4712343`、Chrome
`150.0.7871.125`、Apple M4 Metal、39 texture / RGBA推定310.976MiBで採取した。OFF/ON各3回とも
renderer/audio/integrityが有効で、blackout 0、非有限state 0、Long Task 0。中央値は次の通り。

- 音声OFF: rAF p95 / p99 `18.6 / 18.6ms`、body max step `1.064`、body tracking p95
  `0.161 turn`、settle p95 `818.7ms`
- 音声ON: rAF p95 / p99 `18.5 / 18.6ms`、body max step `1.073`、body tracking p95
  `0.158 turn`、settle p95 `816.805ms`、全3回でAudioContext running・時刻進行・RMS最大約0.645

基準後の通常1巡 `20260719T133346.561029Z` もOFF/ONともpass、`nextAction=observe`。
一方、探索runでは右向きcue付近に約66.4ms停止とbody step 3.456、最初の正式採取でも6回中2回に
33.3ms級停止とstep 1.85〜1.93が出た。再採取6回では再現しなかったため、engine修正はまだ行わず、
断続的な1 repeat warningをmedianで隠さない回帰を追加して30分監視へ引き継いだ。
canonicalは `output/perf/baselines/current.json`、`latest.json`、`history.jsonl`。raw runと
`preview.log` はGit ignore。

監視追加後の確認は、motion Python 29/29、Web 69/69、coverage 行96.47%・分岐89.90%・
関数98.67%、production build、smoke console error 0、eye matrix 5姿勢×6視線=30/30、
v14眼品質13/13、全64frame横向き素材14/14。4173はHTTP 200で
`index-m23XuXp3.js` を配信中。Scheduled管理UIはこの実行環境から操作できないため未作成。
デスクトップアプリの現在チャット内・Local project・30分間隔で、文書内promptを登録する必要がある。

## 2026-07-19 右体3/4終端・近眼上アイラインの赤丸白ノッチ追補

最新の赤丸添付は、実ブラウザの `body/right` frame 15・`gazeX=+1 / gazeY=0`
（iris実移動 `+5px`）とNCC 0.998719で一致した。対象は画面左の近眼＝キャラクター右眼。
前回直した画面右の遠眼とは別で、近眼の上まつ毛中央にある暗紫AA 15pxと、その直下の
暗色領域が可動iris / 白目下地へ誤分類されていた。このため右視線でirisが5px移動すると、
元画像では暗い上アイラインだった赤丸内へ白目が四角く露出し、線が縦に削れて見えていた。

修正は `body/right` の最終frame・画面左眼だけに限定した。上まつ毛に挟まれた
元画像 `x=393..407, y=323` の暗紫AA 15pxを固定eye-lineへ戻し、さらに赤丸相当の
`x=387..397, y=324..330` から暗色76pxだけを固定した。白目そのもの、虹彩下段、反対眼、
ほか15frame、左体、首、正面素材は変更していない。修正前に追加した実描画回帰は、暗色76px中
56pxが白目化して失敗し、修正後は白目化0pxになった。旧atlasとの比較では変更は
`body/right` frame 15の `eye-base` 86px、`irises` 72px、`eye-line` 85pxだけだった。

再生成後の実ブラウザ右視線は `output/screenshots/body-right-near-upper-eyeline-fixed-v14.png`
に保存し、赤丸位置で上アイラインが連続し、下側の可動白目へ固定線が伸びていないことを
拡大目視した。全v14品質13/13、全64frame旧回帰14/14、Web 69/69、5姿勢×6視線E2E 30/30、
smoke、production buildを再確認した。

## 2026-07-19 右体3/4終端・遠眼上アイラインのAAブリッジ追補

最新のユーザー添付1・2は、実ブラウザの `body/right` frame 15・`gazeX=+1 / -1`
（iris実移動 `+5px / -5px`）とそれぞれNCC 0.999851 / 0.999824で一致した。対象は
画面右の遠眼。前回の固定上まつ毛回帰はHSV明度 `V<80` の黒い芯だけを検査していたため、
元画像座標 `x=507..517, y=330` にある暗紫アンチエイリアス11px（`V=86..133`）を
見逃していた。この11pxは `eye-base alpha=255 / irises alpha=255 / eye-line alpha=0` となり、
視線を左右へ動かしたとき白目下塗りが四角い切れ目として露出していた。

修正は `body/right` の最終frame・画面右眼・虹彩上端1行だけに限定した。既存lash guardの
左右に挟まれた `S>=12 / V<145` の虹彩所有画素を補助bridgeとして検出し、固定eye-lineと
movable exclusionへ加える。虹彩mask、bbox、参照texture寸法、次の虹彩行には触れない。
旧v14とのatlas画素比較では、変更は `right-eye-base / right-irises / right-eye-line` の
frame 15各11pxだけで、ほか15frame、左向き、首向き、正面素材は同一だった。

添付相当の実ブラウザ2状態は
`output/screenshots/body-right-upper-eyeline-fixed-v14.png` に保存した。ユーザー報告11pxを
独立source座標で固定する回帰テストは修正前 `base所有11px` で失敗し、修正後はbase/iris所有0、
eye-line未復元0、視線X±5pxの合成RGBA差0。全v14品質11/11、全64frame旧回帰14/14、Web 69/69、
5姿勢×6視線E2E 30/30、smoke、production buildを再確認した。

## 2026-07-19 横向き眼縁・下側白隙間、正面眼差・瞬き・口位置の追補

ユーザー添付1は `body/left` frame 15、添付2・3は `body/right` frame 15に一致した。
白目色の彩度は前回修正済みだったが、旧虹彩消去を5×5楕円で2回膨張していたため、虹彩下端から
下へ4px（Web表示で約5.7px）の下まぶた・肌を白く上書きしていた。さらに遠眼の姿勢別iris maskは
眼窩で欠け、`body/left` は下半分69px、`body/right` は111px不足していた。これらが白い縁、浮いた
眼球、三白眼に見える下側の白い楔を同時に作っていた。

v14 builderは、遠眼の既存bbox内で虹彩下半分だけを内接楕円として補い、元画像で虹彩と下まぶたの
間にある連続白目だけを最大3px回収する。消去領域は横方向へだけ広げ、紫の旧フリンジ以外を下へ
膨張しない。白目塗りも実消去領域内へ限定した。完成虹彩の直下にある非白目画素は固定下まぶた・
肌として `eye-line` 前景へ復元し、可動iris側へ固定線形状の穴を焼き込まない。虹彩所有画素は不透明、
soft alphaは外側だけにした。これにより左右体終端×視線X `-5 / 0 / +5` の12眼条件で、虹彩中央50%
直下の連続白隙間は中央値0px、p90 1px以下になった。露出白目縁のp90彩度18以下、固定上まつ毛、
月輪も同時に維持している。

正面は、画面左の開眼上半分を正本に画面右の上まぶただけを鏡像置換した。眼の110×61 bbox、間隔、
下まぶた、顔、髪、輪郭、眉、鼻、服、アクセサリーは変更していない。左右虹彩は鏡像基準で重心差
x0.08px / y0.03px、主ハイライト差約0.7pxと既に揃っていたため変更せず、画面右＝キャラクター左眼の
白い月輪と左右固有模様を保持した。正面口9種は形・RGBA・解像度不変のままXへ+4px移動し、全bbox
中心を元の正面基準に合うx=547へ揃えた。

正面瞬きは39番目のランタイム素材 `eyes_half_closed.png` を追加し、`open → half → closed` の3キーへ
変更した。画面左の目尻 `(389,471)`・目頭 `(496,474)` と鏡像4点を全キーで固定し、半閉じは顔下地の
上まぶたカバーだけを下げる。下まぶたとiris transformは動かさない。閉眼線は画面左を正本に完全鏡像。
Webは `blink=0 / 0.5 / 1` で各キーを同期し、半閉じでiris alpha 1・座標不変をE2E確認した。

古いv12内容のままだったPSDとは別に、正面15レイヤーを収録する
`assets/character-v14/exports/tsukuyomi-nemuri-faceless-poc-v14.psd` を新規組立てした。manifest検証は
0 errors / 10 hidden-layer warnings。再読込で1086×1448、15レイヤーすべてがstandalone PNGとRGBA一致、
neutral合成の最大平均差0.12656118/255・差25超0.09596%を確認した。Cubism実インポート、ArtMesh、
デフォーマ、パラメータ、物理演算は引き続き未確認。

## 2026-07-19 左右体3/4・白目パッチの肌色リム除去

ユーザー添付4枚は、`body/right` と `body/left` の終端frame 15をそれぞれ
`gazeX=-1 / +1` へ振った4条件と一致した。虹彩や固定まつ毛ではなく、旧虹彩を消す
`eye-base` の下塗り色が原因。`_sclera_fill()` が `S<82` と暖色RGB順序で白目候補を
選んでいたため、実際には頬の肌色を大量に採り、左右端でRGB `(251..252, 217..221,
210..212)`・HSV彩度42〜43の桃色帯を露出させていた。

白目サンプルを各眼の近傍にある `S<=20 / V>=205 / RGB差<=20` の中性色だけへ限定した。
局所中央値は最大チャンネル245以上、チャンネル差14以内へ正規化し、外周フェザーを含む
消去領域全体へ同じ白目色を使う。これにより元絵の薄い色味を残しながら、頬色の枠取りを
白目へ混ぜない。左右体終端・視線X±5pxの露出縁は、修正前p90彩度42〜43から全4条件14へ
低下した。

回帰テストは、移動後虹彩の外周2pxかつeye-baseが実際に見える領域を独立抽出し、40px以上の
非空性とp90彩度18以下を要求する。実ブラウザ30条件と添付相当4条件を再撮影し、
`output/screenshots/body-side-sclera-rim-fixed-v14.png` で桃色リムなしを目視確認した。
正面眼、白い月輪、上まつ毛3px修正、反対向き、瞬き、小開口も回帰を通過している。

## 2026-07-19 右体3/4終端・遠眼の上まつ毛切れ追補

ユーザー添付1の「キャラクター左向き＝画面右向き」は、ランタイムの `body/right` 終端
frame 15・`gazeX=+1` に一致する。画面右の遠眼では、固定すべき上まつ毛3px
`(499,330) / (498,331) / (499,331)` が `eye-line` に入らず、`eye-base` のalpha
26 / 31 / 255で半透明化または完全消去されていた。同時に、列ごとの虹彩上端へ追従した
抽出帯が虹彩側面まで下降し、視線を+5px動かしたときに縦の固定断片を露出させていた。

`scripts/build_character_v14.py` の固定上まつ毛抽出を、列別profileではなく虹彩全体の
`global_top` を基準にした水平帯 `global_top-10..global_top+2` へ変更した。虹彩と重なる
範囲はV<80のnear-blackなまつ毛芯だけを固定し、6px未満の孤立成分は除外する。これにより
本物の3pxを固定線へ回収しつつ、虹彩側面の縦断片と可動虹彩内の中間紫色を固定しない。

独立したsource/raw-mask由来の上まつ毛マスクを使う回帰テストを追加した。修正前は
未保護3px、視線X±5px合成時の最大RGBA差233で失敗し、修正後は未保護0px・差分0px。
実ブラウザでは5ポーズ×6視線の30条件を再撮影し、添付1相当の
`output/screenshots/body-right-right-eye-closeup-v14.png` で上まつ毛の連続と浮遊断片なしを
目視確認した。反対向き、正面、月輪、瞬き、小開口も回帰テストとE2Eを通過している。

## 2026-07-19 v14 正面視線・三白眼感・横向き眼ノイズの修正

ユーザー添付の正面・左右向き拡大と、リポジトリ内の承認済みgreen / hero基準画像を照合した。
正面の視線分散はv13の入力値ではなく、v7で別生成した虹彩が承認済みv5完成眼より左右へ
約13pxずつ外側へ置かれていたことが原因。v13虹彩は下端が開眼下端より5px上にあり、さらに
下半分の淡色域が白目のように見えて三白眼感を強めていた。

横向きは、虹彩atlasへ上まつ毛と旧虹彩フリンジが混入し、eye-base / irisesのlossy WebP圧縮と、
neutral眼からsplit眼へ視線半径0.02〜0.10で重ねる処理が輪郭ノイズを増幅していた。右向きの
画面右＝キャラクター左眼は、元アンカーの弱い白輪をそのまま切り出していたため、正面と異なる
虹彩に見えていた。

v14では正面虹彩を基準画像から再構築し、重心を画面左 `(455, 478)`、画面右 `(630, 478)` へ
合わせた。画面右眼には瞳孔周囲の白い月輪を持つluminous textureを使う。横向き64フレームは、
旧虹彩を眼ごとの白目色で消すeye-base、同じdark / luminous参照ペアを姿勢別silhouetteへ収めた
可動irises、固定上まつ毛のeye-lineへ再分離した。3種ともlossless PNGで、虹彩外周は
`BORDER_CONSTANT` のalpha featherを持つ。旧虹彩下縁を下まぶたと誤認した固定点は除去した。

ランタイムは横向き中央視線からclean splitをalpha 1で常時表示する。これによりneutral眼との
半透明二重描画をなくし、中央から微小に視線を動かす瞬間にも旧虹彩縁が現れない。描画順は
`neutral → eye-base → shifted irises → fixed eye-line → blink → mouth-small` を維持する。

## 2026-07-19 正面目頭・横向き眼球の再修正

ユーザー添付4枚を基準に、正面目頭へ残っていた紫の旧虹彩片と、横向きで可動させた虹彩が
まつ毛・アイラインを切り取る回帰を修正した。原因は二つに分かれる。

- 正面: `eye_base_open.png` の元分割が白目を狭い楕円でしか置換せず、鼻側の白目に旧虹彩片が焼き付いていた
- 横向き: 虹彩上端の紫帯まで固定eye-lineへ分類し、反対に広い凸包の白目・肌を可動irisへ含めていた

正面は、虹彩なし参照画像から左右の鼻側白目ROIだけRGBを置換した。開眼ベースのalphaとROI外は
変更せず、ほかの正面13素材はv12とファイルバイト・RGBAが一致する。

横向きは全64フレームを次の3レイヤーへ再分離した。

- `eye-base`: 可動irisを包含し、有彩色の虹彩フリンジだけへ外側1px広げた安全消去領域
- `irises`: 独立HSV・凸包参照で下側まで回収し、白目・肌色を持ち出さない左右2眼の可動RGBA
- `eye-line`: 独立虹彩内部と排他にした上まつ毛・アイラインのlossless PNG。可動irisより前面へ固定表示

描画順は `neutral → eye-base → shifted irises → eye-line → blink → mouth-small`。横向き中央視線は
完成済みneutral眼だけを表示し、視線半径0.02〜0.10で分離眼へ切り替える。固定eye-lineは視線移動の
影響を受けず、上下左右へ動かしても元画素のRGBAを保持する。

確認成果物は `output/screenshots/eye-motion-matrix-v13.png`（正面・首左右・体左右×視線5方向）と
`assets/character-v13/previews/side-gaze-clean-v1.png`（横向き眼の拡大）に保存した。

## 現在の結論

ランタイムは `assets/character-v14/` の39素材。レビューの初期画面は
`連続首・体キー実験室（推奨）` で、AI演技を自動再生せず手動操作から始まる。
`headTurn / turn / gazeX / gazeY / mouthOpen / blink` を主要操作として表示する。

`headTurn` と `turn` は左右それぞれ16キーを持つ。移動中は現在値の前後2キーを連続表示し、
目標角へ到達して80ms静止すると最寄りの単一キーへ固定する。
首は追従率12/s、体は9/s。正面瞬きはopen / half / closedの3キーで、半閉じ中も虹彩座標と
下まぶたを固定する。`parameter / natural / full` では完成カット交換用の瞬き・
曲線ワイプを起動しない。右体は `front → 25 → 50 → 80 → full`、左体は
`front → generated-33 → generated-66 → full` をアンカーにする。既存左右3/4は終点として保持。

正面PNGの髪・身体を引っ張るparameterメッシュ変形と髪手動補正は停止。首・体16キーには
髪、首、肩を含む完成フレームをキャッシュしている。横向きは中央視線からlossless clean eye-base、
参照由来iris、fixed upper/lower eye-lineを常時表示する。これにより `gazeX / gazeY / blink / mouthOpen`
を追従させつつ、視線移動開始時の旧虹彩二重縁と可動まつ毛を防ぐ。

自動口形は `closed → micro → small → wide` の4キー。`mouth_open_micro` は62×18pxで、
閉じ口と小開口の間を埋める。A/U/E/Oは現状維持。I / いは今回のサンプルを基準に
52×15px・中心x=543の浅いピンク口へ更新し、白い歯面と黒い口腔は入れていない。
現在値と `vowel` はURLクエリから復元できる。

これはWebレビュー用の光学補間であり、CubismのArtMesh・デフォーマ・拡張補間ではない。
既定角度の動画素材を作る現在用途ではCubismは必須ではない。首角×体角×髪束物理×全母音を
任意に直積合成する段階では、隠し塗りを含む素材分割とCubismリギングへ移行する。

## v14で完了したもの

- `character-v13` を非破壊コピーし、`assets/character-v14/` と `scripts/build_character_v14.py` を追加
- 正面虹彩を承認済み基準から再構築し、外向きだった左右重心をv5完成眼の位置へ修正
- 正面虹彩下端を下まぶた近くまで延ばし、太い下側白目帯を解消
- 画面右＝キャラクター左眼へ白い月輪を復元
- 首・体×左右64フレームのirisをdark / luminous参照ペアで再描画
- 旧虹彩とフリンジを白目色で完全置換し、Telea補間由来の灰色・紫色ノイズを除去
- 上まつ毛だけを固定eye-lineへ分離し、旧虹彩下縁の固定点を除去
- 右体3/4終端の遠眼で、水平上まつ毛帯へ修正して切れ目3pxと縦の固定断片を除去
- 同じ遠眼の上アイライン中央にある暗紫AA 11pxを1行bridgeとして固定し、左右視線端の白い切れ目を除去
- 右体3/4終端の近眼で、上アイライン中央の暗紫AA 15pxと赤丸内の暗色76pxを固定し、右視線時の白い切れ込みを除去
- 左右体3/4のeye-baseを局所低彩度白目へ変更し、視線端の肌色リムを除去
- 横向き旧虹彩の消去を横方向へ限定し、下まぶた・肌への4px白塗りを撤去
- 遠眼で欠けた虹彩下半分を眼裂内で補い、固定下まぶたを前景へ復元して下側白隙間を解消
- 正面の画面右上まぶたを画面左上まぶたの鏡像へ調整し、下まぶた・眼サイズ・虹彩は保持
- 正面open / half / closed瞬きと固定4角を追加し、半閉じ中の虹彩座標を固定
- 正面口9種を形状不変のまま右へ4px移動し、bbox中心をx=547へ整列
- v14正面15レイヤーPSDを新規組立てし、全埋込RGBAをstandalone PNGと照合
- side `eye-base / irises / eye-line` をlossless PNGへ変更
- iris bbox境界を透明側へalpha featherし、硬い切断縁を除去
- 横向きsplit眼を中央視線からalpha 1で使い、neutral眼とのcross-fadeを廃止
- ランタイムの38素材URLを `character-v14` へ切り替え
- Parameter Study 08、README、技術方針、Web仕様、生成契約をv14へ更新

## v14の評価用成果物

- 正面中央視線: `output/screenshots/faceless-v14-front-gaze-center.png`
- 首右・体左neutral: `output/screenshots/faceless-v14-neck-right-neutral.png`、`faceless-v14-body-left-neutral.png`
- 横向き終端×中央・上下左右: `assets/character-v14/previews/side-gaze-clean-v2.png`
- 正面・首左右終端・体左右終端×中央・微小・最大4方向: `output/screenshots/eye-motion-matrix-v14.png`
- 右体3/4・右視線の上まつ毛拡大: `output/screenshots/body-right-right-eye-closeup-v14.png`
- 右体3/4・左右視線端の遠眼上アイライン: `output/screenshots/body-right-upper-eyeline-fixed-v14.png`
- 右体3/4・右視線端の近眼上アイライン: `output/screenshots/body-right-near-upper-eyeline-fixed-v14.png`
- 左右体3/4・左右視線端の白目縁拡大: `output/screenshots/body-side-sclera-rim-fixed-v14.png`
- 左右体3/4・視線3方向の下まぶた拡大: `assets/character-v14/previews/body-side-lower-lid-v1.png`
- 正面open / half / closed一覧: `assets/character-v14/previews/front-blink-keys-v1.png`
- Web正面半閉じ・閉眼: `output/screenshots/faceless-v14-front-blink-half.png`、`faceless-v14-front-blink-closed.png`
- PSD: `assets/character-v14/exports/tsukuyomi-nemuri-faceless-poc-v14.psd`
- 首右・体左の虹彩なしeye-base: `faceless-v14-neck-right-eye-base-clean.png`、`faceless-v14-body-left-eye-base-clean.png`
- 首右・体左の視線＋小開口: `faceless-v14-neck-right-gaze-mouth.png`、`faceless-v14-body-left-gaze-mouth.png`
- Webレビュー全体: `output/screenshots/parameter-review-v14-final.png`
- 16:9レビュー全体: `output/screenshots/parameter-review-v14-wide.png`

## v14の確認状況

- `.venv/bin/python test/test_eye_quality_v14.py -v`: 13 / 13成功
- `.venv/bin/python test/test_side_eye_assets.py -v`: v13回帰14 / 14成功（210.358秒）
- 全64フレームで左右2 iris、eye-base包含、eye-line非重複、紫色base残留0、soft alpha edgeを確認
- 全右向き32フレームで画面右の月輪率0.22以上、dark eyeとの差0.095以上を確認
- 左右終端4種で旧虹彩消去、可動irisへのまつ毛混入0、固定上まつ毛のline包含を確認
- `body/right` frame 15遠眼で視線X±5px時の未保護上まつ毛0px、元RGBAとの差分0pxを確認
- 同じ遠眼の暗紫AA bridge 11pxでbase/iris所有0、eye-line未復元0、視線X±5px時の元RGBA差分0px
- `body/right` frame 15近眼の暗紫AA bridge 15pxでbase/iris所有0、eye-line未復元0、視線X±5px時の元RGBA差分0px
- 同じ近眼の赤丸相当暗色76pxで、視線X+5px時の白目化を修正前56pxから0pxへ削減
- `body/left`・`body/right` frame 15の視線X±5pxで、露出白目縁80 / 77 / 90 / 86px、p90彩度は全条件14を確認
- 左右体終端×視線X -5 / 0 / +5の12眼条件で、虹彩直下白隙間median 0px・p90 1px以下
- 正面open / half / closedで4角固定、左右alpha鏡像、半閉じ中のiris transform不変を確認
- `npm test`: 69 / 69成功
- `npm run test:coverage`: 69 / 69成功、行96.47%、分岐89.90%、関数98.67%
- `npm run build`: 終了コード0。v14の39素材と `eyes_half_closed` を収録
- `python3 test/e2e_smoke.py`: 終了コード0、コンソールエラー0
- `python3 test/e2e_eye_matrix.py`: 終了コード0、5ポーズ×6視線＝30条件、コンソールエラー0
- 30条件は首・体の左右±1終端、中央、視線0.06の微小移動、上下左右±1を含む
- 静止A/BはSHA-256 `efe82a341edd7a1164b8a49bf73f5d0e1b74dd92b3f6770c6eddddd0b9c0d0a9` で一致し、`cmp`終了コード0
- `parameter-review-v14-final.png` でParameter Study 08とモデル表示を目視確認
- `faceless-v14-front-gaze-center.png` で正面視線・下側白目帯、`eye-motion-matrix-v14.png` で固定まつ毛・輪郭・白輪を目視確認
- `body-side-lower-lid-v1.png` で左右体・視線端の下側白隙間なし、`front-blink-keys-v1.png` で3キーを目視確認
- Live2D manifest 0 errors / hidden expression 10 warnings。v14 PSD 15レイヤーの埋込RGBA完全一致
- 本番ビルド `index-m23XuXp3.js` と39素材表示を `http://127.0.0.1:4173/?variant=parameter` で確認（HTTP 200）
- 公開、アップロード、配信は行っていない

## v13で完了したもの

- `character-v12` を非破壊コピーし、`assets/character-v13/` と `scripts/build_character_v13.py` を追加
- 首・体×左右の各16フレーム、計64フレームの `eye-base / irises / eye-line` atlasを再生成
- 光学フローで伝播した虹彩マスクを、実際の紫・暗色虹彩へX±12px・Y±6pxの範囲で再整列
- tightな可動iris、少し広い安全消去領域、固定eye-lineへ所有範囲を分離
- 独立HSV・凸包参照で下側虹彩を回収し、8px以上の全可動成分に虹彩内部への所属を要求
- 独立虹彩内部に属さない上まつ毛片11成分・計205pxを固定eye-lineへ戻し、正当な虹彩フリンジは維持
- 正面開眼ベースの鼻側白目2領域を虹彩なし参照から補修
- 中央視線はneutral完成眼だけを表示し、視線半径0.02〜0.10で分離眼を有効化
- 正面近傍0.035のdead zoneを追加し、微小入力によるside atlas汚染を防止
- 横向きの視線可動域をX±5px・Y±2pxへ制限し、強い横角度でも眼裂・上まつ毛から離れないよう抑制
- 横向きで視線を上下左右へ動かしても、元座標の虹彩が残る二重表示を解消
- 固定eye-lineを4本のlossless PNG atlasとして追加し、虹彩移動後に元画素で描画
- 紫色の下まぶた線はキャラクター固有の線画として固定eye-line側に保持
- 右体neutralの光学フロー由来だった鼻横の灰色パッチ2コマを局所肌色補修
- 正面の開眼ベース以外13素材、I / い、静止ロック、blink、mouth-small、評価済み終点、PSDはv12から保持
- ランタイムの38素材URLを `character-v13` へ切り替え
- Parameter Study 07、README、技術方針、Web仕様、生成契約をv13へ更新

## v13の評価用成果物

- 目頭旧虹彩片を除去した正面: `output/screenshots/faceless-v13-front-gaze-center.png`
- 添付相当の左体neutral: `output/screenshots/faceless-v13-body-left-neutral.png`
- 添付相当の首右neutral: `output/screenshots/faceless-v13-neck-right-neutral.png`
- 首右・体左×視線5方向: `assets/character-v13/previews/side-gaze-clean-v1.png`
- 正面・首・体5ポーズ×視線5方向: `output/screenshots/eye-motion-matrix-v13.png`
- 首右の虹彩なしeye-base: `output/screenshots/faceless-v13-neck-right-eye-base-clean.png`
- 体左の虹彩なしeye-base: `output/screenshots/faceless-v13-body-left-eye-base-clean.png`
- 首右中間・視線・小開口: `output/screenshots/faceless-v13-neck-right-gaze-mouth.png`
- 左体中間・視線・小開口: `output/screenshots/faceless-v13-body-left-gaze-mouth.png`
- Webレビュー全体: `output/screenshots/parameter-review-v13-final.png`
- 16:9レビュー全体: `output/screenshots/parameter-review-v13-wide.png`

## v13の確認状況

- `.venv/bin/python test/test_side_eye_assets.py -v`: 14 / 14成功（327.734秒）
- 正面開眼ベースの目頭旧虹彩片0、alpha・ROI外不変、ほかの正面13素材のバイト・RGBA一致を確認
- 合成テストで、伝播マスクが実虹彩から8pxずれた場合も再整列し、移動元に虹彩を残さないことを確認
- 実atlas全64フレームでeye-baseによるiris包含、左右2主眼、全142小成分の独立虹彩所属、固定線非重複、虹彩内部の固定帯0を確認
- 独立下側虹彩24,504pxのbase / iris欠落0・line混入0、独立上まつ毛9,669pxのline欠落0・base / iris混入0を確認
- 4方向×64フレームで固定アイラインの元RGBA完全一致を確認
- `npm run test:coverage`: 68 / 68成功、行96.43%、分岐89.90%、関数98.65%
- `npm run build`: 終了コード0。character-v13の38素材を収録
- `python3 test/e2e_smoke.py`: 終了コード0、コンソールエラー0
- `python3 test/e2e_eye_matrix.py`: 終了コード0、25条件を再撮影、コンソールエラー0
- 起動イントロのopacity 0とCSS / rendererサイズ安定を待ってから撮影し、全体UI画像はWebGL canvasを再合成して空白キャプチャを防止
- 全体UI画像のcanvas明部率を10%超で検査し、9:16 / 16:9ともモデルが実際に写ることを確認
- E2Eで正面近傍dead zone、横向き中央視線のneutral-only、視線移動時の3層眼、小開口、瞬きを確認
- 160ms離した静止A/BはSHA-256 `1aef03946b6ea16d5f2918a70fe2772d98d74c13ed5a997b35ab2751388651d9` で一致し、`cmp`でも完全一致
- Web本番ビルドを `http://127.0.0.1:4173/` でParameter Study 07として確認

## v13の残課題

- 動作中は隣接ラスターの光学補間なので、停止前の中間角には軟化が残り得る
- `parameter` は体系列表示中、独立した `headTurn` を同時合成せず体角を優先する
- 横向き口は閉じ口〜小開口。母音5種と大開口は正面専用
- 髪束別ArtMesh、慣性、衝突、Cubism物理演算は未実装
- PSDはv12から保持しており、Live2D Cubism実インポートは未確認

## v12で完了したもの

- 停止角でも前後2キーを重ね続けていた処理を、移動中だけの隣接補間へ変更
- 目標不変・角度差0.004以下を80ms保持すると最寄り1キーへ固定
- 固定中は横向き全体のidle/breath由来の平行移動・回転・拡縮をidentityへ固定
- 目標が0.0005を超えて変化した1フレーム目で固定解除
- 視線、瞬き、小開口パッチは静止ロック中も独立操作を維持
- ユーザーサンプル基準のI / いをImageGenで制作し、52×15pxへ整列
- `character-v11` を残し、`assets/character-v12/` と `scripts/build_character_v12.py` を追加
- v12の14レイヤーPSDを再組立てし、PSD内Iレイヤーとstandalone PNGのRGBA一致を検査
- Parameter Study 06、README、技術方針、Web仕様、E2Eをv12へ更新

## v12の評価用成果物

- 静止左体A/B: `output/screenshots/faceless-v12-body-left-static-a.png`、`faceless-v12-body-left-static-b.png`
- 新しいI / いのWeb表示: `output/screenshots/faceless-v12-front-mouth-i-reference.png`
- 新旧I / い比較: `assets/character-v12/previews/mouth-i-user-reference-v11-v12.png`
- 左体中間・視線・小開口: `output/screenshots/faceless-v12-body-left-gaze-mouth.png`
- 首右中間・視線・小開口: `output/screenshots/faceless-v12-neck-right-gaze-mouth.png`
- Webレビュー全体: `output/screenshots/parameter-review-v12-final.png`
- 16:9レビュー全体: `output/screenshots/parameter-review-v12-wide.png`
- PSD: `assets/character-v12/exports/tsukuyomi-nemuri-faceless-poc-v12.psd`

## v12の確認結果

- `npm test`: 65 / 65成功
- `npm run test:coverage`: 行96.33%、分岐89.77%、関数98.59%
- `npm run build`: 成功、character-v12の34素材を収録。`dist/assets` 13MiB
- `python3 test/e2e_smoke.py`: 終了コード0、コンソールエラー0
- E2Eで体-0.62停止時にframe 9だけ、upper alpha 0、side transform identityを確認
- 160ms離した静止A/B PNGのSHA-256が一致し、全画素差分bboxなし
- E2Eで入力再開1フレーム目のロック解除、横向き視線・小開口、IボタンとURL復元を確認
- I / いの実測bbox `[517,598,569,613]`、白系画素0、クロマ残り0
- v12メインmanifest: 0 errors、非表示差分に関する9 warnings。状態manifest9件: 0 errors、0 warnings
- v12 PSD: 1086×1448、14レイヤー、PSD内IとPNGのRGBA画素一致
- PSDニュートラル再読込: 可視RGB平均差の最大チャンネル0.12664258/255、差25超0.09596%
- Web本番ビルドを `http://127.0.0.1:4173/` でParameter Study 06として確認

## v12の残課題

- 動作中は隣接ラスターの光学補間なので、停止前の中間角には軟化が残り得る
- `parameter` は体系列表示中、独立した `headTurn` を同時合成せず体角を優先する
- 横向き口は閉じ口〜小開口。母音5種と大開口は正面専用
- 髪束別ArtMesh、慣性、衝突、Cubism物理演算は未実装
- PSDのLive2D Cubism実インポートは未確認

## v11で完了したもの

- 首追従を12/sへ上げ、60fps換算12フレームで入力の90%以上へ到達
- 体向きを左右16キーの連続系列へ変更し、離散カット、強制瞬き、ワイプを撤去
- 組み込みImageGenで左体33%・66%の専用アンカーを追加
- 首・体の各方向に `neutral / eye-base / irises / blink / mouth-small` atlasを生成
- 横向きの可動虹彩、瞬き、小開口を首系列と体系列の両方へ追加
- 旧28ポーズPNGをランタイムロードから除外し、34素材へ整理
- URL更新を90msデバウンスし、同一フレームのTexture再代入を抑止
- rendererのdevice pixel ratioを最大1.5へ制限
- `scripts/build_character_v11.py` と `prompts/parts-v11/generation-contract.md` を追加
- README、技術方針、Webレビュー仕様、E2Eをv11へ更新

## v11の評価用成果物

- 体の左右16キー一覧: `output/review/tsukuyomi-v11-body-keyframes.png`
- 左体中間・視線・小開口: `output/screenshots/faceless-v11-body-left-gaze-mouth.png`
- 首右中間・視線・小開口: `output/screenshots/faceless-v11-neck-right-gaze-mouth.png`
- 右体3/4終点: `output/screenshots/faceless-v11-body-right-endpoint.png`
- Webレビュー全体: `output/screenshots/parameter-review-v11-final.png`
- 16:9レビュー全体: `output/screenshots/parameter-review-v11-wide.png`

## v11の確認結果

- `npm test`: 61 / 61成功
- `npm run test:coverage`: 行96.20%、分岐90.00%、関数98.55%
- `npm run build`: 成功、character-v11の34素材を収録。`dist/assets` 13.05MiB
- `python3 test/e2e_smoke.py`: 終了コード0、コンソールエラー0
- E2Eで首12フレーム時90%以上追従、体24フレームの単調進行、transition常時idleを確認
- E2Eで首右0.72と体左-0.66の可動虹彩、小開口、瞬き、URL復元を確認
- 体左右16キー一覧、首右中間、体左中間、右3/4終点を目視確認

## v11の残課題

- `parameter` は体系列表示中、独立した `headTurn` を同時合成せず体角を優先する
- 横向き口は閉じ口〜小開口。母音5種と大開口は正面専用
- I / いはユーザー作成サンプル受領後に差し替える
- 16キーはラスター光学補間のため、中間角度にわずかな軟化がある
- 髪束別ArtMesh、慣性、衝突、Cubism物理演算は未実装

## v10で完了したもの

- 左右16キーの768×1024ニュートラルを4×4フレームの2 WebP atlasへ格納
- 瞬き・小開口は顔ROIだけの4 patch atlasとし、全画面の重複と矩形継ぎ目を回避
- ニュートラルで算出した双方向DIS optical flowを顔差分へ共用し、表情外の動きを一致
- parameterの首を完成カット閾値切替から連続キー補間へ変更し、首操作中の瞬きワイプを撤去
- 体向きはv9の評価済み右5段階・左3/4完成カットをそのまま保持
- 閉じ口と小開口の間に `mouth_open_micro` を追加し、自動口形を4キー化
- 組み込みImageGenでI / いを再編集し、白面を後処理で除去して58×20pxへ整列
- `character-v10` 48素材、14レイヤーPSD、再構築・PSD検証スクリプトを追加
- OpenCV依存を `requirements-asset-tools.txt` に固定
- 生成・整列契約を `prompts/parts-v10/generation-contract.md` に保存

## v10の評価用成果物

- Webレビュー全体: `output/screenshots/parameter-review-v10-wide.png`
- Web最終フレーム: `output/screenshots/parameter-review-v10-final.png`
- 左右16キー一覧: `output/review/tsukuyomi-v10-neck-keyframes.png`
- 首の実ブラウザ表示: `output/screenshots/faceless-v10-neck-continuous.png`
- 高解像度首キーの実ブラウザ表示: `output/screenshots/faceless-v10-neck-highres-neutral.png`
- 閉じ口・微開き・小開口・I一覧: `output/review/tsukuyomi-v10-mouth-keys.png`
- 微開き／Iの実ブラウザ表示: `output/screenshots/faceless-v10-mouth-micro.png`、`faceless-v10-mouth-vowel-i.png`
- PSD: `assets/character-v10/exports/tsukuyomi-nemuri-faceless-poc-v10.psd`
- PSD再オープン: `assets/character-v10/previews/psd-reopen-composite-v1.png`

## v10の確認結果

- `npm test`: 59 / 59成功
- `npm run test:coverage`: 行96.35%、分岐90.26%、関数98.51%
- `npm run build`: 成功、character-v10の48素材をbundleへ収録
- `python3 test/e2e_smoke.py`: 終了コード0、コンソールエラー0
- E2Eで左右首キーの単調進行、首操作中のtransition idle、微開き、I / い、体3/4、URL復元を確認
- v10メインPSDマニフェスト: 0 errors、非表示差分に関する9 warnings
- v10状態マニフェスト9件: すべて0 errors、0 warnings
- v10 PSD: 1086×1448、14レイヤー
- PSD再オープン: 可視RGB平均差の最大チャンネル0.12664258/255、差25超0.09596%
- 首右0.56の高解像度ニュートラル、微開き、I / い、左右16キー一覧、Web全体を目視確認

## v10の残課題

- 首16キーは光学補間キャッシュのため、中間角度にわずかな軟化がある
- 首向き中は完成ラスター由来なので、正面と同じ独立眼球・母音口にはならない
- 真のLive2D化には、髪・顔・首・身体の隠し塗りを含む分割とCubismデフォーマ設定が必要

## v9で完了したもの

- 組み込みImageGenでI / いを細め＋上歯ありへ再生成し、`(512,592)-(574,621)` へ数値整列
- 組み込みImageGenで右25%・50%・80%の中間完成絵と閉じ目＋小開口差分を生成
- 各中間絵を `neutral / blink / mouth-small / blink-mouth-small` の4状態へ構成
- 中間表情差分を固定目・口ROIへ限定し、ROI外をニュートラルと完全一致させた
- 右首3段階、右体5段階を目的角まで隣接順に進む遷移へ変更
- 同方向の隣接カットは直接ワイプし、左右をまたぐ要求だけ正面経由にした
- `character-v9` 41素材、13レイヤーPSD、再構築・PSD検証スクリプトを追加
- v8のA/U/E/O、正面、自然左右、全身3/4終点がバイト一致することを確認
- 生成・整列契約を `prompts/parts-v9/generation-contract.md` に保存

## v9の評価用成果物

- Webレビュー全体: `output/screenshots/parameter-review-v9-wide.png`
- Web最終フレーム（右50%）: `output/screenshots/parameter-review-v9-final.png`
- 右向き6段階一覧: `output/review/tsukuyomi-v9-right-turn-inbetweens.png`
- I / い修正前後: `output/review/tsukuyomi-v9-mouth-i-before-after.png`
- I / い実ブラウザ表示: `output/screenshots/faceless-v9-mouth-vowel-i.png`
- 首自然右／体3/4右: `output/screenshots/faceless-v9-neck-completed-cut.png`、`faceless-v9-body-completed-cut.png`
- PSD: `assets/character-v9/exports/tsukuyomi-nemuri-faceless-poc-v9.psd`
- PSD再オープン: `assets/character-v9/previews/psd-reopen-composite-v1.png`

## v9の確認結果

- `npm test`: 58 / 58成功
- `npm run test:coverage`: 行96.10%、分岐90.37%、関数98.48%
- `npm run build`: 成功、character-v9の41 PNG素材をbundleへ収録
- `python3 test/e2e_smoke.py`: 終了コード0、コンソールエラー0
- E2Eで右中間12レイヤー、首右50%、体右3/4終点、I / い、URL復元を確認
- v9メインPSDマニフェスト: 0 errors、非表示差分に関する8 warnings
- v9 PSD: 1086×1448、13レイヤー
- PSD再オープン: 可視RGB平均差の最大チャンネル0.12664258/255、差25超0.09596%
- 右向き6段階一覧、I / い修正前後、Web全体、右50%、右3/4を目視確認

## v9の残課題

- 左向きは中間コマ未制作。現在はv8の自然左・全身3/4左へ1段切替
- 各中間は完成ラスターであり、連続3D回転やCubismデフォーマではない
- 髪束分離・物理演算は、肩・服・身体の隠し塗りを含む素材再生成まで保留

## v8で完了したもの

- 組み込みImageGenで「あ・い・う・え・お」の口だけを個別生成
- クロマキー透過後、鼻中心 `x=543`、既存口中心 `y=606.5` 付近へ数値整列
- 正面用の中開き母音5種をPixiJSレイヤーと手動UIへ追加
- `parameter` の首を自然左右完成カット、体を全身3/4完成カットへ割当
- 首0.46／0.38、体0.60／0.52のヒステリシスと、正面経由の閉眼ワイプを共用
- parameterの髪・身体メッシュ変形を停止し、髪手動スライダーをUIから除外
- 正面、視線、首左右、体左右3/4のプリセットと母音を共有URLへ保存
- `character-v8` 29素材、13レイヤーPSD、再構築・PSD検証スクリプトを追加
- 生成・整列契約を `prompts/parts-v8/generation-contract.md` に保存

## v8の評価用成果物

- Webレビュー全体: `output/screenshots/parameter-review-v8-wide.png`
- Web最終フレーム: `output/screenshots/parameter-review-v8-final.png`
- 視線中央／右上: `output/screenshots/faceless-v8-gaze-center.png`、`faceless-v8-gaze-right-up.png`
- 首向き完成カット: `output/screenshots/faceless-v8-neck-completed-cut.png`
- 体向き完成カット: `output/screenshots/faceless-v8-body-completed-cut.png`
- 母音5種一覧: `output/review/tsukuyomi-v8-mouth-vowels-medium.png`
- 母音個別: `output/screenshots/faceless-v8-mouth-vowel-a.png` 〜 `mouth-vowel-o.png`
- PSD: `assets/character-v8/exports/tsukuyomi-nemuri-faceless-poc-v8.psd`
- PSD再オープン: `assets/character-v8/previews/psd-reopen-composite-v1.png`

## v8の確認結果

- `npm test`: 56 / 56成功
- `npm run test:coverage`: 行95.64%、分岐89.32%、関数98.48%
- `npm run build`: 成功、character-v8の29 PNG素材をbundleへ収録
- `python3 test/e2e_smoke.py`: 終了コード0、コンソールエラー0
- E2Eで首自然カット、体全身3/4、髪・身体メッシュ非変形、母音5種、URL復元を確認
- v8メインPSDマニフェスト: 0 errors、非表示差分に関する8 warnings
- 母音5状態マニフェスト: 5件とも0 errors、0 warnings
- v8 PSD: 1086×1448、13レイヤー、9,439,994 bytes
- PSD再オープン: 可視RGB平均差の最大チャンネル0.12664258/255、差25超0.09596%
- Web全体、首カット、体カット、母音表示のスクリーンショットを目視確認

## v7で完了したもの

- 組み込みImageGen編集で虹彩なし白目と左右固有の虹彩ペアを生成
- v6のまつ毛・目外形をpixel-exactで保持し、虹彩部分だけ生成白目へ置換
- PixiJSで虹彩レイヤーを目マスク内だけ上下左右へ移動
- `headTurn` を追加し、`turn` から首方向を分離
- 首、顔位置、首かしげ、体向きから髪追従量を算出し、左右長髪と頭頂を変形
- 手動パラメータUI、状態表示、プリセット、リセット、共有URL復元を追加
- `parameter / natural / full / soft / head-only` の5モードを共存
- 24素材の本番ビルド、Playwright E2E、8レイヤーPSD再オープンを確認
- 生成・整列契約を `prompts/parts-v7/generation-contract.md` に保存
- パラメータ仕様を `docs/parameter-review.md` に保存

## v7の評価用成果物

- Webレビュー全体: `output/screenshots/parameter-review-v7-wide.png`
- Web最終フレーム: `output/screenshots/parameter-review-v7-final.png`
- 視線中央／右上: `output/screenshots/faceless-v7-gaze-center.png`、`faceless-v7-gaze-right-up.png`
- 首＋髪: `output/screenshots/faceless-v7-neck-hair-link.png`
- 体だけ: `output/screenshots/faceless-v7-body-turn.png`
- 眼球分離前後: `output/review/tsukuyomi-v7-eye-split-before-after.png`
- 視線可動範囲: `output/review/tsukuyomi-v7-gaze-range.png`
- PSD: `assets/character-v7/exports/tsukuyomi-nemuri-faceless-poc-v7.psd`
- PSD再オープン: `assets/character-v7/previews/psd-reopen-composite-v1.png`

## v7の確認結果

- `npm test`: 51 / 51成功
- `npm run test:coverage`: 行95.85%、分岐89.56%、関数98.44%
- `npm run build`: 成功、character-v7の24 PNG素材をbundleへ収録
- `python3 test/e2e_smoke.py`: 終了コード0、コンソールエラー0
- E2Eで眼球だけの移動、首＋左右髪、体だけ、全5モード、URL復元を確認
- v7メインPSDマニフェスト: 0 errors、非表示差分に関する3 warnings
- v7状態マニフェスト: 3件とも0 errors（blinkは0 warnings、mouth 2件も0 warnings）
- v7 PSD: 1086×1448、8レイヤー、8,684,826 bytes
- PSD再オープン: 可視RGB平均差の最大チャンネル0.12664258/255、差25超0.09596%

## v6の状態（履歴）

v6では正面の閉じ口を中心 `x=543.0` の60×7pxへ更新し、線alphaを72%へ下げ、
中央下部へピンクのリップ芯を加えた。`natural` は頭部が先に左右へ向き、肩と上半身が
同方向へ少し追従する完成ポーズ。従来の全身3/4とレビューMP4も保持している。

## v6で完了したもの

- 組み込みImageGenで自然左右のニュートラル・瞬き・小開口を生成
- 自然左右の表情変更を固定ROIへ限定し、ROI外をニュートラルと完全一致させた
- v5の左右全身3/4×4状態をv6へコピーして保持
- `natural / full / soft / head-only` の4向きモードを実装
- `natural` は進入0.46／復帰0.38、`full` は従来の進入0.60／復帰0.52を維持
- 正面と自然左右、正面と全身3/4を、完全閉眼中の0.28秒曲線ワイプで交換
- PixiJSの自然左右alpha割り当てで検出した `natural-left/right` とcamelCase重み名の不一致を修正
- `character-v6` 24素材、レビュー画像、マニフェスト、8レイヤーPSDを生成
- 生成・整列契約を `prompts/parts-v6/generation-contract.md` に保存
- READMEとこのCONTEXTをv6の状態へ更新

## v6の評価用成果物

- 正面: `output/review/tsukuyomi-character-v6-front.png`
- 口の前後比較: `output/review/tsukuyomi-v6-mouth-before-after.png`
- 自然左右8状態: `output/review/tsukuyomi-character-v6-natural-expressions.png`
- 新レビューMP4: `output/video/tsukuyomi-natural-motion-review-v1.mp4`
- 新MP4抜粋: `output/review/tsukuyomi-natural-motion-video-contact-sheet-v1.png`
- 実ブラウザ最終状態: `output/screenshots/dev-browser-natural-motion-v6-final.png`
- 自然左: `output/screenshots/faceless-v6-natural-left.png`
- 自然右＋瞬き＋小口: `output/screenshots/faceless-v6-natural-right-combined.png`
- PSD: `assets/character-v6/exports/tsukuyomi-nemuri-faceless-poc-v6.psd`
- PSD再オープン合成: `assets/character-v6/previews/psd-reopen-composite-v1.png`

## v6の確認結果

- `npm test`: 47 / 47成功
- `npm run test:coverage`: 行95.67%、分岐89.35%、関数98.39%
- `npm run build`: 成功、24 PNG素材を本番bundleへ収録
- `python3 test/e2e_smoke.py`: 終了コード0、24素材、コンソールエラー0
- 実ブラウザで旧full左右、自然左右、自然右の複合表情、soft、head-onlyを確認
- MP4: H.264、720×1280、yuv420p、30fps、28.366667秒、851フレーム、7,096,542 bytes
- MP4は851フレームすべて復号成功。自然左右と旧full左右の瞬き・小口を収録
- 自然4回＋旧full4回のbridgeはすべて9フレーム
- v6 PSDマニフェスト: 0 errors、非表示差分に関する既知の3 warnings
- v6 PSD: 1086×1448、8レイヤー、8,675,582 bytes
- PSD再オープン: 可視RGB平均差の最大チャンネル0.12643272/255、差25超0.09596%

## v5までの経緯（履歴）

`models/` 直下の刷新サンプルを新しい正本とし、PixiJSランタイムを
`assets/character-v5/` の16素材へ切り替え済み。正面8素材に加え、左右3/4は
各方向で通常・瞬き・小開口・瞬き＋小開口の4状態を持つ。

ユーザー指摘だった「眉・まつ毛・目の線が太い」「目が小さく半開きで眠そう」への
初回修正で、開眼を128×82pxへ大きくしすぎ、白目が横へはみ出し、右目も外側へ
寄って不気味に見える問題が発生した。この案は撤回済み。

現在は細い暗藤色の眉と、サンプル準拠の110×61pxの横長アーモンド形開眼へ変更した。
サンプル固有の左右差を保持し、画面左（キャラクター右）は暗い藤黒の瞳、画面右
（キャラクター左）は淡い藤白の単一月輪を持つ発光瞳とした。開眼だけは左右を
水平反転コピーせず、左右別の生素材を使う。鼻中心 `x=543` に対して開眼中心は
画面左 `(443, 476.5)`、画面右 `(643, 476.5)`。左右とも中心から100pxで、外形の中心と
サイズを一致させた。追加調整では前版から目の縦幅を5.2%増やし、上まぶたのかかりを
弱め、眉を3px上げて「眠そう」ではなく穏やかな印象へ寄せた。口は既存v1素材を保ち、
小開口を70×41px、大開口を98×75pxへ縮小した。ASMR・朗読の自動口パクは開口率0.40を
上限として大開口へ遷移させず、大開口素材は手動QA用だけに残した。横向き側は入力が
大きくても小開口へ写像する。

正面↔全身3/4のカクつき対策では、旧実装にあった `|turn|=0.40..0.42` の全素材alpha 0と、
移行中のalpha総和1未満を撤廃した。完成PNG同士のクロスフェードも、輪郭・髪・
三日月・胴体の二重像とsource-overによる半透明化が出るため撤廃した。現在は正面頭部の
局所変形を先行させ、`|turn|>=0.60` で時間制御の瞬きを一度だけ開始する。完全閉眼を
先に保持してから、頭部先行・肩胴体遅行の曲線ステンシルワイプを0.28秒かけ、
正面／横向きの不透明な完成姿勢を30fps時約9フレームで段階交換する。ワイプ中の各画素は
どちらか一方の姿勢だけを表示し、弱い横ブラーは移動境界を馴染ませる目的だけに使う。
頭・三日月・肩が集中する画面中央ではワイプ速度を落とし、空の外縁では速める。
正面復帰は `|turn|<=0.52` としてヒステリシスを持たせ、境界付近の入力ノイズで姿勢が
点滅しない。角度を0.60付近で保持しても、交換後は瞬きが終了して開眼へ戻る。向きモードは
`full`（全身3/4）、`soft`（体正面の小さな首振り）、`head-only`（体正面の大きな首振り）
の3種。`turn` だけ3.6/sで遅く減衰補間する。非ゼロ角度でモードを変えた場合は、
現在モードのまま一度正面へ戻し、姿勢交換と瞬きが完了してから新モードを適用し、
保存した目標角へ戻す。

横向き4状態の論理ウェイトは総和1を維持し、PixiJSのsource-overで同じ実効寄与に
なるよう上層からalphaを逆算する。`neutral` は常時不透明な土台とし、残る3状態を
固定された目・口ROI内だけへマスク合成する。これにより表情の中間値でも、髪、衣装、
輪郭のアンチエイリアスが濃くなったり透けたりしない。開眼／閉眼の完成目が長く
重なって二重まぶたに見えないよう、横向き閉眼への補間はblink `0.68..0.94` の
短い区間へ集中させる。

旧 `character-v2`〜`v4`、旧レビュー画像、旧ビルドスクリプトは削除していない。

## v5の正本素材と優先順位

1. `models/ChatGPT Image 2026年7月17日 23_03_43 (1).png`
   - 正面の座標マスター
2. `models/ChatGPT Image 2026年7月17日 22_59_20.png`
   - 高精細な髪、大きな三日月ASMRマイク、衣装、閉じた本のペンダント
3. `models/ChatGPT Image 2026年7月17日 22_59_24.png`
   - 正面の色とキャラクター同一性
4. `models/ChatGPT Image 2026年7月17日 23_03_43 (2).png`
   - 左3/4
5. `models/ChatGPT Image 2026年7月17日 23_03_44 (3).png`
   - 右3/4
6. `models/ChatGPT Image 2026年7月17日 23_03_44 (4).png`
   - 閉眼
7. `models/ChatGPT Image 2026年7月17日 23_03_44 (5).png`
   - 開口
8. `23_06_34` / `23_12_07`
   - 体型とポーズの補助のみ。小さい旧三日月アクセサリーは採用しない

`models/bk/` はv4以前の旧モデル保存先で、v5ランタイムは参照しない。
`models/detail-memo.md` の「月灯りの朗読家」、大きな三日月、紺のケープ、
閉じた本のチャームを識別要素として維持する。

## v5で完成したもの

- 新しい正面のっぺらぼうベースを生成
- 開眼、閉眼、眉、閉じ口、小開口、大開口を個別生成
- 開眼v2の128×82px案と、丸く幼く見えたv4の120×70px案を不採用にし、開眼v5を110×58pxで採用
- 追加調整v6で横110pxを維持したまま縦61pxへ広げ、上まぶたを少し持ち上げて半目感を抑制
- 画面左の目が22px外側へズレた段階では一時的に反転コピーで位置を補正したが、虹彩差が消えるため最終版では不採用
- 前段の反転コピーで失われた左右虹彩差を復元し、開眼は左右別素材へ変更
- 開眼中心間隔を222pxから200pxへ狭め、中心Yを5px上へ移動
- 虹彩を約90%へ縮小し、左右とも正面一点を見るように素材を再生成
- 眉を前版から3px上げ、驚き眉にせず目との余白を調整
- 閉口を76×11px、小開口を70×41px、大開口を98×75pxへ整列
- 自動台本と音声RMSの開口率を0.40へ制限し、大開口を手動QA専用へ変更
- 全画像を1086×1448 RGBAへ正規化し、緑背景を透過
- 顔差分を正面実測座標へ再配置
- 口の状態ごとの上下ズレと、過大だった大開口を補正
- 閉じ口のクロマ由来の緑かぶりを暗藤色へ補正
- 左右3/4サンプルを直接透過して採用
- 左右3/4それぞれに瞬き、小開口、瞬き＋小開口をImageGenで追加
- 横向き編集は固定ROIだけを採用し、目口以外を元サンプルへ戻して全身ドリフトを防止
- 横向き4状態を双線形ウェイトで合成し、瞬きと口パクを独立制御
- 横向き表情を固定ROIへ限定し、通常姿勢を不透明のまま保持して輪郭のalpha変化を撤廃
- 首の局所変形を先行させ、完全閉眼中の0.28秒曲線ワイプで不透明な完成姿勢を段階交換
- 進入0.60／復帰0.52のヒステリシスを追加し、保持中の半目と入力ノイズによる再交換を防止
- 全身3/4、小さな首振り、体正面の大きな首振りの3モードを追加
- 非ゼロ角度のモード変更は中央復帰後に適用し、保存した目標角へ戻す
- 中立、まばたき、小開口、大開口のプレビューを作成
- 8レイヤーPSDと4状態マニフェストを作成
- PSDを再オープンし、レイヤー名、寸法、表示状態、可視RGBを確認
- PixiJSの16素材と顔座標を `character-v5` へ変更
- Playwright E2Eで実ブラウザ動作を確認

## 保存したノウハウ

- 再構築スクリプト: `scripts/build_character_v5.py`
- PSD再オープン検証: `scripts/verify_v5_psd.py`
- 生成・整列契約: `prompts/parts-v5/generation-contract.md`
- 採用ImageGen生出力: `assets/character-v5/raw/imagegen/`
- 参照コピー: `assets/character-v5/raw/source/`
- 整列座標: `scripts/build_character_v5.py` の `TARGETS`

重要な知見: ImageGenへ同じキャンバス・同じ座標を指定しても、採用生出力では
開眼が約100px下へ出て、口も状態ごとに上下位置が変わった。したがって生成座標を
そのままランタイムへ使わず、クロマ除去後に各パーツを分割し、実測座標へ再配置する。

## 評価用フルパス

- 正面レビュー:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/tsukuyomi-character-v5-front.png`
- 顔表情4状態:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/tsukuyomi-character-v5-face-expressions.png`
- 横向き8状態:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/tsukuyomi-character-v5-side-expressions.png`
- 横向きモーション動画:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/video/tsukuyomi-side-motion-review-v1.mp4`
- 横向きモーション動画フレーム一覧:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/tsukuyomi-side-motion-video-contact-sheet-v1.png`
- 全身切替bridge全フレーム:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/tsukuyomi-side-motion-bridge-contact-sheet-v1.png`
- 最終dev-browser状態:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/screenshots/dev-browser-side-motion-final.png`
- 実ブラウザ6状態（自動発話を含み、大開口を除外）:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/screenshots/dev-browser-v7-asmr-sheet.png`
- 覚醒感の修正比較（サンプル／修正前／修正後）:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/tsukuyomi-v7-awake-calm-review.png`
- 左右位置の修正前後比較:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/v5-eye-fix/eye-alignment-before-after.png`
- サンプル・縮小v2・採用v3比較:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/v5-eye-fix/eye-comparison-sample-v2-v3.png`
- UI全体:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/screenshots/faceless-poc-v5-wide.png`
- 正面中立合成:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/assets/character-v5/previews/live2d-neutral-v1.png`
- PSD再オープン合成:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/assets/character-v5/previews/psd-reopen-composite-v1.png`
- PSD:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/assets/character-v5/exports/tsukuyomi-nemuri-faceless-poc-v5.psd`
- マニフェスト:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/assets/character-v5/manifest-live2d-poc-v1.json`
- 正面ベース:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/assets/character-v5/master/front-faceless-v1.png`
- 左右3/4:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/assets/character-v5/poses/`
- 動画:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/video/tsukuyomi-faceless-poc-v5.mp4`
- 動画フレーム一覧:
  `/Users/yuyafujita/Projects/Tsukuyomi-nemuri/output/review/tsukuyomi-v5-video-contact-sheet.png`

ランタイムは `.codex` 配下やImageGenの一時出力を参照しない。

## PSDレイヤー構成

1. `front_faceless_base`
2. `eye_base_open`
3. `irises`
4. `eyes_closed`（非表示差分）
5. `brows_neutral`
6. `mouth_closed`
7. `mouth_open_small`（非表示差分）
8. `mouth_open_wide`（非表示差分）

ランタイムは上記8点に、左右それぞれ `neutral / blink / mouth-small /
blink-mouth-small` を加えた16素材。

## 確認済み

- `npm run test:coverage`: 46件成功
- カバレッジ: 行95.35%、分岐88.57%、関数98.28%
  - PixiJSのブラウザ専用エンジンはNodeカバレッジ対象外とし、Playwright E2Eで確認
- `npm run build`: 成功
- `test/e2e_smoke.py`: 終了コード0
- 姿勢切替の単体検証:
  - 10 / 30 / 60fpsで閉眼ピーク1.0、姿勢交換1回、交換後の開眼復帰を確認
  - 横向き保持中に瞬きが残留しない
  - `0.54..0.60` の境界ノイズで再交換しない
  - 非ゼロ角度でのモード変更は、正面復帰後に適用して保存目標へ戻る
- レイヤーマニフェスト:
  - メイン: 0 errors、非表示差分に関する3 warnings
  - 3状態マニフェスト: 各0 errors、0 warnings
- PSD:
  - 1086×1448
  - 8レイヤー
  - 約7.3MB
  - 再オープン可視RGB平均差の最大チャンネル0.12643908/255
  - 差25超の画素比0.096%
- dev-browser:
  - 16素材ロード、コンソールエラー0
  - 中立は開眼alpha 1.0、閉口alpha 1.0
  - まばたきは閉眼alpha 0.999998
  - 小開口は開眼alpha 1.0、小開口alpha 1.0
  - 自動台本・音声RMSでは大開口alpha 0
  - 手動QA時だけ大開口alpha 1.0
  - クリーン再読込時のロード失敗・コンソールエラー0
  - 左3/4、右3/4の該当グループalpha 1.0
  - `soft`: front 1.0、side 0、局所変形有効、顔移動2.92px
  - `head-only`: front 1.0、side 0、顔移動7.82px
  - `full`: 首の局所変形を先行し、閉眼ピークで不透明な正面／3/4姿勢を1回だけ交換
  - `full` のbridge中は正面／3/4を相補マスクで同時表示し、第3姿勢はalpha 0、弱い横ブラーだけを有効化
  - bridgeは10 / 30 / 60fpsで進捗が単調増加し、全区間blink 1.0、左右の直接遷移は正面経由へ制限
  - 左右3/4の通常・瞬き・小開口・複合状態を確認
  - 横向き中間表情の固定ROI外は基準フレームとの差分0
  - 自動発話と横向き表情はwide 0、向き・表情ウェイト総和1.0
- MP4:
  - 横向きモーション版はH.264、720×1280、yuv420p、30fps
  - 19.10秒、573フレーム、4,634,343 bytes
  - 573フレームすべて復号成功、フレームハッシュも573種類
  - 左右3/4の明示瞬き・小開口・複合、3つの向きモードを収録
  - 全フレームで自動大開口ウェイト0
  - 4回のbridgeはいずれも9フレーム。正面復帰前の完全閉眼保持は左右とも3フレーム、blink 1.0
  - 90×160 grayscaleの隣接MADは正面→左8.8572、左→正面8.3981、正面→右7.9205、右→正面8.1063。全体最大8.8572
  - 暗転、完成姿勢全体の二重露光、完全重複はなし。中央1〜2フレームでは月飾りや本ペンダントに横ブラー由来の軽い輪郭残像が見える
  - 独立目視監査はPASS。通常速度と0.25倍速、bridge全36フレームで確認し、暗転・二重像・縦割れなし。0.25倍速ではbridge中央の意図的なブラーが見えるが、通常速度では許容範囲

## 未実施・制約

- ユーザーによるv6最終レビューはこれから
- Live2D Cubismでの実インポート確認は未実施
- CubismのArtMesh、デフォーマ、パラメータ、物理演算は未設定
- 正面の髪、腕、肩、胴体は独立レイヤーではない
- 左右3/4は各方向4枚の完成状態で、正面のような目口の単独パーツ分割ではない
- `soft` と `head-only` は正面PNGの2D局所変形で、専用頭部素材やCubismによる立体回転ではない
- 開眼は虹彩込みの完成目なので、虹彩単独の視線移動は見た目上無効
- アップロード、公開、配信は未実施

## 次に進める場合

1. ユーザーが口の前後比較、自然左右8状態、新レビューMP4を確認する
2. OKならv6を確定し、既存fullとnaturalを用途別に使い分ける
3. 口の微調整が必要なら `scripts/build_character_v6.py` の `MOUTH_TARGET` とalpha・色だけを変更する
4. 視線移動が必要なら、白目＋まつ毛と虹彩を分離した追加素材を作る
5. 立体的な首回転が必要なら、体正面固定の左右頭部素材またはCubism用の頭部分割を追加する
6. CubismへPSDをインポートし、8レイヤーとテクスチャ分割を実確認する
