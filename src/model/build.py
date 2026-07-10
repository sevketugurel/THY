"""Pyomo model construction.

M0 scope (kept for M0's own tests): a deliberately trivial model (free x_pi in
{0,1}, linear rho-weighted reward, no constraints) that proved the
build->solve->extract chain works end-to-end.

M1 scope (build_model): B (bağlantı uygunluğu, bidirectional reification) + C
(Modul-5 monoton slot).

M2 scope (build_model_with_competition): + D (rakip yenme ve sıralama).

M3 scope (build_model_with_operations): + A (rotasyon) + G (düzenlilik).

M4 scope (build_model_m4): + E1 (yönsel sayı dengesi) + E2 (JT-farkı,
koşullu aktivasyon) + F (kova bağlama, rezidüel kapasite). Full model
(A-G tamamı). main.py henüz bu fonksiyonu KULLANMIYOR -- tek entegrasyon
geçişi bekleniyor (bkz. CLAUDE.md Durum).
"""
import pyomo.environ as pyo

from src.candidates.generate import Candidate
from src.model.constraints_balance import add_e1_constraints, add_e2_constraints
from src.model.constraints_capacity import add_f_constraints, compute_out_of_scope_baselines, compute_residual_capacity
from src.model.constraints_competition import add_d_constraints, add_rank_onehot
from src.model.constraints_operations import add_a_constraints, add_g_constraints
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.model.objective import add_connection_reward_objective, add_ranking_reward_objective


def build_trivial_model(candidates: list[Candidate], rho: dict) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()

    model.CANDIDATES = pyo.Set(initialize=list(range(len(candidates))), ordered=True)
    model.x = pyo.Var(model.CANDIDATES, domain=pyo.Binary)

    model._candidates = candidates  # stashed for result extraction

    def obj_rule(m):
        return sum(rho[(candidates[i].o, candidates[i].d)] * m.x[i] for i in m.CANDIDATES)

    model.objective = pyo.Objective(rule=obj_rule, sense=pyo.maximize)

    return model


def build_model(candidates: list[Candidate], rho: dict, L: int = 60, U: int = 300) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model._candidates = candidates

    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_connection_reward_objective(model, rho)

    return model


def build_model_with_competition(
    candidates: list[Candidate], rho: dict, journey_constants: dict, rival_data: dict,
    b_od_data: dict, ranking_table, L: int = 60, U: int = 300, monotonic: bool = True,
) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model._candidates = candidates

    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_connection_reward_objective(model, rho)

    n_by_market = add_d_constraints(model, candidates, journey_constants, rival_data, monotonic=monotonic)
    add_rank_onehot(model, n_by_market)
    add_ranking_reward_objective(model, rho, b_od_data, ranking_table, n_by_market)

    return model


def build_model_with_operations(
    candidates: list[Candidate], rho: dict, journey_constants: dict, rival_data: dict,
    b_od_data: dict, ranking_table, pairs_df, r_o_lookup: dict, tau: int, x_dev: int,
    epoch_anchor, L: int = 60, U: int = 300, monotonic: bool = True,
) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model._candidates = candidates

    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_connection_reward_objective(model, rho)

    n_by_market = add_d_constraints(model, candidates, journey_constants, rival_data, monotonic=monotonic)
    add_rank_onehot(model, n_by_market)
    add_ranking_reward_objective(model, rho, b_od_data, ranking_table, n_by_market)

    add_a_constraints(model, candidates, pairs_df, r_o_lookup, tau)
    add_g_constraints(model, candidates, epoch_anchor, x_dev)

    return model


def build_model_m4(
    candidates: list[Candidate], rho: dict, journey_constants: dict, rival_data: dict,
    b_od_data: dict, ranking_table, pairs_df, r_o_lookup: dict, tau: int, x_dev: int,
    epoch_anchor, alpha: float, gamma: int, tk_rows, bucket_size_min: int,
    capacity_departure: int, capacity_arrival: int,
    L: int = 60, U: int = 300, monotonic: bool = True,
) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model._candidates = candidates

    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_connection_reward_objective(model, rho)

    n_by_market = add_d_constraints(model, candidates, journey_constants, rival_data, monotonic=monotonic)
    add_rank_onehot(model, n_by_market)
    add_ranking_reward_objective(model, rho, b_od_data, ranking_table, n_by_market)

    # F'in rezidüel kapasitesi VE A'nın kısmi-kapsam rotasyon edge-case'i
    # AYNI kaynağı paylaşır (bir kez hesaplanır -- VARSAYIM, ASSUMPTIONS.md).
    out_of_scope_baselines = compute_out_of_scope_baselines(tk_rows, model, epoch_anchor)

    add_a_constraints(model, candidates, pairs_df, r_o_lookup, tau, out_of_scope_baselines)
    add_g_constraints(model, candidates, epoch_anchor, x_dev)

    add_e1_constraints(model, candidates, alpha)
    add_e2_constraints(model, candidates, journey_constants, gamma)

    residual_dep, residual_arr = compute_residual_capacity(
        out_of_scope_baselines, bucket_size_min, capacity_departure, capacity_arrival,
    )
    add_f_constraints(model, bucket_size_min, capacity_departure, capacity_arrival, residual_dep, residual_arr)

    return model


def build_feasibility_model(
    candidates: list[Candidate], journey_constants: dict, pairs_df, r_o_lookup: dict, tau: int, x_dev: int,
    epoch_anchor, alpha: float, gamma: int, tk_rows, bucket_size_min: int,
    capacity_departure: int, capacity_arrival: int, L: int = 60, U: int = 300,
) -> pyo.ConcreteModel:
    """M5c §3 (docs/decisions.md 2026-07-10, kullanıcı "Plan B" talebi):
    reward'ı TAMAMEN dışarıda bırakan, yalnızca OPERASYONEL fizibiliteyi
    (A/E1/E2/F/G + B'nin pencere-uygunluğu) kuran küçültülmüş model.

    Ultrathink (tek paragraf, model.md'ye de işlenecek): C (monoton slot) ve
    D (rakip yenme + rank_onehot) SADECE ödül fonksiyonunun sıralama
    terimini hesaplamak için var -- hiçbiri t_arr/t_dep/x/gap üzerinde bir
    kısıt KURMUYOR (C'nin `s` değişkenleri ve D'nin `beat`/`beaten`/
    `rank_onehot` değişkenleri yalnızca BİRBİRLERİNE ve x_pi'ye bakan, x'i
    GERİYE doğru kısıtlamayan yardımcı makine). Dolayısıyla (t,x,gap)
    üzerindeki ortak fizibilite kümesi build_model_m4 ile TAMAMEN AYNI --
    bu modelde bulunan HER feasible (t,x,gap) noktası tam modelde de
    feasible'dır (C/D'nin kendi değişkenleri, x sabitken HER ZAMAN ayrıca
    inşa edilebilir: s monoton/toplam kısıtı x'in TOPLAMINA göre her zaman
    çözülebilir bir LP'dir, D'nin beat/rank_onehot'u candidate-bazlı Big-M
    reifikasyonlarla x'e göre HER ZAMAN tutarlı bir atama kabul eder).
    Yani bu bir gevşetme DEĞİL, reward-hesaplama makinesinin feasibility'ye
    hiç katkısı olmayan kısmının ÇIKARILMASI -- warm-start/local-branching
    tohumu olarak tam modele TAŞINABİLİR.
    """
    model = pyo.ConcreteModel()
    model._candidates = candidates

    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)

    out_of_scope_baselines = compute_out_of_scope_baselines(tk_rows, model, epoch_anchor)
    add_a_constraints(model, candidates, pairs_df, r_o_lookup, tau, out_of_scope_baselines)
    add_g_constraints(model, candidates, epoch_anchor, x_dev)

    add_e1_constraints(model, candidates, alpha)
    add_e2_constraints(model, candidates, journey_constants, gamma)

    residual_dep, residual_arr = compute_residual_capacity(
        out_of_scope_baselines, bucket_size_min, capacity_departure, capacity_arrival,
    )
    add_f_constraints(model, bucket_size_min, capacity_departure, capacity_arrival, residual_dep, residual_arr)

    return model
