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
"""
import numpy as np
import pandas as pd


class BlockTimeProvider:
    def __init__(self, tk_rows: pd.DataFrame, L: int, U: int, ridge: float = 1e-6):
        self._L = L
        self._U = U

        gap_min = (tk_rows["dep_time"] - tk_rows["arr_time"]).dt.total_seconds() / 60
        valid = tk_rows[(gap_min >= L) & (gap_min <= U)].copy()
        valid["gap_min"] = gap_min[valid.index]
        valid["implied_k"] = valid["gate_to_gate_min"] - valid["gap_min"]

        self._journey_constants = (
            valid.groupby(["dep1", "arr2"])["implied_k"].median().to_dict()
        )

        self._rotation_constants, self._t_ib, self._t_ob, self._residuals, self._single_role = (
            self._solve_rotation_ls(valid, ridge)
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
