# 使用音源一覧

音源ファイル本体はGitに含めない（`.gitignore` で除外）。
このファイルの情報をもとに各自ダウンロードして `data/` 以下に配置する。

| ファイル名 | 種類 | 入手元（URL） | ライセンス | 元ファイル名・切り出し区間 | 備考 |
|---|---|---|---|---|---|
| speech_en/en_m01.wav | 英語音声・男性（ミッドランド方言） | [OpenSLR SLR83](https://www.openslr.org/83/) | CC BY-SA 4.0 | midlands_english_male/mim_04310_02107352323.wav（全長 5.55 s, 48 kHz） | 行番号 EN0001（Rainbow Passage 第1文）。女性と同一文 |
| speech_en/en_f01.wav | 英語音声・女性（北部方言） | [OpenSLR SLR83](https://www.openslr.org/83/) | CC BY-SA 4.0 | northern_english_female/nof_02484_00734838759.wav（全長 7.51 s, 48 kHz） | 行番号 EN0001（Rainbow Passage 第1文）。男性と同一文 |
| speech_ja/ja_m01.wav | 日本語音声・男性 | | | | |
| speech_ja/ja_f01.wav | 日本語音声・女性 | | | | |
| music_inst/katatsumuri_{piano,flute}_<グループ>.wav | 歌詞なし音楽（「かたつむり」旋律の合成音, 12本） | 自作（`cisim.gen_katatsumuri`） | 自作のため制限なし（旋律は1911年の文部省唱歌） | `midi/katatsumuri_<グループ>.mid` と同一の旋律 | 歌声 modified_grouped と同じ旋律・テンポ・調。再生成可能 |
| （予定）music_inst/katatsumuri_gb_<楽器>_<グループ>.wav | 歌詞なし音楽（GarageBand音源） | 自作（`midi/*.mid` を GarageBand で書き出し） | GarageBand 内蔵音源・自作 | エフェクトなしで書き出し | |
| music_vocal/katatsumuri_m_low_jvs045.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs045/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | F0比較（男性・低, 約145 Hz）／グループ代表 |
| music_vocal/katatsumuri_m_mid_jvs088.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs088/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | F0比較（男性・中, 約174 Hz）／グループ代表 |
| music_vocal/katatsumuri_m_high_jvs099.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs099/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | F0比較（男性・高, 約195 Hz）／グループ代表 |
| music_vocal/katatsumuri_f_low_jvs039.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs039/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | F0比較（女性・低, 約277 Hz）／グループ代表 |
| music_vocal/katatsumuri_f_mid_jvs061.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs061/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | F0比較（女性・中, 約294 Hz）／グループ代表 |
| music_vocal/katatsumuri_f_high_jvs085.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs085/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | F0比較（女性・高, 約349 Hz）／グループ代表 |
| music_vocal/katatsumuri_f_high_jvs010.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs010/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | 声質比較ペア（jvs060と類似度0.03） |
| music_vocal/katatsumuri_f_high_jvs060.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs060/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | 声質比較ペア（jvs010と類似度0.03） |
| music_vocal/katatsumuri_m_high_jvs041.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs041/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | 声質比較ペア（jvs100と類似度0.02） |
| music_vocal/katatsumuri_m_high_jvs100.wav | 歌詞あり音楽（童謡「かたつむり」） | [JVS-MuSiC](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_music) | 研究・非商用利用可、再配布不可 | jvs_music_ver1/jvs100/song_common/wav/modified_grouped.wav（全長, 切り出しなし） | 声質比較ペア（jvs041と類似度0.02） |
| noise/babble01.wav | 雑音 | | | | |

## 前処理
- サンプリング周波数：16 kHz（`cisim.load_audio` で読み込み時に変換）
- 長さ：約10秒に切り出し

## JVS-MuSiC について
- 出典：H. Tamaru, S. Takamichi, N. Tanji, H. Saruwatari, "JVS-MuSiC: free Japanese multispeaker singing-voice corpus," arXiv:2001.07044, 2020.
- `modified_grouped.wav`：テンポは全歌唱者で統一、ピッチは6グループ（男女×低/中/高）内で統一された版。
  → 歌詞・メロディ・テンポが同じで、グループ間ではF0だけが異なる。
- 歌唱者の選定：F0比較は付属 `similarity/*.csv` でグループ内平均類似度が最大の歌唱者、声質比較はグループ内で類似度が最小のペア。
- F0（pYINによる中央値）は jvs045 以外を実測。jvs045 は未計測（グループの統一値と同程度のはず）。
- 元の長さは約31〜33秒、24 kHz。混合時は `analysis.align` で時間合わせしてから重ねる。
- 成果を公開した際は作者（高道先生）に連絡するよう依頼あり。

## OpenSLR SLR83 について
- データセット：Crowdsourced high-quality UK and Ireland English Dialect speech data set（SLR83）
- 使用サブセット：midlands_english_male（ミッドランド・男性）、northern_english_female（北部・女性）
- ライセンス：CC BY-SA 4.0（各 raw フォルダの `LICENSE` を参照）。利用時は出典表記が必要
- 出典：I. Demirsahin, O. Kjartansson, A. Gutkin, C. Rivera, "Open-source Multi-speaker Corpora of the English Accents in the British Isles," Proc. 12th Language Resources and Evaluation Conference (LREC), pp. 6532–6541, 2020.
- 文の内容は各 raw フォルダの `line_index.csv`（行番号, ファイル名, 文）で確認できる
- 注意：男女で方言が異なる（北部 / ミッドランド）ため、男女差に方言差が含まれる
