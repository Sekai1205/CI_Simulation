# CI_simulation

人工内耳（CI）の聞こえをノイズボコーダで模擬し、**電流拡散**による劣化と、それを打ち消す**逆補償（事前補償）**の効果を、音声・音楽などの刺激で比較するコードです。

## ファイル構成

| パス | 内容 |
|---|---|
| `cisim.py` | 処理本体（帯域分割・包絡抽出・電流拡散行列 G・逆補償・合成・刺激生成・wav保存） |
| `analysis.py` | 比較指標（SNR, LSD, STOI, 包絡誤差など）と図の関数 |
| `run_experiments.ipynb` | 実行用ノートブック。設定 → 一括実行 → 表・図 |
| `CISim.ipynb` | 元になった試作ノートブック（参照用・実行不要） |
| `data/` | 入力音（git 管理外）。出典とライセンスは `data/SOURCES.md` |
| `midi/` | 楽器版「かたつむり」の MIDI |
| `figures/` | 論文用の図（ノートブックが出力。git 管理） |
| `results/` | 実行結果（ノートブックが出力。git 管理外。下記参照） |

## 実行方法

1. `uv sync` で環境を作る（Python 3.9, `my_research/.venv`）
2. `data/` に `data/SOURCES.md` の音源を置く
3. `run_experiments.ipynb` を「Restart → Run All」（全刺激で約20分）

## 処理の流れと条件名

```
入力 x ─ 22chに帯域分割 ─ 包絡 e ─┬─────────────── 合成 → vocoder    （拡散なし。比較の基準）
                                    ├─ G·e ─────────── 合成 → spread     （拡散あり＝補償なしのCI）
                                    └─ 逆補償 p ─ G·p ─ 合成 → comp_*    （補償してから拡散）
```

- 22ch（188–7939 Hz）、電極間隔 0.75 mm、拡散 G_jk = exp(−|x_j − x_k| / λ)（行和で正規化）
- 「合成」は各chの包絡 × キャリアの和。キャリアは **noise**（帯域雑音）か **tone**（各chの中心周波数の正弦波）
- 包絡と補償の計算は共通で、キャリアだけを差し替えて両方を出力する

| 条件名 | 意味 |
|---|---|
| `input` | 入力音そのもの |
| `vocoder` | 拡散なし（G = I）。補償の目標で、残差の基準 |
| `spread` | 拡散あり・補償なし（現状のCIに相当） |
| `comp_ideal` | p = G⁻¹e。負の刺激も許す理想（物理的には不可能） |
| `comp_clip` | p = max(G⁻¹e, 0)。負の部分を0にしてから拡散 |
| `comp_nnls` | p ≥ 0 の制約付き最小二乗（NNLS）で求めた補償 |
| `precomp` | 補償した刺激 p そのもの（拡散前）。参考 |

## results/ の構成

```
results/
└── seed0_eps0/                    ← 条件タグ = seed{乱数シード}_eps{正則化ε}。変えると別フォルダ（上書きされない）
    ├── metrics.csv                ← 全刺激 × λ × キャリア × 比較ペアの指標（下記）
    ├── noise/                     ← キャリア = 帯域雑音
    │   └── <刺激名>/              ← sweep, sam_fm16, en_m01, en_f01, song_m_low, song_f_high, piano_f_high
    │       └── lam<λ>/            ← lam2, lam5, lam9（電流拡散の広さ [mm]）
    │           ├── 00_input.wav
    │           ├── 01_vocoder.wav
    │           ├── 02_spread.wav
    │           ├── 03_comp_ideal.wav
    │           ├── 04_comp_clip.wav
    │           ├── 05_precomp.wav
    │           ├── 06_comp_nnls.wav
    │           └── residual/      ← 差の信号（各条件 − vocoder）。「ザー」の正体を聴く用
    │               ├── res_spread_minus_vocoder.wav
    │               ├── res_comp_ideal_minus_vocoder.wav   ← ほぼ無音になるはず
    │               ├── res_comp_clip_minus_vocoder.wav
    │               └── res_comp_nnls_minus_vocoder.wav
    └── tone/                      ← キャリア = 正弦波。中身は noise/ と同じ構成
```

**音量について**
- 同じフォルダ内の `00`〜`06` は、すべて同じ RMS にそろえてから、共通の倍率で保存しています。音量差を気にせずに聴き比べられます。
- `residual/` の差の信号はそろえていません。差そのものの大きさを残すためで、`metrics.csv` の `residual_db` がその大きさです。

**刺激名**

| 刺激名 | 内容 |
|---|---|
| `sweep` | 100→8000 Hz のスイープ（3 s） |
| `sam_fm16` | 1 kHz を 16 Hz で振幅変調した音 |
| `en_m01` / `en_f01` | 英語音声（男性 / 女性、同じ文） |
| `song_m_low` / `song_f_high` | 歌声「かたつむり」（男性・低め / 女性・高め、最初の10 s） |
| `piano_f_high` | `song_f_high` と同じ旋律のピアノ（最初の10 s） |

`results/` の直下にある `en_m01/` などの条件タグのないフォルダや `noise_seed0_eps0/` は、古い版の出力です。現在のコードはこれらを作らないので、削除して構いません。

## metrics.csv の列

1行が「キャリア × 刺激 × λ × 比較ペア（ref, test）」の1組です。

| 列 | 意味 | 良い向き |
|---|---|---|
| `mode` | キャリア（noise / tone） | |
| `stim`, `lam` | 刺激名、拡散の広さ λ [mm] | |
| `ref`, `test` | 比較の基準と対象（例: ref=vocoder, test=comp_nnls） | |
| `neg_ratio` | G⁻¹e が負になったサンプルの割合 | |
| `lag_ms` | 時間ずれ（相互相関で合わせた量） | |
| `snr_db` | ref を信号、差を雑音とみなした SNR | 大 |
| `lsd_db` | 対数スペクトル距離 | 小 |
| `ltas_rmse_db` | 長時間平均スペクトルの差（CI帯域） | 小 |
| `coh_mean` | コヒーレンスの帯域平均（0–1） | 大 |
| `env_corr_mean`, `env_corr_min` | chごとの包絡の相関（平均・最小） | 大 |
| `stoi` | 明瞭度指標 STOI（0–1。音声のみ意味あり） | 大 |

以下の列は **ref = vocoder の行だけ** に値が入ります（それ以外は空欄）。包絡どうしを直接比べるので、キャリアの乱数に左右されません。

| 列 | 意味 | 良い向き |
|---|---|---|
| `env_rel_err_db` (`_mean`, `_max`) | 包絡の相対誤差（全体 dB／chごとの平均・最大） | 小 |
| `profile_corr` | 各時刻のch方向の形（スペクトルの山谷）の相関 | 大 |
| `contrast_ratio` | ch方向の山谷の深さ（変動係数）の比。1 = 基準と同じ | 1 に近い |
| `flatness` / `flatness_ref` | ch方向の平坦度（test／基準）。1 に近いほど平ら＝山谷が消えている | |
| `residual_db` | 差の信号の大きさ（基準に対する dB）。`residual/` の wav と対応 | 小 |

## figures/

| ファイル | 内容 |
|---|---|
| `contrast_ratio_{main,all}.png` | λ に対するコントラスト比（main = 代表4刺激, all = 全刺激） |
| `profile_corr_{main,all}.png` | λ に対する形の相関 |
| `env_rel_err_db_{main,all}.png` | λ に対する包絡誤差 |
| `stoi.png` | 英語音声の STOI |

図はすべて noise キャリアの結果です。

## 波形・スペクトログラムを見る

`run_experiments.ipynb` のセクション5と5bで、刺激・λ・キャリアを選んで描画します。

- 波形は `an.plot_waveforms`。全体と拡大区間を並べて描きます。
- スペクトログラムは `an.plot_spectrograms`。
- wav ファイルを直接見たい場合は、Audacity などで開けば波形とスペクトログラムを表示できます。
