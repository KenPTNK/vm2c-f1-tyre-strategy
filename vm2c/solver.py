"""Exact strategy optimiser (dynamic programming over the global lap).

The papers derive the optimum by hand (marginal-cost lemmas, penalty functions, the
sorting theorem). This solver is the brute-force ground truth used to check every
number they report: it is exact for any lap-time model lap(c, k, l), including the
order-dependent fuel model of Part B.

State: (laps already driven, set of compounds used). Choice: next stint (c, n).
Cost: O(N^2 * |compounds| * 2^|compounds|) lap evaluations, well under a second for N <= 78.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .model import COMPOUNDS


@dataclass(frozen=True)
class Strategy:
    stints: tuple  # ((compound, laps), ...) in driving order
    total: float   # race time (s)

    @property
    def pits(self) -> int:
        return len(self.stints) - 1

    @property
    def pit_laps(self) -> list[int]:
        """Laps after which the car pits."""
        out, lap = [], 0
        for _, n in self.stints[:-1]:
            lap += n
            out.append(lap)
        return out

    def __str__(self) -> str:
        return "+".join(f"{c}{n}" for c, n in self.stints)


def evaluate(stints, lap, P: float) -> float:
    """Total race time of a given stint sequence: sum of lap times + (m-1) P."""
    total, l = 0.0, 0
    for c, n in stints:
        for k in range(1, n + 1):
            l += 1
            total += lap(c, k, l)
    return total + (len(stints) - 1) * P


def optimise(N: int, P: float, lap, compounds=COMPOUNDS, min_compounds: int = 2) -> Strategy:
    """Fastest strategy over N laps.

    min_compounds=2 is the race rule used from A4 on; A1-A3 use min_compounds=1.
    A fixed number of stints (A3) is solved by `part_a.running_times`.
    """
    if min_compounds > len(compounds):
        raise ValueError("min_compounds larger than the number of compounds")
    INF = float("inf")

    @lru_cache(maxsize=None)
    def best(l: int, mask: int):
        if l == N:
            return (0.0, ()) if bin(mask).count("1") >= min_compounds else (INF, ())
        res = (INF, ())
        for i, c in enumerate(compounds):
            run = 0.0
            for n in range(1, N - l + 1):
                run += lap(c, n, l + n)
                sub_t, sub_s = best(l + n, mask | 1 << i)
                t = run + sub_t + (P if l + n < N else 0.0)
                if t < res[0] - 1e-9:
                    res = (t, ((c, n),) + sub_s)
        return res

    t, s = best(0, 0)
    if t == INF:
        raise ValueError("no feasible strategy")
    return Strategy(s, t)

