"""A (zaman sınırları ve uçak rotasyonu) kısıt grubu.

Doğruluk argümanı için bkz. tests/solve/test_m3_constraints_a.py docstring.
Özet: "aynı uçak IST->o->IST" KOŞULSUZ bir operasyonel kural (x_pi'den
bağımsız): dönüş bacağının IST varışı, gidiş bacağının IST kalkışından en az
R_o+tau kadar sonra olmalı. Yalnızca Pair grubundaki ARDIŞIK (Orig==IST
sonra Dest==IST) alt-çiftlere uygulanır -- IST'e değmeyen ara bacaklar
(ör. IST->MEX->CUN->IST'teki MEX->CUN) modelin değişken kapsamı dışında,
bu grup için hiç kısıt kurulmaz (VARSAYIM, bkz. ASSUMPTIONS.md).
"""
import pyomo.environ as pyo


def build_rotation_pairs(model, pairs_df):
    """Pair grubu içindeki ardışık (OB->IB, IST üzerinden) alt-çiftleri,
    HER İKİ bacağın da modelde (ARR_INSTANCES/DEP_INSTANCES) bulunduğu
    ortak günlerle birlikte döner: list of (ob_flno, ib_flno, gun, station)."""
    ob_guns = {}
    ib_guns = {}
    for (role, flno, gun) in model.DEP_INSTANCES:
        if role == "OB":
            ob_guns.setdefault(flno, set()).add(gun)
    for (role, flno, gun) in model.ARR_INSTANCES:
        if role == "IB":
            ib_guns.setdefault(flno, set()).add(gun)

    rotation_pairs = []
    for _, group in pairs_df.groupby("pair"):
        rows = group.to_dict("records")
        for i in range(len(rows) - 1):
            leg1, leg2 = rows[i], rows[i + 1]
            if leg1["orig"] != "IST" or leg2["dest"] != "IST" or leg1["dest"] != leg2["orig"]:
                continue
            station = leg1["dest"]
            ob_flno, ib_flno = leg1["flno"], leg2["flno"]
            common_guns = ob_guns.get(ob_flno, set()) & ib_guns.get(ib_flno, set())
            for gun in common_guns:
                rotation_pairs.append((ob_flno, ib_flno, gun, station))
    return rotation_pairs


def _day_offsets(candidates, epoch_anchor):
    """(role,flno,gun) -> epoch-minute of THAT INSTANCE'S OWN calendar-day
    midnight, relative to the shared global epoch_anchor.

    Kritik düzeltme (ultrathink sonrası bulunamayan, İLK solve denemesinde
    infeasibility olarak yakalanan bug): epoch_anchor TÜM veri kümesi için
    TEK bir GLOBAL referans (compute_epoch_anchor, plan §Context) -- Gün=2'nin
    zamanları Gün=1'inkinden ~1440dk daha BÜYÜK epoch-değerlere sahip (farklı
    takvim günü). G'nin "spread" kontrolü bu HAM epoch değerlerini doğrudan
    karşılaştırırsa, aynı saat-of-day'e sahip iki gün bile ~1440dk'lık SAHTE
    bir farkla karşılaşır (X_dev=15 ile ASLA uzlaştırılamaz -> infeasible).
    Çözüm: her (role,flno,gun)'u KENDİ takvim gününün gece yarısına göre
    normalize et (day_offset çıkar) -- T_ref artık "gün-içi referans dakika"
    temsil eder, gerçek saat-of-day karşılaştırması yapılır."""
    offsets = {}
    for c in candidates:
        offsets[c.r1_id] = int((c.arr_time.normalize() - epoch_anchor).total_seconds() // 60)
        offsets[c.r2_id] = int((c.dep_time.normalize() - epoch_anchor).total_seconds() // 60)
    return offsets


def add_g_constraints(model, candidates, epoch_anchor, x_dev: int):
    """Referans-zaman formülasyonu (doğruluk argümanı: tests/solve/test_m3_constraints_g.py):
    serbest T[role,flno], her gün (t-day_offset) in [T, T+x_dev] -- max-min<=x_dev
    ile TAM eşdeğer (gün-içi saat-of-day üzerinden, bkz. _day_offsets), O(H)
    kısıt (H=gün sayısı), naif O(H^2) çift-karşılaştırmadan daha sıkı.
    Yalnızca 2+ farklı günde modelde bulunan (role,flno) çiftleri için kurulur."""
    day_offset = _day_offsets(candidates, epoch_anchor)

    role_flno_guns = {}
    for (role, flno, gun) in model.ARR_INSTANCES:
        if role == "IB":
            role_flno_guns.setdefault(("IB", flno), set()).add(gun)
    for (role, flno, gun) in model.DEP_INSTANCES:
        if role == "OB":
            role_flno_guns.setdefault(("OB", flno), set()).add(gun)

    multi_day = {k: sorted(guns) for k, guns in role_flno_guns.items() if len(guns) >= 2}

    model.G_FLIGHTS = pyo.Set(initialize=list(multi_day.keys()), dimen=2, ordered=True)
    if not multi_day:
        return multi_day

    def t_bounds_rule(m, role, flno):
        guns = multi_day[(role, flno)]
        var = m.t_arr if role == "IB" else m.t_dep
        offs = [day_offset[(role, flno, g)] for g in guns]
        los = [var[role, flno, g].lb - off for g, off in zip(guns, offs)]
        his = [var[role, flno, g].ub - off for g, off in zip(guns, offs)]
        return (min(los), max(his))
    model.T_ref = pyo.Var(model.G_FLIGHTS, domain=pyo.Integers, bounds=t_bounds_rule)

    day_index = [(role, flno, gun) for (role, flno), guns in multi_day.items() for gun in guns]
    model.G_FLIGHT_DAYS = pyo.Set(initialize=day_index, dimen=3, ordered=True)

    def lower_rule(m, role, flno, gun):
        t = m.t_arr[role, flno, gun] if role == "IB" else m.t_dep[role, flno, gun]
        return t - day_offset[(role, flno, gun)] >= m.T_ref[role, flno]
    model.g_lower = pyo.Constraint(model.G_FLIGHT_DAYS, rule=lower_rule)

    def upper_rule(m, role, flno, gun):
        t = m.t_arr[role, flno, gun] if role == "IB" else m.t_dep[role, flno, gun]
        return t - day_offset[(role, flno, gun)] <= m.T_ref[role, flno] + x_dev
    model.g_upper = pyo.Constraint(model.G_FLIGHT_DAYS, rule=upper_rule)

    return multi_day


def add_a_constraints(model, candidates, pairs_df, r_o_lookup: dict, tau: int):
    rotation_pairs = build_rotation_pairs(model, pairs_df)

    index = [(ob, ib, gun) for (ob, ib, gun, station) in rotation_pairs]
    station_by_pair = {(ob, ib, gun): station for (ob, ib, gun, station) in rotation_pairs}

    model.ROTATION_PAIRS = pyo.Set(initialize=index, dimen=3, ordered=True)

    def rotation_rule(m, ob_flno, ib_flno, gun):
        station = station_by_pair[ob_flno, ib_flno, gun]
        r_o = r_o_lookup[station]
        return m.t_arr["IB", ib_flno, gun] >= m.t_dep["OB", ob_flno, gun] + r_o + tau
    model.a_rotation = pyo.Constraint(model.ROTATION_PAIRS, rule=rotation_rule)

    return rotation_pairs
