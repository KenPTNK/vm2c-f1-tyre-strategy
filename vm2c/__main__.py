"""Reproduce every table and figure of both papers:  python -m vm2c [--out DIR] [--samples N]."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from . import calibration, figures, part_a, part_b, robust
from .model import SAMPLE, B3Params, lap_time_a, lap_time_b3, load_tracks
from .solver import optimise

ROOT = Path(__file__).resolve().parent.parent


def write(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")


def r(x, nd=4):
    return round(float(x), nd)


def strategy_rows(tracks, strategies, extra=None):
    return [{"id": i, "track": t.name, "N": t.N, "strategy": str(s),
             "pit_after_laps": " ".join(map(str, s.pit_laps)), "pits": s.pits, "total_time": r(s.total),
             **(extra[i - 1] if extra else {})}
            for i, (t, s) in enumerate(zip(tracks, strategies), 1)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT)
    ap.add_argument("--samples", type=int, default=90_000, help="Monte Carlo race days for A5")
    args = ap.parse_args()
    res, fig = args.out / "results", args.out / "figures"
    res.mkdir(parents=True, exist_ok=True)
    fig.mkdir(parents=True, exist_ok=True)
    tracks = load_tracks()

    print("A1 - one compound")
    rows, curves = [], {}
    for c, t in SAMPLE.tyres.items():
        opt = part_a.continuous_optimum(t, SAMPLE.P, SAMPLE.N)
        best = part_a.best_single_compound(SAMPLE)[c]
        curves[c] = [(m, part_a.single_compound(SAMPLE, c, m).total) for m in range(1, 9)]
        rows.append({"compound": c, "n_star": r(opt["n_star"], 2), "m_star": r(opt["m_star"], 2),
                     "cliff_binds": opt["cliff_binds"], "best": str(best), "T": r(best.total, 2)})
    write(res / "a1_single_compound.csv", rows)
    figures.tyre_model(fig / "tyre_model.png")
    figures.single_compound(fig / "a1_single_compound.png", curves)

    print("A2 - several compounds")
    eco = part_a.economy(SAMPLE)
    write(res / "a2_economy.csv", [{"compound": c, "n": v["n"], "S_c(n)": r(v["S"], 2), "rate": r(v["rate"])}
                                   for c, v in eco.items()])
    a2 = optimise(SAMPLE.N, SAMPLE.P, lap_time_a(SAMPLE), min_compounds=1)
    print(f"  optimum {a2} = {a2.total:.2f} s")
    figures.cost_rate(fig / "a2_cost_rate.png")

    print("A3 - pit-loss thresholds")
    write(res / "a3_thresholds.csv", [{**x, "P_lo": r(x["P_lo"], 2), "P_hi": r(x["P_hi"], 2), "A_m": r(x["A_m"], 2)}
                                      for x in part_a.pit_thresholds(SAMPLE)])
    A = [a for a, _ in part_a.running_times(SAMPLE)]
    figures.pit_envelope(fig / "a3_envelope.png", A, part_a.marginal_savings(SAMPLE))

    print("A4 - 20 tracks")
    best = [part_a.structures(t) for t in tracks]
    heur = [part_a.penalty_heuristic(t) for t in tracks]
    extra = [{"margin_to_next_structure": r(b[1].total - b[0].total), "next_structure": str(b[1]),
              "penalty_heuristic": str(h), "heuristic_matches": abs(h.total - b[0].total) < 1e-6}
             for b, h in zip(best, heur)]
    write(res / "a4_strategies.csv", strategy_rows(tracks, [b[0] for b in best], extra))
    figures.strategy_bars(fig / "a4_strategies.png",
                          {"A4 - optimal strategy per track": [(t.name, b[0]) for t, b in zip(tracks, best)]})

    print(f"A5 - Monte Carlo ({args.samples} race days)")
    sims, table = {}, {}
    for name, stints in robust.CANDIDATES.items():
        T, parts = robust.simulate(stints, n=args.samples, breakdown=True)
        sims[name], table[name] = T, {**robust.risk(T), **parts}
    write(res / "a5_risk.csv", [{"strategy": k, **{m: r(v, 2) for m, v in x.items()}} for k, x in table.items()])
    figures.trumpet(fig / "a5_trumpet.png", robust.lap_time_band())
    rng = np.random.default_rng(1)
    figures.parameter_distributions(fig / "a5_distributions.png", robust.sample_parameters(60_000, rng),
                                    robust.sample_pits(60_000, rng))
    figures.risk_profile(fig / "a5_risk.png", sims, table)

    print("A6 - calibration on real races")
    tab, E = calibration.calibrate(calibration.load_stints())
    write(res / "a6_calibration.csv", [{k: (r(v) if isinstance(v, float) else v) for k, v in s.items()} for s in tab])
    print(f"  E_r raw {E['E_raw']}, used {E['E_used']}")
    print(f"  mean d per compound {calibration.compound_means(tab)}; L lower bounds "
          f"{calibration.cliff_lower_bounds(tab)}")
    figures.calibration(fig / "a6_calibration.png", tab)

    print("B1 - fuel model on the sample track")
    w, beta = part_b.PARAM_SETS["a"]
    b1 = part_b.solve(SAMPLE, w, beta)
    write(res / "b1_sample.csv", [{"strategy": "+".join(f"{c}{n}" for c, n in s), **{k: r(v, 2) for k, v in part_b.decompose(SAMPLE, s, w, beta).items()}}
                                  for s in [b1.stints, part_b.order_by_wear(SAMPLE, b1.stints)[::-1],
                                            part_b.order_by_wear(SAMPLE, (("S", 13), ("S", 13), ("S", 12), ("S", 12))),
                                            (("M", 25), ("M", 25))]])
    print(f"  optimum {b1} = {b1.total:.2f} s")

    print("B2 - 20 tracks x 3 parameter sets")
    panels = {}
    for key, (w, beta) in part_b.PARAM_SETS.items():
        sols = [part_b.solve(t, w, beta) for t in tracks]
        write(res / f"b2_{key}.csv", strategy_rows(tracks, sols))
        panels[f"({key}) w={w}, beta={beta}"] = [(t.name, s) for t, s in zip(tracks, sols)]
    figures.strategy_bars(fig / "b2_strategies.png", panels)

    print("B3 - improved model (illustrative parameters)")
    params = {c: B3Params(w=0.06, beta={"S": 0.012, "M": 0.010, "H": 0.008}[c], A=t.D, lam=1.0,
                          u={"S": 0.6, "M": 0.8, "H": 1.0}[c], rho=0.5) for c, t in SAMPLE.tyres.items()}
    b3 = optimise(SAMPLE.N, SAMPLE.P, lap_time_b3(SAMPLE, params))
    write(res / "b3_demo.csv", [{"model": "B3 improved (illustrative)", "strategy": str(b3), "total_time": r(b3.total, 2)}])
    print("done")


if __name__ == "__main__":
    main()
