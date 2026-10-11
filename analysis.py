"""
analysis.py — 比較・解析関数

ルール:
  * 数値指標は  f(ref, test, cfg) -> dict  の形にそろえ、METRICS に登録する。
    → 実行ノートブックのループが自動で全刺激×全条件に適用し、表(DataFrame)にまとめる。
  * 図は  plot_xxx(...)  として別に用意（ループの外で、見たい組み合わせだけ描く）。

新しい指標を足すときは、関数を書いて METRICS に1行追加するだけ。
"""
from __future__ import annotations

import numpy as np
import scipy.signal as signal
import matplotlib.pyplot as plt

from cisim import CIConfig, extract_envelopes


# =====================================================================
# 前処理
# =====================================================================
def align(ref: np.ndarray, test: np.ndarray, sr: int, max_lag_ms: float = 50.0):
    """
    相互相関で test を ref に時間合わせする（フィルタ遅延の除去）。
    返り値: (ref_cut, test_cut, lag_ms)   lag>0 は test が遅れている
    """
    n = min(len(ref), len(test))
    r, t = ref[:n], test[:n]
    max_lag = int(sr * max_lag_ms / 1000)
    cc = signal.correlate(t, r, mode="full", method="fft")
    lags = signal.correlation_lags(len(t), len(r), mode="full")
    sel = np.abs(lags) <= max_lag
    lag = int(lags[sel][np.argmax(np.abs(cc[sel]))])
    if lag > 0:
        r, t = r[: n - lag], t[lag:]
    elif lag < 0:
        r, t = r[-lag:], t[: n + lag]
    return r, t, 1000 * lag / sr


def _rms(x):
    return np.sqrt(np.mean(x ** 2)) + 1e-12


def _match_level(ref, test):
    """test を ref と同じRMSにそろえる"""
    return test * (_rms(ref) / _rms(test))


# =====================================================================
# 数値指標（すべて f(ref, test, cfg) -> dict）
# =====================================================================
def m_lag(ref, test, cfg: CIConfig):
    _, _, lag_ms = align(ref, test, cfg.sr)
    return {"lag_ms": lag_ms}


def m_snr(ref, test, cfg: CIConfig):
    """時間合わせ・レベル合わせ後の SNR（ref を信号, 差分を雑音とみなす）"""
    r, t, _ = align(ref, test, cfg.sr)
    t = _match_level(r, t)
    return {"snr_db": 10 * np.log10(np.sum(r ** 2) / (np.sum((r - t) ** 2) + 1e-12))}


def m_lsd(ref, test, cfg: CIConfig, nperseg: int = 512):
    """対数スペクトル距離 [dB]（小さいほどスペクトルが近い）"""
    r, t, _ = align(ref, test, cfg.sr)
    t = _match_level(r, t)
    _, _, R = signal.stft(r, cfg.sr, nperseg=nperseg)
    _, _, T = signal.stft(t, cfg.sr, nperseg=nperseg)
    lr = 10 * np.log10(np.abs(R) ** 2 + 1e-10)
    lt = 10 * np.log10(np.abs(T) ** 2 + 1e-10)
    return {"lsd_db": float(np.mean(np.sqrt(np.mean((lr - lt) ** 2, axis=0))))}


def m_ltas(ref, test, cfg: CIConfig, nperseg: int = 1024):
    """長時間平均スペクトル（LTAS）の差 [dB]（CI帯域内のRMS）"""
    f, pr = signal.welch(ref, cfg.sr, nperseg=nperseg)
    _, pt = signal.welch(_match_level(ref, test), cfg.sr, nperseg=nperseg)
    band = (f >= cfg.fmin) & (f <= cfg.fmax)
    d = 10 * np.log10(pt[band] + 1e-12) - 10 * np.log10(pr[band] + 1e-12)
    return {"ltas_rmse_db": float(np.sqrt(np.mean(d ** 2)))}


def m_coherence(ref, test, cfg: CIConfig, nperseg: int = 1024):
    """
    コヒーレンス γ²(f) の CI帯域平均。
    1 に近い → 線形な関係（補償で戻せる）、低い → 雑音・非線形（線形補償では戻らない）
    """
    r, t, _ = align(ref, test, cfg.sr)
    f, c = signal.coherence(r, t, cfg.sr, nperseg=nperseg)
    band = (f >= cfg.fmin) & (f <= cfg.fmax)
    return {"coh_mean": float(np.mean(c[band]))}


def m_env_corr(ref, test, cfg: CIConfig):
    """両音声を同じフィルタバンクで包絡に分解し、ch ごとの相関の平均・最小"""
    r, t, _ = align(ref, test, cfg.sr)
    er, et = extract_envelopes(r, cfg), extract_envelopes(t, cfg)
    cs = [np.corrcoef(a, b)[0, 1] for a, b in zip(er, et) if np.std(a) > 0 and np.std(b) > 0]
    return {"env_corr_mean": float(np.mean(cs)) if cs else np.nan,
            "env_corr_min": float(np.min(cs)) if cs else np.nan}


def m_stoi(ref, test, cfg: CIConfig):
    """STOI（明瞭度指標, 0〜1）。pip install pystoi が必要。音声の刺激でのみ意味がある。"""
    try:
        from pystoi import stoi
    except ImportError:
        return {"stoi": np.nan}
    r, t, _ = align(ref, test, cfg.sr)
    return {"stoi": float(stoi(r, t, cfg.sr, extended=False))}


METRICS = {
    "lag": m_lag,
    "snr": m_snr,
    "lsd": m_lsd,
    "ltas": m_ltas,
    "coherence": m_coherence,
    "env_corr": m_env_corr,
    "stoi": m_stoi,
}


def compute_metrics(ref, test, cfg: CIConfig, which=None) -> dict:
    """METRICS をまとめて計算して1つの dict に"""
    row = {}
    for name, f in METRICS.items():
        if which is None or name in which:
            row.update(f(ref, test, cfg))
    return row


def env_error(env_ref: np.ndarray, env_test: np.ndarray) -> dict:
    """
    包絡行列どうしの直接比較（キャリアの乱数に左右されない）。
    例: env_error(out['env'], out['env_comp_clip'])
    """
    num = np.sum((env_test - env_ref) ** 2, axis=1)
    den = np.sum(env_ref ** 2, axis=1) + 1e-12
    rel = num / den
    return {"env_rel_err_mean": float(np.mean(rel)),
            "env_rel_err_max": float(np.max(rel)),
            "env_rel_err_db": float(10 * np.log10(np.sum(num) / np.sum(den) + 1e-12))}


def env_contrast(env_ref, env_test, decim=8):
    ref = env_ref[:, ::decim]
    test = env_test[:, ::decim]
    sum_ref = ref.sum(axis=0)
    valid = sum_ref >= (max(sum_ref) * 0.01)
    ref = ref[:, valid]
    test = test[:,valid]
    a = ref - ref.mean(axis=0)
    b = test - test.mean(axis=0)
    num = (a * b).sum(axis=0)
    den = np.sqrt((a ** 2).sum(axis=0) * (b ** 2).sum(axis=0))
    profile_corr = np.mean(num /den)
    cv_ref = ref.std(axis=0) / ref.mean(axis=0)
    cv_test = test.std(axis=0) / test.mean(axis=0)
    contrast_ratio = np.median(cv_test / cv_ref)
    return {
        "profile_corr": profile_corr,
        "contrast_ratio": contrast_ratio
    }

# =====================================================================
# 図
# =====================================================================
def plot_spectrograms(signals: dict, sr: int, nperseg: int = 512, fmax: float = 8000,
                      diff_pair: tuple | None = None, title: str = ""):
    """
    signals: {'input': x, 'vocoder': ..., 'comp_clip': ...} を縦に並べて表示。
    diff_pair=('vocoder','comp_clip') を渡すと、差分スペクトログラム [dB] を最下段に追加。
    """
    keys = list(signals)
    n = len(keys) + (1 if diff_pair else 0)
    fig, axes = plt.subplots(n, 1, figsize=(10, 2.2 * n), sharex=True)
    axes = np.atleast_1d(axes)
    specs = {}
    for ax, k in zip(axes, keys):
        f, t, S = signal.stft(signals[k], sr, nperseg=nperseg)
        specs[k] = 20 * np.log10(np.abs(S) + 1e-10)
        im = ax.pcolormesh(t, f, specs[k], shading="auto", cmap="magma",
                           vmin=specs[k].max() - 80, vmax=specs[k].max())
        ax.set_ylim(0, fmax)
        ax.set_ylabel(f"{k}\nHz")
        fig.colorbar(im, ax=ax, label="dB")
    if diff_pair:
        a, b = diff_pair
        m = min(specs[a].shape[1], specs[b].shape[1])
        d = specs[b][:, :m] - specs[a][:, :m]
        im = axes[-1].pcolormesh(t[:m], f, d, shading="auto", cmap="RdBu_r", vmin=-20, vmax=20)
        axes[-1].set_ylim(0, fmax)
        axes[-1].set_ylabel(f"{b} − {a}\nHz")
        fig.colorbar(im, ax=axes[-1], label="ΔdB")
    axes[-1].set_xlabel("Time (s)")
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def plot_ltas(signals: dict, sr: int, nperseg: int = 1024, title: str = ""):
    """長時間平均スペクトル（RMSそろえ）を重ね描き"""
    fig, ax = plt.subplots(figsize=(9, 4))
    ref = next(iter(signals.values()))
    for k, x in signals.items():
        f, p = signal.welch(_match_level(ref, x), sr, nperseg=nperseg)
        ax.semilogx(f[1:], 10 * np.log10(p[1:] + 1e-12), label=k, lw=1.2)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("PSD (dB)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    ax.set_title(title or "LTAS")
    fig.tight_layout()
    return fig


def plot_coherence(ref: np.ndarray, tests: dict, sr: int, nperseg: int = 1024, title: str = ""):
    """ref と各 test のコヒーレンス γ²(f)"""
    fig, ax = plt.subplots(figsize=(9, 3.5))
    for k, x in tests.items():
        r, t, _ = align(ref, x, sr)
        f, c = signal.coherence(r, t, sr, nperseg=nperseg)
        ax.semilogx(f[1:], c[1:], label=k)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Coherence γ²")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    ax.set_title(title or "Coherence")
    fig.tight_layout()
    return fig


def plot_env_error(env_ref: np.ndarray, env_test: np.ndarray, cfg: CIConfig, title: str = ""):
    """
    包絡の誤差ヒートマップ（ch × 時間）：補償誤差が「どのchのどの時刻」に出るかを見る
    """
    err = env_test - env_ref
    t = np.arange(err.shape[1]) / cfg.sr
    v = np.max(np.abs(err)) + 1e-12
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw={"width_ratios": [4, 1]})
    im = axes[0].imshow(err, aspect="auto", origin="lower", cmap="RdBu_r", vmin=-v, vmax=v,
                        extent=[t[0], t[-1], 0.5, cfg.n_ch + 0.5])
    axes[0].set_xlabel("Time (s)")
    axes[0].set_ylabel("Channel")
    fig.colorbar(im, ax=axes[0], label="env error")
    rel = np.sum(err ** 2, axis=1) / (np.sum(env_ref ** 2, axis=1) + 1e-12)
    axes[1].barh(np.arange(1, cfg.n_ch + 1), 10 * np.log10(rel + 1e-12))
    axes[1].set_xlabel("rel. error (dB)")
    axes[1].set_ylim(0.5, cfg.n_ch + 0.5)
    fig.suptitle(title or "Envelope error")
    fig.tight_layout()
    return fig


def plot_waveforms(signals: dict, sr: int, tlim: tuple | None = None, title: str = ""):
    """波形を縦に並べる（短い信号・インパルス応答の確認用）"""
    n = len(signals)
    fig, axes = plt.subplots(n, 1, figsize=(10, 1.8 * n), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, (k, x) in zip(axes, signals.items()):
        ax.plot(np.arange(len(x)) / sr * 1000, x, lw=0.7)
        ax.set_ylabel(k)
        ax.grid(True, alpha=0.3)
    if tlim:
        axes[-1].set_xlim(*tlim)
    axes[-1].set_xlabel("Time (ms)")
    fig.suptitle(title)
    fig.tight_layout()
    return fig


COND_STYLE = {"spread": ("補償なし", "gray"), "comp_clip": ("クリップ", "tab:red"), "comp_nnls": ("NNLS", "tab:blue")}
STIM_LABEL = {"sweep": "スイープ", "sam_fm16": "SAM音 (16 Hz)", "en_m01": "英語音声 (男性)", "en_f01": "英語音声 (女性)", "song_m_low": "歌声 (男性・低)", "song_f_high": "歌声 (女性・高)", "piano_f_high": "ピアノ (女性・高と同旋律)"}


def plot_metric_vs_lambda(df, metric, stims, tests=("spread", "comp_clip", "comp_nnls"), ylabel=None, ncols=4):
    nrows = int(np.ceil(len(stims) / ncols))
    if len(stims) < ncols:
        ncols = len(stims)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3 * ncols, 3 * nrows), sharey=True, squeeze=False)
    for i, ax in enumerate(axes.flat):
        if i < len(stims):
            stim = stims[i]
            ax.set_title(STIM_LABEL.get(stim, stim))
            for test in tests:
                sub_df = df[(df["ref"] == "vocoder") & (df["stim"] == stim) & (df["test"] == test)]
                sub_df = sub_df.sort_values("lam")
                label, color = COND_STYLE[test]
                ax.plot(sub_df["lam"], sub_df[metric], marker="o", color=color, label=label)
        else:
            ax.set_visible(False)
        ax.set_xlabel("λ [mm]")
        ax.set_xticks([2, 5, 9])
        if i == 0:
            ax.legend()
    if ylabel:
        for r in range(nrows): axes[r, 0].set_ylabel(ylabel)
    fig.tight_layout()
    return fig