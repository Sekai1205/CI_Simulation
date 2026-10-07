"""
cisim.py — CIシミュレーション(ノイズバンドボコーダ + 電流拡散G行列 + 逆補償)の処理本体

CISim.ipynb のセクション3・5・7の処理を関数としてまとめたもの。
信号処理の中身は「元ノートブックと同じ挙動」のままにしてあり、
改善候補の箇所には  # TODO(修正候補○)  のコメントを付けている（後で解説しながら直す前提）。

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
    # TODO(修正候補⑤): ba形式は低い正規化周波数で数値的に不安定になりやすい
    #                  （セクション6でNaNが出た原因候補）。sos形式 + sosfilt を検討。
    return signal.butter(order, [low, high], btype="band")


def split_bands(x: np.ndarray, cfg: CIConfig) -> np.ndarray:
    """ステップ1: 22chのバンドパスフィルタで分割 → shape (n_ch, N)"""
    b_edges = cfg.boundaries
    out = np.zeros((cfg.n_ch, len(x)))
    for i in range(cfg.n_ch):
        ba = _band_coeffs(b_edges[i], b_edges[i + 1], cfg.sr, cfg.bp_order)
        if ba is None:
            continue
        # TODO(修正候補⑤): lfilter(因果的) と filtfilt(ゼロ位相) が元ノートでは混在。どちらかに統一。
        out[i] = signal.lfilter(*ba, x)
    return out


def extract_envelope(sig: np.ndarray, cfg: CIConfig) -> np.ndarray:
    """ヒルベルト変換の絶対値 → LPF で平滑化"""
    env = np.abs(signal.hilbert(sig))
    b, a = signal.butter(cfg.env_order, cfg.env_cut / (cfg.sr / 2), btype="low")
    return signal.lfilter(b, a, env)


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
            ba = _band_coeffs(b_edges[i], b_edges[i + 1], cfg.sr, cfg.bp_order)
            if ba is None:
                continue
            car[i] = signal.lfilter(*ba, rng.standard_normal(n_samples))
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
