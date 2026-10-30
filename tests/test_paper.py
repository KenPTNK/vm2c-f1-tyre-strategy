"""Every number checked here is printed in the team's papers (Part A and Part B)."""
import itertools

import numpy as np
import pytest

from vm2c import SAMPLE, Tyre, load_tracks, optimise
from vm2c import calibration, part_a, part_b, robust
from vm2c.model import lap_time_a

TRACKS = {t.name: t for t in load_tracks()}

# A4 table: track -> (multiset of stints, total time, margin to the next structure)
A4 = {
    "Bahrain": ("M16+M16+M15+S10", 5592.3750, 0.4075), "Jeddah": ("H28+M22", 4603.5000, 1.5000),
    "Melbourne": ("M19+S13+S13+S13", 4715.2950, 1.1850), "Suzuka": ("M17+S12+S12+S12", 4919.5000, 3.0000),
    "Imola": ("H37+M26", 4949.5100, 2.4450), "Monaco": ("H32+M23+M23", 5769.7800, 1.8500),
    "Barcelona": ("M19+M19+S14+S14", 5190.8600, 0.1000), "Montreal": ("H28+M21+M21", 5274.6550, 1.8775),
    "Spielberg": ("M20+M20+M19+S12", 4807.1600, 2.0400), "Silverstone": ("M20+M20+S12", 4733.4400, 4.4800),
    "Hungaroring": ("H22+M16+M16+M16", 5581.5925, 0.3375), "Spa": ("M16+S14+S14", 4686.0000, 6.2000),
    "Zandvoort": ("H22+M17+M17+M16", 5303.7750, 1.7750), "Monza": ("H31+M22", 4339.3720, 2.8840),
    "Singapore": ("H24+M19+M19", 6079.2000, 3.5200), "COTA": ("M20+S12+S12+S12", 5536.2500, 0.5500),
    "Mexico": ("M20+M19+M19+S13", 5716.8400, 0.5750), "Interlagos": ("M20+M19+M19+S13", 5238.5200, 2.1250),
    "LasVegas": ("H28+M22", 4802.5000, 0.5000), "AbuDhabi": ("M22+M22+S14", 5248.8200, 0.4750),
}

# Part B, B2 table: track -> (strategy (a)=(b) in driving order, T(a), T(b), strategy (c), T(c))
B2 = {
    "Bahrain": ("H23+M17+M17", 5705.39, 5771.51, "H18+H22+M17", 5728.07),
    "Jeddah": ("H28+M22", 4686.59, 4737.59, "H27+M23", 4699.75),
    "Melbourne": ("M16+M17+S12+S13", 4832.78, 4901.22, "H17+M14+M15+S12", 4854.41),
    "Suzuka": ("M17+S12+S12+S12", 5020.59, 5077.82, "M12+M14+M15+S12", 5043.22),
    "Imola": ("H37+M26", 5085.48, 5166.12, "H20+H23+M20", 5107.68),
    "Monaco": ("H26+H29+M23", 5969.70, 6092.94, "H25+H29+M24", 5995.64),
    "Barcelona": ("M16+M17+M19+S14", 5343.52, 5431.96, "H18+M14+M15+M19", 5373.67),
    "Montreal": ("H24+H26+M20", 5438.56, 5537.96, "H22+H27+M21", 5463.98),
    "Spielberg": ("H20+M16+M17+M18", 4982.19, 5084.43, "H16+H17+H20+M18", 5011.59),
    "Silverstone": ("M19+M21+S12", 4829.94, 4885.06, "H18+M15+M19", 4851.39),
    "Hungaroring": ("H19+H20+M15+M16", 5748.61, 5848.01, "H16+H17+H20+M17", 5775.55),
    "Spa": ("M16+S14+S14", 4753.81, 4793.41, "M16+S13+S15", 4770.28),
    "Zandvoort": ("H19+H21+M15+M17", 5480.29, 5585.41, "H16+H18+H21+M17", 5508.46),
    "Monza": ("H30+M23", 4431.91, 4489.15, "H29+M24", 4445.22),
    "Singapore": ("H25+M18+M19", 6211.83, 6289.95, "H20+H23+M19", 6236.13),
    "COTA": ("M14+M15+M15+S12", 5647.06, 5710.90, "H18+H20+M18", 5668.18),
    "Mexico": ("H24+H26+M21", 5888.42, 5990.66, "H16+H17+H20+M18", 5915.06),
    "Interlagos": ("H20+M16+M17+M18", 5413.94, 5516.18, "H16+H17+H20+M18", 5443.22),
    "LasVegas": ("H28+M22", 4885.59, 4936.59, "H27+M23", 4898.75),
    "AbuDhabi": ("M16+M17+S12+S13", 5366.78, 5435.22, "H18+H21+M19", 5386.74),
}


def multiset(s):
    return sorted(str(s).split("+"))


# ---------------------------------------------------------------- model
def test_closed_form_stint_time_matches_sum():
    for t in [*SAMPLE.tyres.values(), Tyre(95.0, 0.29, 10, 3.0)]:
        for n in range(1, 60):
            assert t.stint(n) == pytest.approx(sum(t.lap(k) for k in range(1, n + 1)))


# ---------------------------------------------------------------- A1-A3
def test_a1_single_compound():
    best = part_a.best_single_compound(SAMPLE)
    assert (str(best["S"]), best["S"].total) == ("S13+S13+S12+S12", pytest.approx(4132.6))
    assert best["M"].total == pytest.approx(4135.0)
    assert best["H"].total == pytest.approx(4155.0)
    opt = part_a.continuous_optimum(SAMPLE.tyres["S"], SAMPLE.P, SAMPLE.N)
    assert opt["n_star"] == pytest.approx(15.81, abs=0.01) and opt["cliff_binds"]


def test_a2_economy_and_optimum():
    eco = part_a.economy(SAMPLE)
    assert [(eco[c]["n"], round(eco[c]["rate"], 4)) for c in "SMH"] == [(15, 83.0667), (22, 83.1864), (32, 83.5563)]
    best = optimise(SAMPLE.N, SAMPLE.P, lap_time_a(SAMPLE), min_compounds=1)
    assert multiset(best) == ["M20", "S15", "S15"] and best.total == pytest.approx(4131.0)


def test_a3_marginal_savings_and_thresholds():
    d = part_a.marginal_savings(SAMPLE)
    assert [round(x, 2) for x in d[:9]] == [225.25, 29.0, 23.4, 12.6, 8.2, 6.0, 4.4, 3.4, 3.0]
    assert round(d[-1], 2) == 0.2
    rows = {r["m"]: r for r in part_a.pit_thresholds(SAMPLE)}
    assert [round(rows[m]["A_m"], 2) for m in (5, 4, 3, 2, 1)] == [4045.0, 4057.6, 4081.0, 4110.0, 4335.25]
    assert (round(rows[3]["P_lo"], 1), round(rows[3]["P_hi"], 1)) == (23.4, 29.0)


# ---------------------------------------------------------------- A4
@pytest.mark.parametrize("name", A4)
def test_a4_table(name):
    track, (strategy, total, margin) = TRACKS[name], A4[name]
    ranked = part_a.structures(track)
    assert ranked[0].total == pytest.approx(total, abs=1e-6)
    assert multiset(ranked[0]) == sorted(strategy.split("+"))
    assert ranked[1].total - ranked[0].total == pytest.approx(margin, abs=1e-6)
    assert optimise(track.N, track.P, lap_time_a(track)).total == pytest.approx(total, abs=1e-6)
    assert part_a.penalty_heuristic(track).total == pytest.approx(total, abs=1e-6)


def test_a4_literal_heuristic_misses_four_tracks():
    missed = {n for n, t in TRACKS.items()
              if part_a.penalty_heuristic(t, widened=False).total > A4[n][1] + 1e-6}
    assert missed == {"Monaco", "Montreal", "COTA", "LasVegas"}


# ---------------------------------------------------------------- A5
def test_a5_risk_ranking():
    table = {k: robust.risk(robust.simulate(s, n=90_000)) for k, s in robust.CANDIDATES.items()}
    paper = {"Nominal optimum S15-S15-M20": (4151.1, 57.1, 4278.6), "Safety margin S13-S13-M24": (4147.4, 49.8, 4257.6),
             "S-M-M S15-M18-M17": (4147.3, 40.0, 4233.8), "All soft S13-S13-S12-S12": (4142.7, 45.2, 4237.7),
             "Conservative M25-M25": (4158.9, 70.5, 4318.6)}
    for k, (mean, std, cvar) in paper.items():  # Monte Carlo noise: ~0.2 s on the mean
        assert table[k]["mean"] == pytest.approx(mean, abs=1.0)
        assert table[k]["std"] == pytest.approx(std, abs=1.5)
        assert table[k]["CVaR"] == pytest.approx(cvar, abs=2.5)
    assert min(table, key=lambda k: table[k]["mean"]).startswith("All soft")
    assert min(table, key=lambda k: table[k]["std"]).startswith("S-M-M")
    assert min(table, key=lambda k: table[k]["CVaR"]).startswith("S-M-M")


def test_a5_pit_quantiles_and_cliff_penalty_convexity():
    U = np.array([0.5, 0.75, 0.9, 0.95, 0.99])
    assert np.round(24 + (U / (1 - U)) ** (1 / 3), 2).tolist() == [25.0, 25.44, 26.08, 26.67, 28.63]
    L = np.random.default_rng(0).integers(10, 20, 10_000)
    phi = [robust.expected_cliff_penalty(n, L) for n in range(5, 25)]
    assert all(b - a <= c - b + 1e-12 for a, b, c in zip(phi, phi[1:], phi[2:]))  # convex


# ---------------------------------------------------------------- A6
def test_a6_calibration_table():
    table, E = calibration.calibrate(calibration.load_stints())
    assert round(E["E_raw"]["Bahrain"], 3) == -0.711 and E["E_used"]["Bahrain"] == 0.0
    assert E["E_raw"]["Spain"] is None and round(E["E_used"]["Hungary"], 3) == 0.419
    B_ref = [94.828, 95.364, 95.592, 77.472, 77.176, 76.814, 81.278, 81.536, 81.278]
    d_corr = [0.108, 0.054, 0.066, 0.027, 0.051, 0.092, 0.034, 0.047, 0.028]
    assert [round(s["B_ref"], 3) for s in table] == B_ref
    # the paper fitted Hungary stint 1 on lap-level data: 0.034 vs 0.031 from stint-level numbers
    assert [s["d_corr"] for s in table] == pytest.approx(d_corr, abs=0.004)
    assert calibration.cliff_lower_bounds(table) == {"S": 22, "M": 26, "H": 28}


def test_a6_broken_stick_recovers_cliff():
    t = Tyre(90.0, 0.08, 18, 1.2)
    k = np.arange(1, 30)
    noise = np.random.default_rng(0).normal(0, 0.05, k.size)
    fit = calibration.broken_stick(k, [t.lap(int(i)) for i in k] + noise)
    assert fit["L"] == 18 and fit["D"] == pytest.approx(1.2, abs=0.05)


# ---------------------------------------------------------------- Part B
def test_b1_sample_track():
    best = part_b.solve(SAMPLE, 0.06, 0.01)
    assert str(best) == "M20+S15+S15" and best.total == pytest.approx(4219.92)
    parts = part_b.decompose(SAMPLE, (("S", 15), ("S", 15), ("M", 20)), 0.06, 0.01)
    assert (parts["T_A"], parts["w_const"], round(parts["beta_Phi"], 2), round(parts["T_B"], 2)) == \
        (pytest.approx(4131.0), pytest.approx(76.5), 15.12, 4222.62)


def test_b1_sorting_theorem_matches_brute_force():
    track = TRACKS["Hungaroring"]
    for stints in [(("S", 12), ("M", 20), ("H", 25), ("M", 13)), (("H", 30), ("S", 10), ("M", 30))]:
        brute = min(itertools.permutations(stints), key=lambda p: part_b.coupling(track, p))
        assert part_b.coupling(track, part_b.order_by_wear(track, stints)) == pytest.approx(
            part_b.coupling(track, brute))
        a, b = stints[0], stints[1]
        assert part_b.swap_difference(track, a, b) == pytest.approx(
            part_b.coupling(track, (a, b)) - part_b.coupling(track, (b, a)))


@pytest.mark.parametrize("name", B2)
def test_b2_table(name):
    track, (sa, ta, tb, sc, tc) = TRACKS[name], B2[name]
    a, b, c = (part_b.solve(track, *part_b.PARAM_SETS[k]) for k in "abc")
    assert (str(a), str(b), str(c)) == (sa, sa, sc)
    assert (a.total, b.total, c.total) == (pytest.approx(ta, abs=0.006), pytest.approx(tb, abs=0.011),
                                           pytest.approx(tc, abs=0.006))
    # Theorem B.4: (a) and (b) differ by exactly 0.04 N(N+1)/2
    assert b.total - a.total == pytest.approx(0.04 * track.N * (track.N + 1) / 2)
