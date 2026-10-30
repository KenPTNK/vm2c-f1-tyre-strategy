"""Part A, task A5: parameter uncertainty, Monte Carlo and a robust strategy.

Noise structure: one shared race-day factor xi ~ N(0,1) hits every compound with the same
sign; each parameter also gets its own independent N(0,1) noise, with equal weight.

    B_c = B0 (1 + aB (xi + nu_c))                         scaled normal
    d_c = d0 exp(ad (xi + eps_c))                         log-normal
    D_c = max(D0 exp(aD (xi + eps'_c)), 3 d_c)            log-normal, cliff stays a cliff
    L_c = round(L0 (1 - aL xi) + sL zeta_c)               rounded normal (hot day -> earlier cliff)
    P   = P0 + mP (U/(1-U))^(1/b)  per pit stop           log-logistic, floor P0, median P0+mP

Coefficients are the paper's calibration from Cappello & Hoegh (2025) posterior intervals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .model import SAMPLE, Track


@dataclass(frozen=True)
class Uncertainty:
    aB: dict = field(default_factory=lambda: {"S": 0.00203, "M": 0.00201, "H": 0.00198})
    ad: dict = field(default_factory=lambda: {"S": 0.285, "M": 0.328, "H": 0.392})
    aD: dict = field(default_factory=lambda: {"S": 0.247, "M": 0.272, "H": 0.304})
    aL: float = 0.10   # shared share of the cliff position (fraction of tyre life)
    sL: float = 1.8    # own noise of the cliff position (laps)
    P0: float = 24.0   # pit floor (s)
    mP: float = 1.0    # median - floor (s)
    bP: float = 3.0    # log-logistic shape (small = heavy tail)


def coefficient_from_cov(cov: float, lognormal: bool) -> float:
    """Split a total CoV equally between shared and own noise: a = CoV/sqrt2 or sigma/sqrt2."""
    sigma = np.sqrt(np.log1p(cov ** 2)) if lognormal else cov
    return float(sigma / np.sqrt(2))


def sample_parameters(n: int, rng: np.random.Generator, track: Track = SAMPLE, u: Uncertainty = Uncertainty()):
    """Draw n race days. Returns {compound: (B, d, L, D)} arrays of length n."""
    xi = rng.standard_normal(n)
    out = {}
    for c, t in track.tyres.items():
        B = t.B * (1 + u.aB[c] * (xi + rng.standard_normal(n)))
        d = t.d * np.exp(u.ad[c] * (xi + rng.standard_normal(n)))
        D = np.maximum(t.D * np.exp(u.aD[c] * (xi + rng.standard_normal(n))), 3 * d)
        L = np.maximum(1, np.round(t.L * (1 - u.aL * xi) + u.sL * rng.standard_normal(n)))
        out[c] = (B, d, L, D)
    return out


def sample_pits(shape, rng: np.random.Generator, u: Uncertainty = Uncertainty()):
    U = rng.random(shape)
    return u.P0 + u.mP * (U / (1 - U)) ** (1 / u.bP)


def simulate(stints, n: int = 90_000, seed: int = 0, track: Track = SAMPLE, u: Uncertainty = Uncertainty(),
             breakdown: bool = False):
    """Race-time samples T for a fixed strategy; each pit stop is drawn independently.

    With breakdown=True also returns the mean of each E[T] term:
    base sum n B, degradation sum d n(n-1)/2, cliff sum (D-d)(k-L)^+, and pits.
    """
    rng = np.random.default_rng(seed)
    par = sample_parameters(n, rng, track, u)
    base = deg = cliff = np.zeros(n)
    for c, m in stints:
        B, d, L, D = par[c]
        k = np.arange(1, m + 1)[:, None]
        base = base + m * B
        deg = deg + d * m * (m - 1) / 2
        cliff = cliff + ((D - d) * np.maximum(k - L, 0)).sum(axis=0)
    pits = sample_pits((len(stints) - 1, n), rng, u).sum(axis=0)
    T = base + deg + cliff + pits
    if breakdown:
        return T, {"base": base.mean(), "degradation": deg.mean(), "cliff": cliff.mean(), "pit": pits.mean()}
    return T


def risk(T: np.ndarray, alpha: float = 0.90) -> dict:
    """Mean, std, VaR_alpha and CVaR_alpha = E[T | T >= VaR_alpha]."""
    var = float(np.quantile(T, alpha))
    return {"mean": float(T.mean()), "std": float(T.std()), "VaR": var, "CVaR": float(T[T >= var].mean())}


# The five candidates of the A5 section, each the structural minimiser of one criterion.
CANDIDATES = {
    "Nominal optimum S15-S15-M20": (("S", 15), ("S", 15), ("M", 20)),
    "Safety margin S13-S13-M24": (("S", 13), ("S", 13), ("M", 24)),
    "S-M-M S15-M18-M17": (("S", 15), ("M", 18), ("M", 17)),
    "All soft S13-S13-S12-S12": (("S", 13), ("S", 13), ("S", 12), ("S", 12)),
    "Conservative M25-M25": (("M", 25), ("M", 25)),
}


def lap_time_band(track: Track = SAMPLE, u: Uncertainty = Uncertainty(), k_max: int = 45) -> dict:
    """Delta-method 95% band of t_c(k) (the 'trumpet' figure):

    Var t_c(k) ~ sB^2 + (k-1)^2 sd^2 + 1{k>L}(k-L)^2 sD^2 + 1{|k-L|<=1}(D-d)^2 sL^2.
    """
    out = {}
    k = np.arange(1, k_max + 1)
    for c, t in track.tyres.items():
        sB = t.B * u.aB[c] * np.sqrt(2)
        sd = t.d * np.sqrt(np.exp(2 * u.ad[c] ** 2) - 1)
        sD = t.D * np.sqrt(np.exp(2 * u.aD[c] ** 2) - 1)
        sL = np.hypot(t.L * u.aL, u.sL)
        mean = np.array([t.lap(int(i)) for i in k])
        var = (sB ** 2 + (k - 1) ** 2 * sd ** 2 + (k > t.L) * (k - t.L) ** 2 * sD ** 2
               + (np.abs(k - t.L) <= 1) * (t.D - t.d) ** 2 * sL ** 2)
        out[c] = (k, mean, 1.96 * np.sqrt(var))
    return out


def expected_cliff_penalty(n: int, L_samples: np.ndarray) -> float:
    """phi(n) = E[(n - L)^+]; convex in n with phi(n) - phi(n-1) = F_L(n-1) (safety-margin theorem)."""
    return float(np.maximum(n - L_samples, 0).mean())
