"""Part B: fuel load.  t_c(k, l) = B_c + w F(l) + g_c(k)(1 + beta F(l)),  F(l) = N - l + 1.

Key identity (Proposition B.1):  T_B = T_A + w N(N+1)/2 + beta * Phi,  Phi = sum_i sum_k g_ci(k) F(l).
  * the w term is the same for every strategy, so w never changes the optimal strategy;
  * only beta * Phi depends on the order of the stints.
Sorting theorem (B.2): Phi is minimal when stints run in increasing mean wear G_i / n_i
(the gentlest tyre goes first, while the car is heaviest).
"""
from __future__ import annotations

from .model import Track, lap_time_b
from .solver import Strategy, evaluate, optimise

PARAM_SETS = {"a": (0.06, 0.01), "b": (0.10, 0.01), "c": (0.06, 0.03)}  # (w, beta) of task B2


def total_wear(track: Track, c: str, n: int) -> float:
    """G = sum_{k=1..n} g_c(k)."""
    return sum(track.tyres[c].wear(k) for k in range(1, n + 1))


def mean_wear(track: Track, c: str, n: int) -> float:
    """g_bar = G / n, the sorting key of Theorem B.2."""
    return total_wear(track, c, n) / n


def coupling(track: Track, stints) -> float:
    """Phi = sum over laps of g_c(k) F(l) for stints driven in the given order."""
    phi, l = 0.0, 0
    for c, n in stints:
        for k in range(1, n + 1):
            l += 1
            phi += track.tyres[c].wear(k) * (track.N - l + 1)
    return phi


def decompose(track: Track, stints, w: float, beta: float) -> dict:
    """Split T_B into the Part A time, the fuel constant and the fuel-wear coupling."""
    T_A = sum(track.tyres[c].stint(n) for c, n in stints) + (len(stints) - 1) * track.P
    const = w * track.N * (track.N + 1) / 2
    phi = coupling(track, stints)
    return {"T_A": T_A, "w_const": const, "Phi": phi, "beta_Phi": beta * phi, "T_B": T_A + const + beta * phi}


def order_by_wear(track: Track, stints) -> tuple:
    """Optimal driving order of a fixed set of stints (Theorem B.2)."""
    return tuple(sorted(stints, key=lambda s: mean_wear(track, *s)))


def swap_difference(track: Track, a, b) -> float:
    """Phi(..., A, B, ...) - Phi(..., B, A, ...) = n_B G_A - n_A G_B for adjacent stints A, B.

    Negative means A should run first; equivalent to g_bar_A < g_bar_B.
    """
    (ca, na), (cb, nb) = a, b
    return nb * total_wear(track, ca, na) - na * total_wear(track, cb, nb)


def solve(track: Track, w: float, beta: float) -> Strategy:
    """Exact optimum under the fuel model (at least two compounds, as in A4)."""
    return optimise(track.N, track.P, lap_time_b(track, w, beta))


def time_b(track: Track, stints, w: float, beta: float) -> float:
    return evaluate(stints, lap_time_b(track, w, beta), track.P)
