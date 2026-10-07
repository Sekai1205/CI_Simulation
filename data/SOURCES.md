# 使用音源一覧

音源ファイル本体はGitに含めない（`.gitignore` で除外）。
このファイルの情報をもとに各自ダウンロードして `data/` 以下に配置する。

| ファイル名 | 種類 | 入手元（URL） | ライセンス | 元ファイル名・切り出し区間 | 備考 |
|---|---|---|---|---|---|
| speech_en/en_m01.wav | 英語音声・男性 | | | | |
| speech_en/en_f01.wav | 英語音声・女性 | | | | |
| speech_ja/ja_m01.wav | 日本語音声・男性 | | | | |
| speech_ja/ja_f01.wav | 日本語音声・女性 | | | | |
| music_inst/inst01.wav | 歌詞なし音楽 | | | | |
| music_vocal/vocal01.wav | 歌詞あり音楽 | | | | |
| noise/babble01.wav | 雑音 | | | | |

## 前処理
- サンプリング周波数：16 kHz（`cisim.load_audio` で読み込み時に変換）
- 長さ：約10秒に切り出し
