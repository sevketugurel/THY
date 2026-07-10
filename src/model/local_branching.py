"""M5d Adım 2 (docs/decisions.md 2026-07-10, local-branching fallback):
Fischetti-Lodi tarzı bir trust-region kısıtı. Elimizdeki tek referans nokta
(A+G+F'in optimal çözümü + B'nin reifikasyonu) hard E1/E2 kısıtlarını
1879 yerde ihlal ediyor (bkz. runs/warm_start_elastic_20260710T203810Z.log.json)
-- bu noktayı build_model_m4'e OLDUĞU GİBİ warm-start olarak vermek anlamsız
(zaten infeasible). Bunun yerine: referans noktadan en fazla k adet zaman
örneğinin (t_arr/t_dep) FARKLI olmasına izin veren bir komşuluk kısıtlıyoruz
-- geri kalan örnekler referansa göre serbestçe hareket edemez, ama solver
KENDİSİ o k serbest örneği kullanarak E1/E2'yi düzeltebilir.

Doğruluk argümanı: her örnek r için bir moved[r] binary'si var. Eğer
moved[r]=0 ise, Big-M ikisi de sıfıra sıkışır (M=ub-lb, t ve referans ikisi
de [lb,ub] içinde olduğu için |t-ref|<=ub-lb HER ZAMAN doğru -- yani M asla
gerçek farkı KISITLAMAZ, sadece moved[r]=1 olmadıkça t'yi referansa sabitler).
moved[r]=1 olduğunda kısıt gevşer (t serbest, kendi [lb,ub] sınırları
içinde). Toplam moved sayısı k'yı aşamaz."""
import pyomo.environ as pyo


def add_local_branching(model, reference_arr: dict, reference_dep: dict, k: int):
    """Requires add_flight_time_variables to have already run (model.t_arr,
    model.t_dep, model.ARR_INSTANCES, model.DEP_INSTANCES)."""
    missing_arr = set(model.ARR_INSTANCES) - set(reference_arr)
    missing_dep = set(model.DEP_INSTANCES) - set(reference_dep)
    assert not missing_arr, f"reference_arr eksik örnekler: {sorted(missing_arr)[:5]}"
    assert not missing_dep, f"reference_dep eksik örnekler: {sorted(missing_dep)[:5]}"

    model.moved_arr = pyo.Var(model.ARR_INSTANCES, domain=pyo.Binary)
    model.moved_dep = pyo.Var(model.DEP_INSTANCES, domain=pyo.Binary)

    def arr_up_rule(m, role, flno, gun):
        r = (role, flno, gun)
        M = m.t_arr[r].ub - m.t_arr[r].lb
        return m.t_arr[r] - reference_arr[r] <= M * m.moved_arr[r]
    model.local_branch_arr_up = pyo.Constraint(model.ARR_INSTANCES, rule=arr_up_rule)

    def arr_down_rule(m, role, flno, gun):
        r = (role, flno, gun)
        M = m.t_arr[r].ub - m.t_arr[r].lb
        return reference_arr[r] - m.t_arr[r] <= M * m.moved_arr[r]
    model.local_branch_arr_down = pyo.Constraint(model.ARR_INSTANCES, rule=arr_down_rule)

    def dep_up_rule(m, role, flno, gun):
        r = (role, flno, gun)
        M = m.t_dep[r].ub - m.t_dep[r].lb
        return m.t_dep[r] - reference_dep[r] <= M * m.moved_dep[r]
    model.local_branch_dep_up = pyo.Constraint(model.DEP_INSTANCES, rule=dep_up_rule)

    def dep_down_rule(m, role, flno, gun):
        r = (role, flno, gun)
        M = m.t_dep[r].ub - m.t_dep[r].lb
        return reference_dep[r] - m.t_dep[r] <= M * m.moved_dep[r]
    model.local_branch_dep_down = pyo.Constraint(model.DEP_INSTANCES, rule=dep_down_rule)

    model.local_branch_budget = pyo.Constraint(
        expr=sum(model.moved_arr[r] for r in model.ARR_INSTANCES)
        + sum(model.moved_dep[r] for r in model.DEP_INSTANCES) <= k
    )
