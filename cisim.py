"""
cisim.py — CIシミュレーション(ノイズバンドボコーダ + 電流拡散G行列 + 逆補償)の処理本体

CISim.ipynb のセクション3・5・7の処理を関数としてまとめたもの。
信号処理の中身は「元ノートブックと同じ挙動」のままにしてあり、

構成:
    1. CIConfig        … パラメータを1か所にまとめる
    2. 処理関数        … 帯域分割 / 包絡線抽出 / G行列 / キャリア / 再合成
    3. run_conditions  … 1つの入力から全条件(vocoder, spread, comp…)の出力をまとめて作る
    4. 刺激(入力音)    … テスト信号の生成・音声ファイルの読み込み・混合
    5. 保存ユーティリティ
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict

import numpy as np
import scipy.signal as signal
import soundfile as sf


# =====================================================================
# 1. パラメータ
# =====================================================================
@dataclass
class CIConfig:
    sr: int = 16000              # サンプリング周波数 [Hz]（ファイルはこれにリサンプリングして読む）
    n_ch: int = 22               # チャンネル数（= 電極数, Cochlear社準拠）
    fmin: float = 188.0          # 最低周波数 [Hz]
    fmax: float = 7939.0         # 最高周波数 [Hz]
    env_cut: float = 400.0       # 包絡線LPFのカットオフ [Hz]
    bp_order: int = 4            # バンドパスの次数（元: セクション3・7=4, セクション6=2）
    env_order: int = 2           # 包絡線LPFの次数
    spacing: float = 0.75        # 電極間隔 [mm]
    seed: int = 0                # キャリア乱数のシード（固定すると再現可能）
    causal: bool = False         #True=因果的(sosfilt)、False=ゼロ位相(sosfiltfilt)

    @property
    def boundaries(self) -> np.ndarray:
        """チャンネル境界周波数（対数等間隔, n_ch+1 個）"""
        return np.logspace(np.log10(self.fmin), np.log10(self.fmax), self.n_ch + 1)

    @property
    def electrode_x(self) -> np.ndarray:
        """電極位置 [mm]"""
        return np.arange(self.n_ch) * self.spacing

    def to_dict(self) -> dict:
        return asdict(self)


# =====================================================================
# 2. 処理関数
# =====================================================================
def _band_coeffs(lo_hz, hi_hz, sr, order):
    """バンドパス係数。範囲外なら None。"""
    low = np.clip(lo_hz / (sr / 2), 0.001, 0.999)
    high = np.clip(hi_hz / (sr / 2), 0.001, 0.999)
    if low >= high:
        return None
    return signal.butter(order, [low, high], btype="band", output="sos")


def _apply_filter(sos, x, cfg):
    if cfg.causal:
        return signal.sosfilt(sos,x)
    else:
        return signal.sosfiltfilt(sos,x)


def split_bands(x: np.ndarray, cfg: CIConfig) -> np.ndarray:
    """ステップ1: 22chのバンドパスフィルタで分割 → shape (n_ch, N)"""
    b_edges = cfg.boundaries
    out = np.zeros((cfg.n_ch, len(x)))
    for i in range(cfg.n_ch):
        sos = _band_coeffs(b_edges[i], b_edges[i + 1], cfg.sr, cfg.bp_order)
        if sos is None:
            continue
        out[i] = _apply_filter(sos, x, cfg)
    return out

def extract_envelope(sig: np.ndarray, cfg: CIConfig) -> np.ndarray:
    """ヒルベルト変換の絶対値 → LPF で平滑化"""
    env = np.abs(signal.hilbert(sig))
    sos = signal.butter(cfg.env_order, cfg.env_cut / (cfg.sr / 2), btype="low", output="sos")
    return _apply_filter(sos, env, cfg)


def extract_envelopes(x: np.ndarray, cfg: CIConfig) -> np.ndarray:
    """ステップ1+2: 入力音 → 各chの包絡線 shape (n_ch, N)"""
    bands = split_bands(x, cfg)
    return np.array([extract_envelope(b, cfg) for b in bands])


def make_G(cfg: CIConfig, lam: float) -> np.ndarray:
    """G[j,k] = exp(-|x_j - x_k| / λ)"""
    x = cfg.electrode_x
    return np.exp(-np.abs(x[:, None] - x[None, :]) / lam)


def normalize_rows(M: np.ndarray) -> np.ndarray:
    """行和が1になるよう正規化"""
    return M / np.sum(M, axis=1, keepdims=True)


def make_G_inv(G: np.ndarray, eps: float = 0.0, rownorm: bool = False) -> np.ndarray:
    """
    (G + εI)^{-1}
    eps=0      : 元ノート セクション5-2 と同じ（正規化済みGの素の逆行列）
    eps>0      : セクション5-3 と同じ正則化
    rownorm=True: セクション5-3・6 と同じく、逆行列をさらに行和で正規化
    """
    # TODO(修正候補①): rownorm=True だと G @ G_inv が単位行列にならず、それ自体が残差を生む。
    Gi = np.linalg.inv(G + eps * np.eye(G.shape[0]))
    return normalize_rows(Gi) if rownorm else Gi


def make_carriers(cfg: CIConfig, n_samples: int, mode: str = "noise",
                  rng: np.random.Generator | None = None) -> np.ndarray:
    """
    キャリア生成 shape (n_ch, N)
    mode='noise': 帯域ノイズ（ノイズボコーダ）
    mode='tone' : 中心周波数の正弦波（サイン波ボコーダ）
    """
    rng = rng if rng is not None else np.random.default_rng(cfg.seed)
    b_edges = cfg.boundaries
    t = np.arange(n_samples) / cfg.sr
    car = np.zeros((cfg.n_ch, n_samples))
    for i in range(cfg.n_ch):
        if mode == "noise":
            sos = _band_coeffs(b_edges[i], b_edges[i + 1], cfg.sr, cfg.bp_order)
            if sos is None:
                continue
            car[i] = _apply_filter(sos, rng.standard_normal(n_samples), cfg)
        elif mode == "tone":
            fc = np.sqrt(b_edges[i] * b_edges[i + 1])
            car[i] = np.sin(2 * np.pi * fc * t)
        else:
            raise ValueError(f"unknown carrier mode: {mode}")
    return car


def synthesize(env: np.ndarray, carriers: np.ndarray) -> np.ndarray:
    """ステップ4: 包絡線 × キャリア を全ch合計"""
    return np.sum(env * carriers, axis=0)


# =====================================================================
# 3. 全条件をまとめて実行
# =====================================================================
def run_conditions(x: np.ndarray, cfg: CIConfig, lam: float, eps: float = 0.0,
                   rownorm: bool = False, mode: str = "noise") -> dict:
    """
    1つの入力 x から比較用の全条件を作る。キャリアは全条件で共通（差が処理だけによるものになる）。

    返り値 dict:
      音声 (N,)        : 'vocoder'    拡散なし(G=I)。補償の比較基準
                         'spread'     拡散あり（現状のCI音）
                         'comp_ideal' 逆補償 → 拡散（負の包絡も許す＝物理的には不可能な理想）
                         'comp_clip'  逆補償の包絡を 0 以上にクリップしてから拡散（電流≥0の制約）
                         'precomp'    逆補償した刺激そのもの（拡散前）
      包絡 (n_ch, N)   : 'env', 'env_spread', 'env_comp_ideal', 'env_comp_clip', 'env_precomp'
      その他           : 'G', 'G_inv', 'neg_ratio'（precompで負になった割合）
    """
    env = extract_envelopes(x, cfg)
    car = make_carriers(cfg, len(x), mode, np.random.default_rng(cfg.seed))

    G = normalize_rows(make_G(cfg, lam))
    Gi = make_G_inv(G, eps=eps, rownorm=rownorm)

    pre = Gi @ env
    env_spread = G @ env
    env_comp_ideal = G @ pre
    env_comp_clip = G @ np.clip(pre, 0, None)

    return {
        # 音声
        "vocoder": synthesize(env, car),
        "spread": synthesize(env_spread, car),
        "comp_ideal": synthesize(env_comp_ideal, car),
        "comp_clip": synthesize(env_comp_clip, car),
        "precomp": synthesize(pre, car),
        # 包絡
        "env": env,
        "env_spread": env_spread,
        "env_comp_ideal": env_comp_ideal,
        "env_comp_clip": env_comp_clip,
        "env_precomp": pre,
        # その他
        "G": G,
        "G_inv": Gi,
        "neg_ratio": float(np.mean(pre < 0)),
    }


AUDIO_KEYS = ["vocoder", "spread", "comp_ideal", "comp_clip", "precomp"]


# =====================================================================
# 4. 刺激（入力音）
# =====================================================================
def _fade(x: np.ndarray, sr: int, ms: float = 10.0) -> np.ndarray:
    """両端にフェードを付けてクリックノイズを防ぐ"""
    n = min(int(sr * ms / 1000), len(x) // 2)
    if n > 0:
        w = np.hanning(2 * n)
        x = x.copy()
        x[:n] *= w[:n]
        x[-n:] *= w[n:]
    return x


def rms_normalize(x: np.ndarray, target_rms: float = 0.05) -> np.ndarray:
    r = np.sqrt(np.mean(x ** 2))
    return x * (target_rms / r) if r > 0 else x


def load_audio(path: str, sr: int, max_sec: float | None = None) -> np.ndarray:
    """音声ファイルを読み込み、モノラル化・リサンプリング"""
    try:
        import librosa
        x, _ = librosa.load(path, sr=sr, mono=True, duration=max_sec)
    except ImportError:  # librosa がなければ soundfile + resample_poly
        from math import gcd
        x, fs = sf.read(path, always_2d=True)
        x = x.mean(axis=1)
        if fs != sr:
            g = gcd(int(fs), int(sr))
            x = signal.resample_poly(x, sr // g, int(fs) // g)
        if max_sec:
            x = x[: int(max_sec * sr)]
    return rms_normalize(np.asarray(x, dtype=float))


def gen_tone(sr, freq=1000.0, dur=1.0):
    t = np.arange(int(sr * dur)) / sr
    return rms_normalize(_fade(np.sin(2 * np.pi * freq * t), sr))


def gen_sweep(sr, f0=100.0, f1=8000.0, dur=3.0):
    """対数スイープ：1本で全帯域の伝達特性を見る"""
    t = np.arange(int(sr * dur)) / sr
    f1 = min(f1, sr / 2 * 0.95)
    return rms_normalize(_fade(signal.chirp(t, f0, dur, f1, method="logarithmic"), sr))


def gen_noise(sr, dur=3.0, color="white", seed=1):
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(int(sr * dur))
    if color == "pink":  # 1/f 特性（周波数領域で整形）
        X = np.fft.rfft(n)
        f = np.fft.rfftfreq(len(n), 1 / sr)
        f[0] = f[1]
        n = np.fft.irfft(X / np.sqrt(f), len(n))
    return rms_normalize(_fade(n, sr))


def gen_click_train(sr, rate=100.0, dur=1.0):
    """クリック列：時間応答・時間ピッチの確認"""
    x = np.zeros(int(sr * dur))
    x[:: max(1, int(sr / rate))] = 1.0
    return rms_normalize(x)


def gen_sam(sr, fc=1000.0, fm=16.0, depth=1.0, dur=2.0):
    """正弦波振幅変調音：包絡LPFの変調伝達を確認"""
    t = np.arange(int(sr * dur)) / sr
    x = (1 + depth * np.sin(2 * np.pi * fm * t)) * np.sin(2 * np.pi * fc * t)
    return rms_normalize(_fade(x, sr))


def gen_harmonic(sr, f0=200.0, n_harm=20, dur=1.0):
    """調波複合音：ピッチ(F0)符号化の確認"""
    t = np.arange(int(sr * dur)) / sr
    x = sum(np.sin(2 * np.pi * f0 * k * t) for k in range(1, n_harm + 1) if f0 * k < sr / 2)
    return rms_normalize(_fade(x, sr))


def mix_at_snr(target: np.ndarray, masker: np.ndarray, snr_db: float) -> np.ndarray:
    """target に masker を指定SNRで混ぜる（2話者混合・雑音下音声用）"""
    n = min(len(target), len(masker))
    t, m = target[:n], masker[:n]
    pt, pm = np.mean(t ** 2), np.mean(m ** 2)
    m = m * np.sqrt(pt / (pm * 10 ** (snr_db / 10)))
    return rms_normalize(t + m)


# =====================================================================
# 4b. 「かたつむり」の楽器音（JVS-MuSiC modified_grouped と同じ旋律・タイミング）
# =====================================================================
# 旋律は楽譜のドレミ表記と、JVS-MuSiC 7名分の歌声のピッチ・オンセット実測を照合して決定。
# 1フレーズ = 12拍、四分音符 = 0.4 s（150 BPM）、歌い出し 2.41 s、3フレーズ × 2番。
# 音高は「ド」からの半音数（ド=0, レ=2, ミ=4, ファ=5, ソ=7, ラ=9, 高いド=12）。
# 各要素: (拍位置, 長さ[拍], 音高)
_KATATSUMURI_PHRASES = [
    # でんでんむしむし かたつむり（ソ ソソ ミ ド ドド レ ミ ミレ ド レ）
    [(0, 1, 7), (1, .5, 7), (1.5, .5, 7), (2, 1, 4), (3, 1, 0), (4, .5, 0), (4.5, .5, 0),
     (5, 1, 2), (6, 1, 4), (7, .5, 4), (7.5, .5, 2), (8, 1, 0), (9, 3, 2)],
    # おまえのあたまは どこにある（ミ ファソ ラ ソ ソソ ミ レ レド レ ミ）
    [(0, 1, 4), (1, .5, 5), (1.5, .5, 7), (2, 1, 9), (3, 1, 7), (4, .5, 7), (4.5, .5, 7),
     (5, 1, 4), (6, 1, 2), (7, .5, 2), (7.5, .5, 0), (8, 1, 2), (9, 3, 4)],
    # つのだせ やりだせ あたまだせ（付点8分の連続：ソ ド' ド' ソ ミ ソ ソ ミ ド ミ ミ レ ド）
    [(i * .75, .75, p) for i, p in enumerate([7, 12, 12, 7, 4, 7, 7, 4, 0, 4, 4, 2])] + [(9, 3, 0)],
]

# 各グループの「ド」の MIDI ノート番号（modified_grouped の実測から）
KATATSUMURI_DO = {"m_low": 46, "m_mid": 49, "m_high": 51,
                  "f_low": 57, "f_mid": 58, "f_high": 61}

KATATSUMURI_START = 2.41   # 歌い出し [s]
KATATSUMURI_QUARTER = 0.4  # 四分音符の長さ [s]（150 BPM）


def katatsumuri_notes(group: str = "f_low", start: float = KATATSUMURI_START,
                      quarter: float = KATATSUMURI_QUARTER, verses: int = 2):
    """[(開始 s, 長さ s, MIDIノート番号), ...] を返す"""
    do = KATATSUMURI_DO[group]
    notes, beat0 = [], 0.0
    for _ in range(verses):
        for ph in _KATATSUMURI_PHRASES:
            for b, d, p in ph:
                notes.append((start + (beat0 + b) * quarter, d * quarter, do + p))
            beat0 += 12
    return notes


def _instrument_tone(f0, dur, sr, timbre):
    """1音ぶんの合成音（加算合成）"""
    t = np.arange(int(dur * sr)) / sr
    if timbre == "piano":      # 倍音多め・鋭い立ち上がり・指数減衰
        amps = [1 / k for k in range(1, 16)]
        env = np.exp(-t * 3.0) * np.minimum(1, t / 0.005)
    elif timbre == "flute":    # 基音中心・やわらかい立ち上がり・持続
        amps = [1.0, 0.35, 0.12, 0.05]
        env = np.minimum(1, t / 0.06)
    elif timbre == "sine":     # 純音（倍音なし）
        amps = [1.0]
        env = np.minimum(1, t / 0.01)
    else:
        raise ValueError(f"unknown timbre: {timbre}")
    x = sum(a * np.sin(2 * np.pi * f0 * k * t) for k, a in enumerate(amps, start=1) if f0 * k < sr / 2)
    rel = min(int(0.02 * sr), len(t) // 2)          # 音の終わりのクリック防止
    if rel > 0:
        env = env.copy()
        env[-rel:] *= np.linspace(1, 0, rel)
    return x * env


def gen_katatsumuri(sr: int, group: str = "f_low", timbre: str = "piano",
                    total_sec: float = 31.2) -> np.ndarray:
    """歌声(modified_grouped)と同じ旋律・タイミング・調の楽器音を合成"""
    y = np.zeros(int(total_sec * sr))
    for st, d, m in katatsumuri_notes(group):
        f0 = 440.0 * 2 ** ((m - 69) / 12)
        tone = _instrument_tone(f0, d * 0.95, sr, timbre)   # 音符間にわずかな隙間
        i = int(st * sr)
        y[i:i + len(tone)] += tone[: len(y) - i]
    return rms_normalize(y)


def write_katatsumuri_midi(path: str, group: str = "f_low", program: int = 0) -> None:
    """GarageBand などに読み込める MIDI ファイル（1トラック, 150 BPM）を書き出す"""
    import struct
    tpq = 480
    bpm = 60 / KATATSUMURI_QUARTER
    ev = []  # (tick, データ)
    for st, d, m in katatsumuri_notes(group):
        on = int(round(st / KATATSUMURI_QUARTER * tpq))
        off = int(round((st + d * 0.95) / KATATSUMURI_QUARTER * tpq))
        ev += [(on, bytes([0x90, m, 90])), (off, bytes([0x80, m, 0]))]
    ev.sort(key=lambda e: (e[0], e[1][0] == 0x90))

    def vlq(n):
        out = [n & 0x7F]
        while n > 0x7F:
            n >>= 7
            out.insert(0, (n & 0x7F) | 0x80)
        return bytes(out)

    usec = int(60_000_000 / bpm)
    trk = vlq(0) + b"\xff\x51\x03" + usec.to_bytes(3, "big")      # テンポ
    trk += vlq(0) + b"\xff\x58\x04\x04\x02\x18\x08"                # 4/4拍子
    trk += vlq(0) + bytes([0xC0, program])                        # 音色
    last = 0
    for tick, data in ev:
        trk += vlq(tick - last) + data
        last = tick
    trk += vlq(0) + b"\xff\x2f\x00"
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 0, 1, tpq))
        f.write(b"MTrk" + struct.pack(">I", len(trk)) + trk)


# =====================================================================
# 5. 保存
# =====================================================================
def peak_normalize(x: np.ndarray) -> np.ndarray:
    # TODO(修正候補④): 元ノートと同じピーク正規化。レベル比較をするならRMS正規化の方が適切。
    return x / (np.max(np.abs(x)) + 1e-10)


def save_wavs(outdir: str, x_in: np.ndarray, out: dict, sr: int) -> None:
    """入力と各条件の音声を outdir に保存（聴き比べ用）"""
    os.makedirs(outdir, exist_ok=True)
    sf.write(os.path.join(outdir, "00_input.wav"), peak_normalize(x_in), sr)
    for i, k in enumerate(AUDIO_KEYS, start=1):
        sf.write(os.path.join(outdir, f"{i:02d}_{k}.wav"), peak_normalize(out[k]), sr)
