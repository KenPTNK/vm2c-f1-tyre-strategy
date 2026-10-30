"""Lap-time models from the paper.

Part A:  t_c(k)    = B_c + g_c(k)
Part B:  t_c(k, l) = B_c + w F(l) + g_c(k) (1 + beta F(l)),   F(l) = N - l + 1
B3:      t_c(k, l) = B_c + w_c F(l) + g~_c(k) (1 + beta_c F(l)) + u_c exp(-rho_c (k-1))

k is the lap index inside the stint (tyre age), l the global lap of the race.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

COMPOUNDS = ("S", "M", "H")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Tyre:
    B: float  # base lap time of a fresh tyre (s)
    d: float  # degradation before the cliff (s/lap)
    L: int    # cliff lap
    D: float  # degradation after the cliff (s/lap)

    def wear(self, k: int) -> float:
        """g_c(k): degradation part of lap k of a stint."""
        return self.d * (k - 1) if k <= self.L else self.d * (self.L - 1) + self.D * (k - self.L)

    def lap(self, k: int) -> float:
        """t_c(k) of Part A."""
        return self.B + self.wear(k)

    def stint(self, n: int) -> float:
        """S_c(n) = sum_{k=1..n} t_c(k), closed form from Section 'Fundamental theorems'."""
        if n <= self.L:
            return n * self.B + self.d / 2 * n * (n - 1)
        return (n * self.B + self.d / 2 * (self.L - 1) * (2 * n - self.L)
                + self.D / 2 * (n - self.L) * (n - self.L + 1))


@dataclass(frozen=True)
class Track:
    name: str
    N: int      # race laps
    P: float    # pit-stop loss (s)
    tyres: dict  # compound -> Tyre


# The "sample track" of Part A (N = 50, P = 25).
SAMPLE = Track("Sample", 50, 25.0, {
    "S": Tyre(80.0, 0.20, 15, 3.0),
    "M": Tyre(81.0, 0.10, 25, 2.0),
    "H": Tyre(82.0, 0.05, 35, 1.5),
})


def load_tracks(path: str | Path = DATA_DIR / "tracks.csv") -> list[Track]:
    """Read the 20-track table (problem appendix A)."""
    with open(path, newline="", encoding="utf-8") as f:
        return [Track(r["track"], int(r["N"]), float(r["P"]),
                      {c: Tyre(float(r[f"B_{c}"]), float(r[f"d_{c}"]), int(r[f"L_{c}"]), float(r[f"D_{c}"]))
                       for c in COMPOUNDS})
                for r in csv.DictReader(f)]


def lap_time_a(track: Track):
    """Part A lap time as a function lap(c, k, l) for the solver."""
    return lambda c, k, l: track.tyres[c].lap(k)


def lap_time_b(track: Track, w: float, beta: float):
    """Part B lap time (problem equation (1))."""
    N = track.N
    def lap(c, k, l):
        tyre, F = track.tyres[c], N - l + 1
        return tyre.B + w * F + tyre.wear(k) * (1 + beta * F)
    return lap


@dataclass(frozen=True)
class B3Params:
    """Per-compound parameters of the improved model proposed in B3."""
    w: float      # fuel weight -> slower
    beta: float   # fuel weight -> faster wear
    A: float      # height of the smooth cliff
    lam: float    # sharpness of the smooth cliff
    u: float      # cold-tyre penalty on the out-lap
    rho: float    # how fast the cold-tyre penalty fades


def smooth_wear(tyre: Tyre, p: B3Params, k: int) -> float:
    """g_c^new(k) = d_c (k-1) + A_c ln(1 + exp(lambda_c (k - L_c)))  (softplus cliff)."""
    x = p.lam * (k - tyre.L)
    softplus = x + math.log1p(math.exp(-x)) if x > 0 else math.log1p(math.exp(x))
    return tyre.d * (k - 1) + p.A * softplus


def lap_time_b3(track: Track, params: dict):
    """Improved B3 model: t = B + w_c F + g^new(k)(1 + beta_c F) + u_c exp(-rho_c (k-1))."""
    N = track.N
    def lap(c, k, l):
        tyre, p, F = track.tyres[c], params[c], N - l + 1
        return tyre.B + p.w * F + smooth_wear(tyre, p, k) * (1 + p.beta * F) + p.u * math.exp(-p.rho * (k - 1))
    return lap
