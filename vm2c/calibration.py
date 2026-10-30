"""Part A, task A6: calibrating the tyre model on real races (Max Verstappen, 2023).

Observation model for a clean lap (race r, global lap l, compound c, tyre age k):

    y = B_ref[r,c] + d_c (k-1) + F_r(l) + H_r(l) + eps
    F_r(l) = phi_r (N_r - l),     phi_r = 3.0 / (N_r - 1)     fuel still on board
    H_r(l) = E_r exp(-(l-1)/10)                               track not rubbered in yet

E_r is identified only from two stints on the same compound in the same race.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .model import DATA_DIR

YEAR, DRIVER, GPS = 2023, "VER", ["Bahrain", "Spain", "Hungary"]
TRACK_LAMBDA = 10.0  # laps for the track-evolution penalty to fade by 1/e
FUEL_SPREAD = 3.0    # s: ~100 kg of fuel at ~0.03 s/kg


# ---------------------------------------------------------------- data extraction (needs fastf1)
def extract_one(gp: str, out_dir: Path = DATA_DIR / "fastf1", cache: Path = Path(".fastf1_cache")) -> Path:
    """Clean laps of one Grand Prix, as in the paper's FastF1 listing.

    Drops lap 1, in-laps, out-laps and laps not run under green flag (TrackStatus == "1").
    Since 2026 the F1 live-timing server needs an F1 account: fastf1 will ask for it.
    """
    import fastf1  # optional dependency: pip install -e .[a6]

    cache.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache))
    ses = fastf1.get_session(YEAR, gp, "R")
    ses.load(telemetry=False, weather=True)

    laps = ses.laps.pick_drivers(DRIVER).copy()
    laps["LapTimeS"] = laps["LapTime"].dt.total_seconds()
    laps = laps[["LapNumber", "LapTimeS", "Stint", "Compound", "TyreLife",
                 "PitInTime", "PitOutTime", "TrackStatus"]].reset_index(drop=True)
    laps["clean"] = ~((laps["LapNumber"] == 1) | laps["PitInTime"].notna() | laps["PitOutTime"].notna()) \
        & (laps["TrackStatus"].astype(str) == "1")

    print(f"\n=== {DRIVER} - {YEAR} {gp} GP ===")
    for st, grp in laps.groupby("Stint"):
        comp = grp["Compound"].mode().iat[0]
        print(f" Stint {int(st)} | {comp:7s} | {len(grp):2d} laps (clean: {int(grp['clean'].sum()):2d}) "
              f"| laps {int(grp.LapNumber.min())}-{int(grp.LapNumber.max())}")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{DRIVER}_{YEAR}_{gp}_clean.csv"
    laps[laps["clean"]][["LapNumber", "Stint", "Compound", "TyreLife", "LapTimeS"]].to_csv(path, index=False)
    print(f" -> wrote {int(laps['clean'].sum())} clean laps: {path}")
    return path


# ---------------------------------------------------------------- corrections
def fuel_rate(N: int) -> float:
    """phi_r = 3/(N_r - 1) s per lap."""
    return FUEL_SPREAD / (N - 1)


def fuel_penalty(l, N: int):
    """F_r(l) = phi_r (N_r - l): zero on the last lap."""
    return fuel_rate(N) * (N - np.asarray(l, dtype=float))


def track_penalty(l, E: float, lam: float = TRACK_LAMBDA):
    """H_r(l) = E_r exp(-(l-1)/lambda)."""
    return E * np.exp(-(np.asarray(l, dtype=float) - 1) / lam)


def estimate_E(B_raw_a: float, l_a: int, B_raw_b: float, l_b: int, N: int, lam: float = TRACK_LAMBDA) -> float:
    """E_r from two same-compound stints starting at l_a and l_b (their baselines must agree)."""
    Fa, Fb = fuel_penalty(l_a, N), fuel_penalty(l_b, N)
    return float(((B_raw_b - Fb) - (B_raw_a - Fa)) / (np.exp(-(l_b - 1) / lam) - np.exp(-(l_a - 1) / lam)))


def ols(x, y) -> tuple[float, float]:
    """Least squares y = a + b x. Returns (a, b)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    b = ((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum()
    return float(y.mean() - b * x.mean()), float(b)


def correct_stint(B_raw: float, d_raw: float, l0: int, laps: int, N: int, E: float = 0.0) -> dict:
    """Move a raw stint fit to the reference point (no fuel, rubbered-in track).

    B_ref = B_raw - F(l0) - H(l0);   d = d_raw + phi - beta_H,
    beta_H = OLS slope of H(l0 + k - 1) on k - 1 (negative, so the track correction raises d).
    """
    k = np.arange(1, laps + 1)
    beta_H = ols(k - 1, track_penalty(l0 + k - 1, E))[1] if E else 0.0
    F0, H0 = float(fuel_penalty(l0, N)), float(track_penalty(l0, E))
    return {"F0": F0, "H0": H0, "B_ref": B_raw - F0 - H0, "d_corr": d_raw + fuel_rate(N) - beta_H}


def fit_laps(path: Path, N: int, E: float = 0.0) -> list[dict]:
    """Per-stint raw and corrected fits from a clean-lap CSV written by `extract_one`."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for st in sorted({int(float(r["Stint"])) for r in rows}):
        s = [r for r in rows if int(float(r["Stint"])) == st]
        l = np.array([float(r["LapNumber"]) for r in s])
        k = np.array([float(r["TyreLife"]) for r in s])
        y = np.array([float(r["LapTimeS"]) for r in s])
        B_raw, d_raw = ols(k - 1, y)
        B_ref, d_corr = ols(k - 1, y - fuel_penalty(l, N) - track_penalty(l, E))
        out.append({"stint": st, "compound": s[0]["Compound"], "l0": int(l.min()), "laps": len(s),
                    "B_raw": B_raw, "d_raw": d_raw, "B_ref": B_ref, "d_corr": d_corr})
    return out


def load_stints(path: Path = DATA_DIR / "a6_stints.csv") -> list[dict]:
    """Stint-level raw fits reported in the paper (used when lap data is not downloaded)."""
    with open(path, newline="", encoding="utf-8") as f:
        return [{**r, "N": int(r["N"]), "stint": int(r["stint"]), "l0": int(r["l0"]), "laps": int(r["laps"]),
                 "B_raw": float(r["B_raw"]), "d_raw": float(r["d_raw"])} for r in csv.DictReader(f)]


def calibrate(stints: list[dict]) -> tuple[list[dict], dict]:
    """Full A6(b) pipeline on stint-level fits.

    E_r is estimated from the first same-compound pair of each race and kept only when it is
    positive (a negative 'track penalty' contradicts its meaning, so it is set to 0).
    """
    E_raw, E_used = {}, {}
    for race in dict.fromkeys(s["race"] for s in stints):
        rs = [s for s in stints if s["race"] == race]
        pair = next(((a, b) for i, a in enumerate(rs) for b in rs[i + 1:] if a["compound"] == b["compound"]), None)
        E_raw[race] = estimate_E(pair[0]["B_raw"], pair[0]["l0"], pair[1]["B_raw"], pair[1]["l0"], rs[0]["N"]) \
            if pair else None
        E_used[race] = E_raw[race] if E_raw[race] and E_raw[race] > 0 else 0.0
    table = [{**s, **correct_stint(s["B_raw"], s["d_raw"], s["l0"], s["laps"], s["N"], E_used[s["race"]])}
             for s in stints]
    return table, {"E_raw": E_raw, "E_used": E_used}


def compound_means(table: list[dict]) -> dict:
    """Corrected degradation pooled per compound (descriptive)."""
    out = {}
    for s in table:
        out.setdefault(s["compound"], []).append(s["d_corr"])
    return {c: float(np.mean(v)) for c, v in out.items()}


def cliff_lower_bounds(table: list[dict]) -> dict:
    """No stint shows a clear cliff, so L_c is at least the longest observed stint."""
    out = {}
    for s in table:
        out[s["compound"]] = max(out.get(s["compound"], 0), s["laps"])
    return out


def broken_stick(k, y) -> dict:
    """Fit t(k) = b0 + b1 min(k-1, kappa-1) + b2 max(0, k-kappa) by scanning kappa (min RSS).

    Gives L = kappa, d = b1, D = b2 when post-cliff laps exist in the data.
    """
    k, y = np.asarray(k, float), np.asarray(y, float)
    best = None
    for kappa in range(2, int(k.max())):
        X = np.column_stack([np.ones_like(k), np.minimum(k - 1, kappa - 1), np.maximum(0, k - kappa)])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        rss = float(((X @ coef - y) ** 2).sum())
        if best is None or rss < best["rss"]:
            best = {"L": kappa, "B": float(coef[0]), "d": float(coef[1]), "D": float(coef[2]), "rss": rss}
    return best


if __name__ == "__main__":
    for gp in GPS:
        extract_one(gp)
