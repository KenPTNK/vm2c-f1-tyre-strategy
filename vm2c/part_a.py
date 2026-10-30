"""Part A, tasks A1-A4: deterministic tyre strategy (lap time depends only on tyre age)."""
from __future__ import annotations

import math
from itertools import combinations_with_replacement

from .model import COMPOUNDS, Track, Tyre
from .solver import Strategy


# ---------------------------------------------------------------- A1
def continuous_optimum(tyre: Tyre, P: float, N: int) -> dict:
    """Minimise the pit-amortised average lap time  t(n) = B + d(n-1)/2 + P/n  over real n.

    n* = sqrt(2P/d),  m* = N/n*,  t* = B - d/2 + sqrt(2Pd).
    If n* > L the cliff binds; stopping exactly at L is optimal iff D >= P/L - d(L-1)/2.
    """
    n_star = math.sqrt(2 * P / tyre.d)
    return {
        "n_star": n_star,
        "m_star": N / n_star,
        "t_star": tyre.B - tyre.d / 2 + math.sqrt(2 * P * tyre.d),
        "cliff_binds": n_star > tyre.L,
        "stop_at_cliff_ok": tyre.D >= P / tyre.L - tyre.d / 2 * (tyre.L - 1),
    }


def balanced(N: int, m: int) -> list[int]:
    """Split N laps into m stints differing by at most one lap (optimal for one compound)."""
    q, r = divmod(N, m)
    return [q + 1] * r + [q] * (m - r)


def single_compound(track: Track, c: str, m: int) -> Strategy:
    lengths = balanced(track.N, m)
    tyre = track.tyres[c]
    return Strategy(tuple((c, n) for n in lengths), sum(tyre.stint(n) for n in lengths) + (m - 1) * track.P)


def best_single_compound(track: Track, max_stints: int = 10) -> dict:
    """A1: for every compound, the best number of stints when only that compound is used."""
    return {c: min((single_compound(track, c, m) for m in range(1, max_stints + 1)), key=lambda s: s.total)
            for c in COMPOUNDS}


# ---------------------------------------------------------------- A2
def envelope(track: Track, n: int) -> tuple[str, float]:
    """g(n) = min_c S_c(n): best compound for a single stint of n laps."""
    return min(((c, track.tyres[c].stint(n)) for c in COMPOUNDS), key=lambda x: x[1])


def economy(track: Track) -> dict:
    """A2: most economical stint length of each compound, minimising (S_c(n) + P)/n."""
    out = {}
    for c, tyre in track.tyres.items():
        n = min(range(1, track.N + 1), key=lambda n: (tyre.stint(n) + track.P) / n)
        out[c] = {"n": n, "S": tyre.stint(n), "rate": (tyre.stint(n) + track.P) / n}
    return out


# ---------------------------------------------------------------- A3
def running_times(track: Track) -> list[tuple[float, list[int]]]:
    """A_m for m = 1..N: least running time with exactly m stints (pit cost excluded).

    Returns [(A_m, stint lengths)] indexed by m-1; each stint uses the envelope compound g(n).
    """
    N, INF = track.N, float("inf")
    g = [0.0] + [envelope(track, n)[1] for n in range(1, N + 1)]
    A = [[INF] * (N + 1) for _ in range(N + 1)]
    back = [[0] * (N + 1) for _ in range(N + 1)]
    A[0][0] = 0.0
    for m in range(1, N + 1):
        for l in range(m, N + 1):
            for n in range(1, l - m + 2):
                v = A[m - 1][l - n] + g[n]
                if v < A[m][l] - 1e-9:
                    A[m][l], back[m][l] = v, n
    out = []
    for m in range(1, N + 1):
        lengths, l = [], N
        for k in range(m, 0, -1):
            lengths.append(back[k][l])
            l -= back[k][l]
        out.append((A[m][N], sorted(lengths, reverse=True)))
    return out


def pit_thresholds(track: Track) -> list[dict]:
    """A3: optimal stint count as a step function of the pit loss P.

    T_m(P) = A_m + (m-1)P.  Adding a stint pays iff Delta_m = A_m - A_{m+1} > P.
    """
    runs = running_times(track)
    A = [a for a, _ in runs]
    cuts = sorted({round(A[m] - A[m + 1], 9) for m in range(len(A) - 1)} | {0.0})
    rows = []
    for lo, hi in zip(cuts, cuts[1:] + [math.inf]):
        P = (lo + hi) / 2 if hi < math.inf else lo + 1.0
        m = min(range(1, len(A) + 1), key=lambda m: A[m - 1] + (m - 1) * P)
        lengths = runs[m - 1][1]
        if rows and rows[-1]["m"] == m:
            rows[-1]["P_hi"] = hi
            continue
        rows.append({"P_lo": lo, "P_hi": hi, "m": m, "pits": m - 1, "A_m": A[m - 1],
                     "stints": "+".join(f"{envelope(track, n)[0]}{n}" for n in lengths)})
    return rows


def marginal_savings(track: Track) -> list[float]:
    """Delta_m = A_m - A_{m+1}, m = 1..N-1 (the A3 'benefit of one more stint' table)."""
    A = [a for a, _ in running_times(track)]
    return [A[m] - A[m + 1] for m in range(len(A) - 1)]


# ---------------------------------------------------------------- A4
def ideal_rate(track: Track) -> tuple[float, str, int]:
    """lambda = min_{c,n} (S_c(n) + P)/n and the ideal stint (c0, n0) reaching it."""
    return min(((t.stint(n) + track.P) / n, c, n) for c, t in track.tyres.items() for n in range(1, track.N + 1))


def penalty(track: Track, lam: float, c: str, n: int) -> float:
    """p_c(n) = S_c(n) + P - n*lambda >= 0.  Total time T = N*lambda - P + sum p."""
    return track.tyres[c].stint(n) + track.P - n * lam


def _fit_to_N(track: Track, lam: float, stints: list[list]) -> None:
    """Greedy trim/extend until the stints cover exactly N laps.

    Removing lap r of a (c, r) stint raises the penalty by lambda - t_c(r); adding lap r+1
    raises it by t_c(r+1) - lambda. Both are monotone per stint, so the greedy choice is optimal.
    """
    lap = lambda c, k: track.tyres[c].lap(k)
    excess = sum(n for _, n in stints) - track.N
    while excess > 0:
        i = min((i for i, s in enumerate(stints) if s[1] > 1), key=lambda i: lam - lap(*stints[i]))
        stints[i][1] -= 1
        excess -= 1
    while excess < 0:
        i = min(range(len(stints)), key=lambda i: lap(stints[i][0], stints[i][1] + 1) - lam)
        stints[i][1] += 1
        excess += 1


def penalty_heuristic(track: Track, widened: bool = True) -> Strategy:
    """A4 method of the paper: build x*C_L + y*C_A from the ideal and second-ideal stints.

    widened=False is the literal recipe (m in {floor, ceil}(N/n0), x >= y, best second compound).
    widened=True also tries m +- 1, x < y and both other compounds ("compare against all").
    """
    lam, c0, n0 = ideal_rate(track)
    N = track.N
    seconds = {c: min(range(1, N + 1), key=lambda n: penalty(track, lam, c, n)) for c in COMPOUNDS if c != c0}
    if not widened:
        c1 = min(seconds, key=lambda c: penalty(track, lam, c, seconds[c]))
        seconds = {c1: seconds[c1]}
    lo, hi = math.floor(N / n0), math.ceil(N / n0)
    ms = range(max(2, lo - 1), hi + 2) if widened else sorted({max(2, lo), max(2, hi)})
    best = None
    for c1, n1 in seconds.items():
        for m in ms:
            for y in range(1, m):
                x = m - y
                if not widened and x < y:
                    continue
                stints = [[c0, n0] for _ in range(x)] + [[c1, n1] for _ in range(y)]
                _fit_to_N(track, lam, stints)
                T = sum(track.tyres[c].stint(n) for c, n in stints) + (m - 1) * track.P
                if best is None or T < best.total - 1e-9:
                    best = Strategy(tuple(map(tuple, stints)), T)
    return best


def best_for_multiset(track: Track, compounds: tuple) -> Strategy:
    """Best stint lengths for a fixed multiset of compounds (order is irrelevant in Part A)."""
    N, INF = track.N, float("inf")
    m = len(compounds)
    cost = [[INF] * (N + 1) for _ in range(m + 1)]
    back = [[0] * (N + 1) for _ in range(m + 1)]
    cost[0][0] = 0.0
    for i, c in enumerate(compounds, 1):
        tyre = track.tyres[c]
        for l in range(i, N + 1):
            for n in range(1, l - i + 2):
                v = cost[i - 1][l - n] + tyre.stint(n)
                if v < cost[i][l] - 1e-9:
                    cost[i][l], back[i][l] = v, n
    stints, l = [], N
    for i in range(m, 0, -1):
        stints.append((compounds[i - 1], back[i][l]))
        l -= back[i][l]
    return Strategy(tuple(reversed(stints)), cost[m][N] + (m - 1) * track.P)


def structures(track: Track, max_stints: int = 5) -> list[Strategy]:
    """Best strategy for every compound multiset with >= 2 compounds, fastest first.

    The gap between the first two entries is the 'margin' column of the A4 table.
    """
    out = [best_for_multiset(track, ms)
           for m in range(2, max_stints + 1)
           for ms in combinations_with_replacement(COMPOUNDS, m) if len(set(ms)) >= 2]
    return sorted(out, key=lambda s: s.total)
