"""F (hub kova/kapasite bağlama) kısıt grubu.

Doğruluk argümanı için bkz. tests/solve/test_m4_constraints_f.py ve
tests/unit/test_capacity.py docstring. Özet: her ayarlanabilir uçuş örneği
(t_arr/t_dep) HER ZAMAN hub'da fiziksel olarak bir 10-dakikalık kovaya denk
gelir -- x_pi'den (bağlantı sunuluyor mu) TAMAMEN bağımsız bir fiziksel
gerçek. z[role,flno,gun,b] yalnızca PENCERE-ULAŞILABİLİR kovalar için
tanımlanır (t'nin kendi [lo,hi] Var bounds'unun kesiştiği kovalar) --
GÜNÜN TÜM kovaları (144, bucket_size=10) DEĞİL, M5 ölçek performansı için
kritik bir budama (kullanıcının kendi tahmini: ~19/uçuş).

Bucket-time bağlama (M5c row-explosion fix, `docs/lp_anatomy.md` öncelik
#1, ultrathink): kovalar t'nin ekseninde ARDIŞIK ve AYRIK bir bölme
oluşturduğundan (kova b == [b*bucket_size, (b+1)*bucket_size)), t HER ZAMAN
t = bucket_start(b)*z[r,b] + offset[r] şeklinde tek-anlamlı (bijective)
çözülür -- offset[r] in [0, bucket_size-1] YENİ bir tamsayı değişken, z
Sum_b z=1 (zaten var) sayesinde toplamda yalnızca SEÇİLEN b'nin terimi
hayatta kalır. Bu TEK eşitlik, eski per-bucket Big-M ÇİFTİNİN (~2*37 satır,
kova başına biri lower biri upper) yerini alır -- hem Big-M SIFIRLANIR
(gevşeklik yok, LP'yi de sıkılaştırır) hem satır sayısı N_INSTANCES*N_BUCKETS
yerine N_INSTANCES'a düşer. Doğruluk: t'nin kendi [lo,hi] Var bound'u zaten
solver tarafından ayrıca uygulanıyor: seçilen b, t'nin [lo,hi] içindeki
gerçek konumuna göre offset ile tam eşleşir (eski Big-M'in b'nin uç
kovalarında zaten REDÜNDAN ürettiği davranışla birebir aynı sonuç, bkz.
`tests/solve/test_m4_constraints_f.py`).

Kapsam-dışı (modelin hiç değişkeni olmayan) TK bacakları, kendi HAM
baseline zamanlarında SABİT işgal ettikleri kabul edilir (VARSAYIM,
ASSUMPTIONS.md) ve kapasiteden düşülür (`compute_residual_capacity`) --
model kurulmadan önce bir kez, tam-tarama precompute.
"""
from collections import defaultdict

import pyomo.environ as pyo


def derive_window_reachable_buckets(lo: int, hi: int, bucket_size_min: int) -> list:
    """Kova k kanonik olarak [k*bucket_size,(k+1)*bucket_size) aralığını
    temsil eder. [lo,hi] ile kesişen TÜM kovaları döner (floor division,
    negatif lo için de doğru -- Python'un // operatörü zaten floor)."""
    k_lo = lo // bucket_size_min
    k_hi = hi // bucket_size_min
    return list(range(k_lo, k_hi + 1))


def compute_out_of_scope_baselines(tk_rows, model, epoch_anchor) -> dict:
    """Tüm TK satırlarını tarar, model'in ARR_INSTANCES/DEP_INSTANCES
    kapsamı DIŞINDA kalan (role,flno,gun) örneklerinin HAM (baseline)
    epoch-dakika zamanını döner -- bu uçuşlar modelde hiç değişken değil
    (candidate üretiminde hiçbir eşleşmeleri achievable-range kapısını
    geçmemiş), F'nin rezidüel kapasite hesabı VE A'nın rotasyon kısıtının
    "kısmen kapsam-dışı" edge-case'i için ortak kaynak (VARSAYIM, bkz
    ASSUMPTIONS.md)."""
    in_scope_arr = set(model.ARR_INSTANCES)
    in_scope_dep = set(model.DEP_INSTANCES)

    def epoch_min(ts):
        return int((ts - epoch_anchor).total_seconds() // 60)

    baselines = {}
    for row in tk_rows.itertuples():
        arr_key = ("IB", int(row.flno1), int(row.gun))
        if arr_key not in in_scope_arr and arr_key not in baselines:
            baselines[arr_key] = epoch_min(row.arr_time)
        dep_key = ("OB", int(row.flno2), int(row.gun))
        if dep_key not in in_scope_dep and dep_key not in baselines:
            baselines[dep_key] = epoch_min(row.dep_time)
    return baselines


def compute_residual_capacity(out_of_scope_baselines: dict, bucket_size_min: int,
                               capacity_departure: int, capacity_arrival: int) -> tuple:
    """Kapsam-dışı TK bacaklarının kendi baseline zamanına denk gelen
    kovadan kapasiteyi düşer (VARSAYIM). Dönüş: (residual_dep, residual_arr)
    -- yalnızca en az bir kapsam-dışı uçuşun işgal ettiği kovalar için
    anahtar var; diğerleri ima edilen taban kapasitede."""
    dep_occupancy = defaultdict(int)
    arr_occupancy = defaultdict(int)
    for (role, flno, gun), baseline_min in out_of_scope_baselines.items():
        bucket = baseline_min // bucket_size_min
        if role == "OB":
            dep_occupancy[bucket] += 1
        else:
            arr_occupancy[bucket] += 1
    residual_dep = {b: max(0, capacity_departure - n) for b, n in dep_occupancy.items()}
    residual_arr = {b: max(0, capacity_arrival - n) for b, n in arr_occupancy.items()}
    return residual_dep, residual_arr


def add_f_constraints(model, bucket_size_min: int, capacity_departure: int, capacity_arrival: int,
                       residual_dep: dict = None, residual_arr: dict = None):
    if residual_dep is None:
        residual_dep = {}
    if residual_arr is None:
        residual_arr = {}

    dep_buckets = {
        r: derive_window_reachable_buckets(model.t_dep[r].lb, model.t_dep[r].ub, bucket_size_min)
        for r in model.DEP_INSTANCES
    }
    arr_buckets = {
        r: derive_window_reachable_buckets(model.t_arr[r].lb, model.t_arr[r].ub, bucket_size_min)
        for r in model.ARR_INSTANCES
    }

    dep_index = [(role, flno, gun, b) for (role, flno, gun) in model.DEP_INSTANCES for b in dep_buckets[role, flno, gun]]
    arr_index = [(role, flno, gun, b) for (role, flno, gun) in model.ARR_INSTANCES for b in arr_buckets[role, flno, gun]]
    model.DEP_Z_INDEX = pyo.Set(initialize=dep_index, dimen=4, ordered=True)
    model.ARR_Z_INDEX = pyo.Set(initialize=arr_index, dimen=4, ordered=True)
    model.z_dep = pyo.Var(model.DEP_Z_INDEX, domain=pyo.Binary)
    model.z_arr = pyo.Var(model.ARR_Z_INDEX, domain=pyo.Binary)

    def dep_sum_rule(m, role, flno, gun):
        return sum(m.z_dep[role, flno, gun, b] for b in dep_buckets[role, flno, gun]) == 1
    model.f_dep_sum = pyo.Constraint(model.DEP_INSTANCES, rule=dep_sum_rule)

    def arr_sum_rule(m, role, flno, gun):
        return sum(m.z_arr[role, flno, gun, b] for b in arr_buckets[role, flno, gun]) == 1
    model.f_arr_sum = pyo.Constraint(model.ARR_INSTANCES, rule=arr_sum_rule)

    model.dep_offset = pyo.Var(model.DEP_INSTANCES, domain=pyo.NonNegativeIntegers,
                                bounds=(0, bucket_size_min - 1))
    model.arr_offset = pyo.Var(model.ARR_INSTANCES, domain=pyo.NonNegativeIntegers,
                                bounds=(0, bucket_size_min - 1))

    def dep_decompose_rule(m, role, flno, gun):
        return m.t_dep[role, flno, gun] == (
            sum(b * bucket_size_min * m.z_dep[role, flno, gun, b] for b in dep_buckets[role, flno, gun])
            + m.dep_offset[role, flno, gun]
        )
    model.f_dep_decompose = pyo.Constraint(model.DEP_INSTANCES, rule=dep_decompose_rule)

    def arr_decompose_rule(m, role, flno, gun):
        return m.t_arr[role, flno, gun] == (
            sum(b * bucket_size_min * m.z_arr[role, flno, gun, b] for b in arr_buckets[role, flno, gun])
            + m.arr_offset[role, flno, gun]
        )
    model.f_arr_decompose = pyo.Constraint(model.ARR_INSTANCES, rule=arr_decompose_rule)

    dep_bucket_values = sorted(set(b for (_, _, _, b) in dep_index))
    arr_bucket_values = sorted(set(b for (_, _, _, b) in arr_index))
    model.DEP_BUCKET_VALUES = pyo.Set(initialize=dep_bucket_values, ordered=True)
    model.ARR_BUCKET_VALUES = pyo.Set(initialize=arr_bucket_values, ordered=True)

    def dep_capacity_rule(m, b):
        cap = residual_dep.get(b, capacity_departure)
        relevant = [(role, flno, gun) for (role, flno, gun) in model.DEP_INSTANCES if b in dep_buckets[role, flno, gun]]
        return sum(m.z_dep[role, flno, gun, b] for (role, flno, gun) in relevant) <= cap
    model.f_dep_capacity = pyo.Constraint(model.DEP_BUCKET_VALUES, rule=dep_capacity_rule)

    def arr_capacity_rule(m, b):
        cap = residual_arr.get(b, capacity_arrival)
        relevant = [(role, flno, gun) for (role, flno, gun) in model.ARR_INSTANCES if b in arr_buckets[role, flno, gun]]
        return sum(m.z_arr[role, flno, gun, b] for (role, flno, gun) in relevant) <= cap
    model.f_arr_capacity = pyo.Constraint(model.ARR_BUCKET_VALUES, rule=arr_capacity_rule)

    return dep_buckets, arr_buckets
