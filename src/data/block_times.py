"""Block-time constant provider: K_od (journey constant) and R_o (rotation constant).

Neither T_IB_o nor T_OB_o is directly present in the O&D connection table -- only
combined IST arrival/departure timestamps and a per-row total gate-to-gate duration
are given. Two different constants are derived from this, each independent of the
other's estimation method (see plan §4 "Blok süresi sağlayıcısı"):

- K_od = T_IB_o + T_OB_d: observed directly per row (gate_to_gate - gap), aggregated
  by median across valid-gap ([L,U]) TK rows for that market. No least-squares needed.
- R_o = T_IB_o + T_OB_o: recovered via least-squares over the bipartite system of
  per-station T_IB_x / T_OB_y unknowns, one equation per valid-gap TK row
  (T_IB_o + T_OB_d = observed). This system has a 1-parameter shift ambiguity per
  connected component of the o<->d bipartite graph (T_IB_x -> T_IB_x + c,
  T_OB_x -> T_OB_x - c leaves every row residual unchanged); R_o is invariant to
  that shift by construction, so the ridge term used to pin the ambiguity (T_IB_x
  approx= T_OB_x) only affects individual-value reporting, never R_o itself.

v2 (VARSAYIM-15, M5e): when the input DataFrame carries elapsed1_min/elapsed2_min
(per-leg block times from the organizer's ElapsedTime1/ElapsedTime2 columns, added
2026-07-09), K_od and R_o become DIRECT observations instead of a gap-dependent
equation / recovered LS unknowns -- implied_k = gate_to_gate_min - gap_min reduces
algebraically to exactly elapsed1_min + elapsed2_min (gate_to_gate_min is now
COMPOSED as elapsed1_min + gap_min + elapsed2_min by loaders.load_od_table's
wrap-fix), so K_od no longer depends on gap at all. The [L,U] gap filter -- a
data-quality guard against invalid/placeholder displayed durations -- is dropped
for this path: Elapsed1/Elapsed2 are populated and internally consistent
regardless of gap validity (verified against the real v2 file, 0/57,317
exceptions; docs/decisions.md 2026-07-11). Similarly, Elapsed1 on a dep1==o row
IS a direct observation of T_IB_o, Elapsed2 on an arr2==o row IS a direct
observation of T_OB_o -- per-station medians replace the bipartite LS solve
entirely, no shift-ambiguity/ridge term needed (these are observations, not
recovered unknowns). Interface (all 4 public methods/properties) is unchanged;
only __init__ picks a different internal path based on column presence.
"""
import logging

import numpy as np
import pandas as pd


class BlockTimeProvider:
    def __init__(self, tk_rows: pd.DataFrame, L: int, U: int, ridge: float = 1e-6):
        self._L = L
        self._U = U
        self._has_elapsed = {"elapsed1_min", "elapsed2_min"}.issubset(tk_rows.columns)

        if self._has_elapsed:
            self._init_from_elapsed(tk_rows)
        else:
            self._init_from_ls(tk_rows, ridge)

    def _init_from_ls(self, tk_rows: pd.DataFrame, ridge: float):
        gap_min = (tk_rows["dep_time"] - tk_rows["arr_time"]).dt.total_seconds() / 60
        valid = tk_rows[(gap_min >= self._L) & (gap_min <= self._U)].copy()
        valid["gap_min"] = gap_min[valid.index]
        valid["implied_k"] = valid["gate_to_gate_min"] - valid["gap_min"]

        self._journey_constants = (
            valid.groupby(["dep1", "arr2"])["implied_k"].median().to_dict()
        )

        self._rotation_constants, self._t_ib, self._t_ob, self._residuals, self._single_role = (
            self._solve_rotation_ls(valid, ridge)
        )

    def _init_from_elapsed(self, tk_rows: pd.DataFrame):
        rows = tk_rows.copy()
        rows["implied_k"] = rows["elapsed1_min"] + rows["elapsed2_min"]

        self._journey_constants = rows.groupby(["dep1", "arr2"])["implied_k"].median().to_dict()

        t_ib = rows.groupby("dep1")["elapsed1_min"].median()
        t_ob = rows.groupby("arr2")["elapsed2_min"].median()
        self._t_ib = t_ib.to_dict()
        self._t_ob = t_ob.to_dict()

        stations = sorted(set(t_ib.index) | set(t_ob.index))
        self._rotation_constants = {
            s: self._t_ib.get(s, 0.0) + self._t_ob.get(s, 0.0) for s in stations
        }
        self._single_role = {
            s for s in stations if not (s in t_ib.index and s in t_ob.index)
        }
        # Same per-row formula as the LS path's row_residuals (T_IB[dep1] +
        # T_OB[arr2] - implied_k, the row's own "equation" residual) -- here
        # T_IB/T_OB are direct medians rather than an LS solution, but every
        # row's dep1/arr2 is guaranteed present in t_ib/t_ob (both indices
        # are built from these same rows), so no NaN case arises.
        self._residuals = pd.Series(
            [self._t_ib[row.dep1] + self._t_ob[row.arr2] - row.implied_k for row in rows.itertuples()],
            index=rows.index, name="rotation_ls_residual_min",
        )

        spreads = rows.groupby(["dep1", "arr2"])["implied_k"].agg(lambda s: s.max() - s.min())
        if len(spreads):
            logging.info(
                "BlockTimeProvider (elapsed path): K_od spread across %d markets -- "
                "median=%.1f p90=%.1f max=%.1f",
                len(spreads), spreads.median(), spreads.quantile(0.9), spreads.max(),
            )

    def get_journey_constant(self, o: str, d: str) -> float:
        return self._journey_constants[(o, d)]

    def get_journey_constant_estimate(self, o: str, d: str) -> float:
        """M5 fallback (VARSAYIM-8, ASSUMPTIONS.md): direct median-based K_od
        needs at least one TK row with a VALID ([L,U]) gap for that exact
        (o,d) pair -- real full data has 575/1329 markets with none (every
        baseline row for that pair is invalid, only reachable via the
        adjustable window). K_od=T_IB_o+T_OB_d is estimated instead from
        R_o's OWN least-squares system (T_IB_o, T_OB_d individually) --
        shift-invariant by the SAME proof as R_o (a global T_IB+=c,T_OB-=c
        shift across a connected component leaves every row equation
        T_IB_o+T_OB_d=k unchanged, so this specific o+d combination is
        exactly as recoverable as the o+o combination R_o uses). Raises
        KeyError only if either station was never observed in ANY role."""
        return self._t_ib[o] + self._t_ob[d]

    def get_rotation_constant(self, o: str) -> float:
        return self._rotation_constants[o]

    @property
    def single_role_stations(self) -> set:
        return self._single_role

    @property
    def rotation_residuals(self) -> pd.Series:
        return self._residuals

    @staticmethod
    def _solve_rotation_ls(valid: pd.DataFrame, ridge: float):
        stations = sorted(set(valid["dep1"]) | set(valid["arr2"]))
        idx = {s: i for i, s in enumerate(stations)}
        n = len(stations)
        # unknown vector layout: [T_IB_0..T_IB_{n-1}, T_OB_0..T_OB_{n-1}]

        origin_stations = set(valid["dep1"])
        dest_stations = set(valid["arr2"])
        single_role = {s for s in stations if not (s in origin_stations and s in dest_stations)}

        n_rows = len(valid)
        n_ridge = n
        A = np.zeros((n_rows + n_ridge, 2 * n))
        b = np.zeros(n_rows + n_ridge)

        for i, (_, row) in enumerate(valid.iterrows()):
            oi, di = idx[row["dep1"]], idx[row["arr2"]]
            A[i, oi] = 1.0
            A[i, n + di] = 1.0
            b[i] = row["implied_k"]

        for j, s in enumerate(stations):
            r = n_rows + j
            A[r, idx[s]] = ridge
            A[r, n + idx[s]] = -ridge
            b[r] = 0.0

        solution, *_ = np.linalg.lstsq(A, b, rcond=None)
        t_ib = solution[:n]
        t_ob = solution[n:]

        rotation_constants = {s: t_ib[idx[s]] + t_ob[idx[s]] for s in stations}
        t_ib_by_station = {s: t_ib[idx[s]] for s in stations}
        t_ob_by_station = {s: t_ob[idx[s]] for s in stations}

        row_residuals = A[:n_rows] @ solution - b[:n_rows]
        residuals = pd.Series(row_residuals, index=valid.index, name="rotation_ls_residual_min")

        return rotation_constants, t_ib_by_station, t_ob_by_station, residuals, single_role
