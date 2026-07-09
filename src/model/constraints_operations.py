"""A (zaman sınırları ve uçak rotasyonu) kısıt grubu.

Doğruluk argümanı için bkz. tests/solve/test_m3_constraints_a.py docstring.
Özet: "aynı uçak IST->o->IST" KOŞULSUZ bir operasyonel kural (x_pi'den
bağımsız): dönüş bacağının IST varışı, gidiş bacağının IST kalkışından en az
R_o+tau kadar sonra olmalı. Yalnızca Pair grubundaki ARDIŞIK (Orig==IST
sonra Dest==IST) alt-çiftlere uygulanır -- IST'e değmeyen ara bacaklar
(ör. IST->MEX->CUN->IST'teki MEX->CUN) modelin değişken kapsamı dışında,
bu grup için hiç kısıt kurulmaz (VARSAYIM, bkz. ASSUMPTIONS.md).

Edge case (M4/F ile birlikte bulundu): bir Pair alt-çiftinin bacaklarından
BİRİ modelin candidate üretiminde hiç yer almamışsa (kapsam dışı -- ör.
achievable-range kapısını hiçbir eşleşmede geçemedi), rotasyon kuralı
SESSİZCE atlanmamalı -- kapsam dışı bacak kendi ham baseline zamanında
SABİT kabul edilip (VARSAYIM), in-scope bacağa karşı kısıt yine kurulur
(`build_rotation_pairs`'in `partial_pairs` çıktısı, `out_of_scope_baselines`
girdisiyle -- bkz. `src.model.constraints_capacity.compute_out_of_scope_baselines`).
"""
import pyomo.environ as pyo

from src.model.day_clustering import cluster_flight_days


def build_rotation_pairs(model, pairs_df, out_of_scope_baselines: dict = None):
    """Pair grubu içindeki ardışık (OB->IB, IST üzerinden) alt-çiftlerini
    ikiye ayırır:

    full_pairs: HER İKİ bacağın da modelde (ARR_INSTANCES/DEP_INSTANCES)
      bulunduğu ortak günler -- list of (ob_flno, ib_flno, gun, station).

    partial_pairs: yalnızca BİR bacağın modelde olduğu, DİĞER bacağın
      `out_of_scope_baselines`'ta (ham TK baseline, model değişkeni DEĞİL --
      bkz. src.model.constraints_capacity.compute_out_of_scope_baselines)
      bulunduğu günler -- list of (ob_flno, ib_flno, gun, station,
      fixed_side, fixed_baseline_min). VARSAYIM (ASSUMPTIONS.md, F ile
      birlikte): kapsam-dışı ortağın kendi baseline'ında SABİT çalıştığı
      varsayılır (modelin onu hareket ettirecek bir kolu yok, hiç candidate
      bacağı olarak üretilmedi) -- rotasyon fiziksel kuralı yine de o SABİT
      zamana karşı in-scope bacağa uygulanır.

    Her iki bacağı da kapsam dışı olan (full_pairs'e de partial_pairs'e de
    girmeyen) çiftler zaten modelin karar değişkeni kapsamı tamamen dışında
    -- kısıt kurulacak bir şey yok, sessizce atlanır."""
    if out_of_scope_baselines is None:
        out_of_scope_baselines = {}

    ob_guns = {}
    ib_guns = {}
    for (role, flno, gun) in model.DEP_INSTANCES:
        if role == "OB":
            ob_guns.setdefault(flno, set()).add(gun)
    for (role, flno, gun) in model.ARR_INSTANCES:
        if role == "IB":
            ib_guns.setdefault(flno, set()).add(gun)

    full_pairs = []
    partial_pairs = []
    for _, group in pairs_df.groupby("pair"):
        rows = group.to_dict("records")
        for i in range(len(rows) - 1):
            leg1, leg2 = rows[i], rows[i + 1]
            if leg1["orig"] != "IST" or leg2["dest"] != "IST" or leg1["dest"] != leg2["orig"]:
                continue
            station = leg1["dest"]
            ob_flno, ib_flno = leg1["flno"], leg2["flno"]
            ob_gun_set = ob_guns.get(ob_flno, set())
            ib_gun_set = ib_guns.get(ib_flno, set())

            for gun in ob_gun_set & ib_gun_set:
                full_pairs.append((ob_flno, ib_flno, gun, station))

            for gun in ob_gun_set - ib_gun_set:
                baseline_key = ("IB", ib_flno, gun)
                if baseline_key in out_of_scope_baselines:
                    partial_pairs.append(
                        (ob_flno, ib_flno, gun, station, "IB_fixed", out_of_scope_baselines[baseline_key])
                    )

            for gun in ib_gun_set - ob_gun_set:
                baseline_key = ("OB", ob_flno, gun)
                if baseline_key in out_of_scope_baselines:
                    partial_pairs.append(
                        (ob_flno, ib_flno, gun, station, "OB_fixed", out_of_scope_baselines[baseline_key])
                    )
    return full_pairs, partial_pairs


def _flight_cut_points(candidates):
    """(role,flno) -> "gün sınırı" saat-of-day dakikası, gerçek gece yarısı
    (00:00) DEĞİL -- o uçağın KENDİ baseline saat-of-day'inin TAM 12 SAAT
    KARŞISI ((tod+720) mod 1440). Bkz. _day_offsets docstring: neden gerçek
    gece yarısı güvenli bir çapa DEĞİL."""
    cuts = {}
    for c in candidates:
        for role, flno, ts in (("IB", c.flno1, c.arr_time), ("OB", c.flno2, c.dep_time)):
            key = (role, flno)
            if key in cuts:
                continue
            tod = int((ts - ts.normalize()).total_seconds() // 60)
            cuts[key] = (tod + 720) % 1440
    return cuts


def _day_offsets(candidates, epoch_anchor):
    """(role,flno,gun) -> epoch-minute of THAT INSTANCE'S OWN "gün sınırı"
    (bkz. _flight_cut_points -- gerçek gece yarısı DEĞİL, o uçuşun kendi
    baseline saatinin 12 saat karşısı), relative to the shared global
    epoch_anchor.

    Kritik düzeltme #1 (M3, ilk solve denemesinde infeasibility olarak
    yakalanan bug): epoch_anchor TÜM veri kümesi için TEK bir GLOBAL referans
    (compute_epoch_anchor, plan §Context) -- Gün=2'nin zamanları Gün=1'inkinden
    ~1440dk daha BÜYÜK epoch-değerlere sahip (farklı takvim günü). G'nin
    "spread" kontrolü bu HAM epoch değerlerini doğrudan karşılaştırırsa, aynı
    saat-of-day'e sahip iki gün bile ~1440dk'lık SAHTE bir farkla karşılaşır
    (X_dev=15 ile ASLA uzlaştırılamaz -> infeasible). Çözüm: her
    (role,flno,gun)'u KENDİ takvim gününün bir referans noktasına göre
    normalize et (day_offset çıkar).

    Kritik düzeltme #2 (M4, "G check" -- gece yarısı SARMASI): #1'in ilk
    çözümü referans noktası olarak GERÇEK gece yarısını (00:00) kullanıyordu.
    Bu, KENDİ saati gerçek gece yarısına YAKIN olan bir uçuş için YANLIŞ:
    Pazartesi 23:55 (gün-içi=1435) ile Salı 00:05 (gün-içi=5) arasındaki
    GERÇEK fark yalnızca 10 dakikadır, ama gece-yarısı-çapalı [0,1440)
    gün-içi temsilinde bu iki değer ARALIĞIN İKİ UCUNA düşer -- |1435-5|=1430,
    SAHTE bir ~1430dk'lık "ihlal" (X_dev ile ASLA uzlaştırılamaz ->
    infeasible, GERÇEKTE uyumlu bir tarife bile). Çözüm: referans noktasını
    gerçek gece yarısından, o uçuşun KENDİ baseline saatinin TAM 12 SAAT
    KARŞISINA kaydır (_flight_cut_points) -- uçuşun gerçekçi ayarlanabilir
    aralığı (Big-M disiplini gereği hiçbir zaman +-720dk'yı aşamaz) bu yeni
    sınırdan ASLA taşamaz, sarma sorunu o uçuş için yapısal olarak imkansız
    hale gelir. Denklik kanıtı (elle doğrulandı): iki nokta arası GERÇEK
    dakika farkı, hangi referans noktası (00:00 veya cut) seçilirse seçilsin
    AYNI kalır -- TEK ŞART, referansın uçuşun gerçek zaman kümesinin
    ORTASINDAN değil, dışından geçmesi (cut bunu HER ZAMAN garanti eder,
    00:00 garanti etmez)."""
    cuts = _flight_cut_points(candidates)
    offsets = {}
    for c in candidates:
        for role, flno, ts in (("IB", c.flno1, c.arr_time), ("OB", c.flno2, c.dep_time)):
            key = (role, flno, c.gun)
            if key in offsets:
                continue
            cut = cuts[(role, flno)]
            day_midnight = int((ts.normalize() - epoch_anchor).total_seconds() // 60)
            tod = int((ts - ts.normalize()).total_seconds() // 60)
            offsets[key] = day_midnight + cut if tod >= cut else day_midnight + cut - 1440
    return offsets


def _baseline_tod(candidates):
    """(role,flno,gun) -> baseline saat-of-day dakikası [0,1440) -- cluster_flight_days'e
    girdi (bkz. src.model.day_clustering)."""
    tods = {}
    for c in candidates:
        for role, flno, ts in (("IB", c.flno1, c.arr_time), ("OB", c.flno2, c.dep_time)):
            key = (role, flno, c.gun)
            if key in tods:
                continue
            tods[key] = int((ts - ts.normalize()).total_seconds() // 60)
    return tods


def add_g_constraints(model, candidates, epoch_anchor, x_dev: int):
    """Referans-zaman formülasyonu (doğruluk argümanı: tests/solve/test_m3_constraints_g.py):
    serbest T[role,flno,cluster], her gün (t-day_offset) in [T, T+x_dev] --
    max-min<=x_dev ile TAM eşdeğer (gün-içi saat-of-day üzerinden, bkz.
    _day_offsets), O(H) kısıt (H=gün sayısı), naif O(H^2) çift-karşılaştırmadan
    daha sıkı. Yalnızca 2+ farklı günde modelde bulunan (role,flno) çiftleri
    için kurulur.

    M5 VARSAYIM-9 (ASSUMPTIONS.md, bkz. src.model.day_clustering docstring):
    gerçek veride EN AZ BİR uçuş numarası (TK2841) TÜM günlerini TEK bir
    X_dev-bandına sığdıramıyor (baseline'ın kendisi zaten uzlaştırılamaz --
    645dk > 2*180+15=375dk). KOŞULSUZ (tüm günler tek grup) okuma TÜM modeli
    infeasible yapardı. Çözüm: her (role,flno)'nun günlerini EN AZ sayıda
    UZLAŞTIRILABİLİR kümeye ayır (`cluster_flight_days`) -- G yalnızca KÜME
    İÇİNDE uygulanır, kümeler ARASI hiç kısıt YOK. Tüm günler zaten
    uzlaştırılabilirse (yaygın durum) TEK küme oluşur = M3 davranışı
    DEĞİŞMEDEN korunur."""
    day_offset = _day_offsets(candidates, epoch_anchor)
    baseline_tod = _baseline_tod(candidates)

    role_flno_guns = {}
    for (role, flno, gun) in model.ARR_INSTANCES:
        if role == "IB":
            role_flno_guns.setdefault(("IB", flno), set()).add(gun)
    for (role, flno, gun) in model.DEP_INSTANCES:
        if role == "OB":
            role_flno_guns.setdefault(("OB", flno), set()).add(gun)

    multi_day = {k: sorted(guns) for k, guns in role_flno_guns.items() if len(guns) >= 2}

    cluster_of_gun = {}
    g_flights_index = []
    for (role, flno), guns in multi_day.items():
        var = model.t_arr if role == "IB" else model.t_dep
        occurrences = []
        for gun in guns:
            lb, ub = var[role, flno, gun].lb, var[role, flno, gun].ub
            half_width = (ub - lb) // 2
            occurrences.append((gun, baseline_tod[role, flno, gun], half_width))
        clusters = cluster_flight_days(occurrences, x_dev)
        for cluster in clusters:
            cluster_key = min(cluster)
            for gun in cluster:
                cluster_of_gun[role, flno, gun] = cluster_key
            if len(cluster) >= 2:
                g_flights_index.append((role, flno, cluster_key))

    model.G_FLIGHTS = pyo.Set(initialize=g_flights_index, dimen=3, ordered=True)
    if not g_flights_index:
        return multi_day

    def cluster_guns(role, flno, cluster_key):
        return [g for g in multi_day[(role, flno)] if cluster_of_gun[role, flno, g] == cluster_key]

    def t_bounds_rule(m, role, flno, cluster_key):
        guns = cluster_guns(role, flno, cluster_key)
        var = m.t_arr if role == "IB" else m.t_dep
        offs = [day_offset[(role, flno, g)] for g in guns]
        los = [var[role, flno, g].lb - off for g, off in zip(guns, offs)]
        his = [var[role, flno, g].ub - off for g, off in zip(guns, offs)]
        return (min(los), max(his))
    model.T_ref = pyo.Var(model.G_FLIGHTS, domain=pyo.Integers, bounds=t_bounds_rule)

    day_index = [
        (role, flno, cluster_key, gun)
        for (role, flno, cluster_key) in g_flights_index
        for gun in cluster_guns(role, flno, cluster_key)
    ]
    model.G_FLIGHT_DAYS = pyo.Set(initialize=day_index, dimen=4, ordered=True)

    def lower_rule(m, role, flno, cluster_key, gun):
        t = m.t_arr[role, flno, gun] if role == "IB" else m.t_dep[role, flno, gun]
        return t - day_offset[(role, flno, gun)] >= m.T_ref[role, flno, cluster_key]
    model.g_lower = pyo.Constraint(model.G_FLIGHT_DAYS, rule=lower_rule)

    def upper_rule(m, role, flno, cluster_key, gun):
        t = m.t_arr[role, flno, gun] if role == "IB" else m.t_dep[role, flno, gun]
        return t - day_offset[(role, flno, gun)] <= m.T_ref[role, flno, cluster_key] + x_dev
    model.g_upper = pyo.Constraint(model.G_FLIGHT_DAYS, rule=upper_rule)

    return multi_day


def add_a_constraints(model, candidates, pairs_df, r_o_lookup: dict, tau: int, out_of_scope_baselines: dict = None):
    full_pairs, partial_pairs = build_rotation_pairs(model, pairs_df, out_of_scope_baselines)

    # VARSAYIM ("rotasyon verisi olmayan istasyon icin A atlanir", ASSUMPTIONS.md):
    # r_o_lookup only covers stations where get_rotation_constant succeeded
    # (main.py already skips the rest at population time) -- this exemption
    # must ALSO apply here, at constraint-build time, or a station present
    # in pairs_df but absent from r_o_lookup crashes with a raw KeyError
    # (found on real full data) instead of being silently exempted.
    full_pairs = [(ob, ib, gun, station) for (ob, ib, gun, station) in full_pairs if station in r_o_lookup]
    partial_pairs = [
        (ob, ib, gun, station, fixed_side, baseline)
        for (ob, ib, gun, station, fixed_side, baseline) in partial_pairs if station in r_o_lookup
    ]

    index = [(ob, ib, gun) for (ob, ib, gun, station) in full_pairs]
    station_by_pair = {(ob, ib, gun): station for (ob, ib, gun, station) in full_pairs}

    model.ROTATION_PAIRS = pyo.Set(initialize=index, dimen=3, ordered=True)

    def rotation_rule(m, ob_flno, ib_flno, gun):
        station = station_by_pair[ob_flno, ib_flno, gun]
        r_o = r_o_lookup[station]
        return m.t_arr["IB", ib_flno, gun] >= m.t_dep["OB", ob_flno, gun] + r_o + tau
    model.a_rotation = pyo.Constraint(model.ROTATION_PAIRS, rule=rotation_rule)

    partial_index = [(ob, ib, gun) for (ob, ib, gun, station, fixed_side, baseline) in partial_pairs]
    partial_info = {
        (ob, ib, gun): (station, fixed_side, baseline)
        for (ob, ib, gun, station, fixed_side, baseline) in partial_pairs
    }
    model.ROTATION_PARTIAL_PAIRS = pyo.Set(initialize=partial_index, dimen=3, ordered=True)

    def partial_rotation_rule(m, ob_flno, ib_flno, gun):
        station, fixed_side, baseline = partial_info[ob_flno, ib_flno, gun]
        r_o = r_o_lookup[station]
        if fixed_side == "IB_fixed":
            # Dönüş bacağı (IB) kapsam dışı, kendi baseline'ında SABİT --
            # gidiş (OB, model değişkeni) o sabit varıştan en az R_o+tau
            # ÖNCE kalkmış olmalı (rotasyon eşitsizliğinin tersine çevrilmiş
            # hali: arr>=dep+R_o+tau -> dep<=arr_fixed-R_o-tau).
            return m.t_dep["OB", ob_flno, gun] <= baseline - r_o - tau
        # OB_fixed: gidiş bacağı kapsam dışı, kendi baseline'ında SABİT --
        # dönüş (IB, model değişkeni) o sabit kalkıştan en az R_o+tau SONRA
        # varmış olmalı.
        return m.t_arr["IB", ib_flno, gun] >= baseline + r_o + tau
    model.a_rotation_partial = pyo.Constraint(model.ROTATION_PARTIAL_PAIRS, rule=partial_rotation_rule)

    return full_pairs, partial_pairs
