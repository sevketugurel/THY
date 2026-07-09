"""Independent feasibility validator -- deliberately does not import src.model.*
or src.candidates.*. Re-derives gap validity, legal-window membership, and
beaten-rival/rank claims from raw data + the OUTPUT's own reported values,
never trusting a value the solver already computed internally (disqualification
insurance, plan §1/§5). Some logic (epoch anchor, window bounds) is
intentionally duplicated from src.candidates.generate rather than imported --
a shared bug there must not be able to silently pass validation too.

D-checking reuses src.data.block_times / src.data.competitors (the DATA layer,
not src.model.*/src.candidates.*) to recompute journey times and rival best
times -- this is a disclosed, narrower sharing than "zero shared code": a bug
in the block-time/rival DERIVATION itself could still slip through both the
model and the validator, but the DECISION LOGIC (which candidates get
selected, which beats get claimed) is independently re-verified.

M1: B-style gap-window check validated against the OUTPUT's own reported
adjusted times, plus a legal-window check per adjustable flight instance.
M2: beaten_rivals/rank claims re-derived and cross-checked. A/E/F/G land
alongside their constraint groups in M3-M4.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od


@dataclass
class ValidationResult:
    is_valid: bool
    violations: list = field(default_factory=list)


def _epoch_anchor(tk):
    return min(tk["arr_time"].min(), tk["dep_time"].min()).normalize()


def _epoch_min(ts, anchor):
    return int((ts - anchor).total_seconds() // 60)


def _baseline_bounds(tk, role, flno, gun, anchor, adjustable_window_min, adjustable_set):
    if role == "IB":
        match = tk[(tk.flno1 == flno) & (tk.gun == gun)]
        baseline_col = "arr_time"
    else:
        match = tk[(tk.flno2 == flno) & (tk.gun == gun)]
        baseline_col = "dep_time"
    if match.empty:
        return None
    baseline = _epoch_min(match.iloc[0][baseline_col], anchor)
    if adjustable_set == "all":
        return baseline - adjustable_window_min, baseline + adjustable_window_min
    return baseline, baseline


def _cluster_flight_days_independent(occurrences, x_dev):
    """Bağımsız yeniden-uygulama (src.model.day_clustering.cluster_flight_days
    ile BİREBİR aynı algoritma, kasıtlı olarak KOPYALANMIŞ -- diskalifiye
    sigortası, oradaki bir bug validasyonu da sessizce geçemesin). M5
    VARSAYIM-9 (ASSUMPTIONS.md): dairesel en-büyük-boşluktan kes, sonra
    soldan-sağa açgözlü ÇAP taraması (küme BAŞLANGICINA göre, ardışık öğeye
    göre DEĞİL -- bkz. tests/unit/test_day_clustering.py 0-300-600 zinciri).
    occurrences: (key, baseline_tod_min, half_width_min) üçlüleri."""
    if len(occurrences) <= 1:
        return [[key for key, _, _ in occurrences]]
    sorted_occ = sorted(occurrences, key=lambda o: o[1])
    n = len(sorted_occ)
    gaps = []
    for i in range(n):
        cur_tod = sorted_occ[i][1]
        nxt_tod = sorted_occ[(i + 1) % n][1]
        gap = (nxt_tod + 1440 - cur_tod) if i == n - 1 else (nxt_tod - cur_tod)
        gaps.append(gap)
    cut_after = max(range(n), key=lambda i: gaps[i])
    linear = list(sorted_occ[cut_after + 1:]) + [
        (key, tod + 1440, hw) for (key, tod, hw) in sorted_occ[:cut_after + 1]
    ]
    clusters = []
    current = [linear[0]]
    start_tod, start_hw = linear[0][1], linear[0][2]
    for occ in linear[1:]:
        key, tod, hw = occ
        if tod - start_tod <= start_hw + hw + x_dev:
            current.append(occ)
        else:
            clusters.append(current)
            current = [occ]
            start_tod, start_hw = tod, hw
    clusters.append(current)
    return [[o[0] for o in cluster] for cluster in clusters]


def _rotation_subpairs(pairs_df):
    """Same logic as src.model.constraints_operations.build_rotation_pairs
    but working purely from the raw Flight Pairs table (no model.* access) --
    consecutive (Orig==IST -> OB, Dest==IST -> IB) sub-pairs within each Pair
    group. Legs not touching IST (e.g. an intermediate MEX->CUN leg in a
    IST->MEX->CUN->IST group) are outside our variable scope and skipped."""
    subpairs = []
    for _, group in pairs_df.groupby("pair"):
        rows = group.to_dict("records")
        for i in range(len(rows) - 1):
            leg1, leg2 = rows[i], rows[i + 1]
            if leg1["orig"] != "IST" or leg2["dest"] != "IST" or leg1["dest"] != leg2["orig"]:
                continue
            subpairs.append((leg1["flno"], leg2["flno"], leg1["dest"]))
    return subpairs


def validate_output(
    output_path: Path, od_table_path: Path, L: int, U: int,
    adjustable_window_min: int = 0, adjustable_set: str = "none",
    flight_pairs_path: Path = None, tau: int = None, x_dev: int = None,
    alpha: float = None, gamma: int = None,
    bucket_size_min: int = None, capacity_departure: int = None, capacity_arrival: int = None,
) -> ValidationResult:
    data = json.loads(Path(output_path).read_text())
    od_table = load_od_table(od_table_path)
    tk = od_table[od_table.cr1 == "TK"]
    anchor = _epoch_anchor(tk)

    violations = []

    reported_times = {}
    for entry in data.get("adjusted_flight_times", []):
        key = (entry["role"], entry["flno"], entry["gun"])
        reported_times[key] = entry["time_min"]

        bounds = _baseline_bounds(tk, entry["role"], entry["flno"], entry["gun"],
                                   anchor, adjustable_window_min, adjustable_set)
        if bounds is None:
            violations.append(
                f"adjusted_flight_times entry role={entry['role']} FlNo={entry['flno']} "
                f"Gün={entry['gun']}: not found in raw O&D table"
            )
            continue
        lo, hi = bounds
        if not (lo <= entry["time_min"] <= hi):
            violations.append(
                f"adjusted_flight_times entry role={entry['role']} FlNo={entry['flno']} "
                f"Gün={entry['gun']}: reported time {entry['time_min']} outside legal window [{lo},{hi}]"
            )

    for conn in data["selected_connections"]:
        o, d = conn["od"].split("-")
        # Candidates are a full inbound x outbound cross-product (plan §4) --
        # a pairing never explicitly listed together as one raw row can still
        # be a legitimate candidate. Each leg must exist independently as a
        # real TK flight instance on this day (in the correct role/station),
        # not that the exact (flno1,flno2) pairing was pre-enumerated.
        inbound_exists = not tk[(tk.dep1 == o) & (tk.flno1 == conn["flno1"]) & (tk.gun == conn["gun"])].empty
        outbound_exists = not tk[(tk.arr2 == d) & (tk.flno2 == conn["flno2"]) & (tk.gun == conn["gun"])].empty
        if not (inbound_exists and outbound_exists):
            violations.append(
                f"connection {conn['od']} FlNo1={conn['flno1']} FlNo2={conn['flno2']} "
                f"Gün={conn['gun']}: not found in raw O&D table"
            )
            continue

        arr_key = ("IB", conn["flno1"], conn["gun"])
        dep_key = ("OB", conn["flno2"], conn["gun"])
        if arr_key not in reported_times or dep_key not in reported_times:
            violations.append(
                f"connection {conn['od']} FlNo1={conn['flno1']} FlNo2={conn['flno2']} "
                f"Gün={conn['gun']}: missing adjusted_flight_times entry for its legs"
            )
            continue

        actual_gap = reported_times[dep_key] - reported_times[arr_key]
        if not (L <= actual_gap <= U):
            violations.append(
                f"connection {conn['od']} FlNo1={conn['flno1']} FlNo2={conn['flno2']} "
                f"Gün={conn['gun']}: gap={actual_gap}min outside [{L},{U}]"
            )

    if alpha is not None:
        counts = {}
        for conn in data["selected_connections"]:
            o, d = conn["od"].split("-")
            counts[(o, d, conn["gun"])] = counts.get((o, d, conn["gun"]), 0) + 1
        checked = set()
        for (o, d, gun) in list(counts.keys()):
            if (o, d, gun) in checked or (d, o, gun) not in counts:
                continue
            checked.add((o, d, gun))
            checked.add((d, o, gun))
            n_fwd, n_bwd = counts[(o, d, gun)], counts[(d, o, gun)]
            if abs(n_fwd - n_bwd) > alpha * (n_fwd + n_bwd):
                violations.append(
                    f"E1 {o}-{d} Gün={gun}: |n_fwd({n_fwd})-n_bwd({n_bwd})| "
                    f"exceeds alpha({alpha})*(n_fwd+n_bwd)"
                )

    if gamma is not None:
        # Bağımsız Jbest: model.py'nin argmin-sandviç MIP mekanizmasına hiç
        # gerek yok -- validator saf Python'da min() alabilir (solver'ın
        # aksine, burada "hangi candidate seçilecek" diye bir karar değil,
        # zaten SEÇİLMİŞ (offered) bağlantıların arasından minimum bulmak
        # yeterli). E2 check bilerek ranking_results/provider'dan bağımsız,
        # kendi BlockTimeProvider'ını kurar.
        provider_e2 = BlockTimeProvider(tk, L=L, U=U)
        journeys_by_market = {}
        for conn in data["selected_connections"]:
            o, d = conn["od"].split("-")
            arr_key = ("IB", conn["flno1"], conn["gun"])
            dep_key = ("OB", conn["flno2"], conn["gun"])
            if arr_key not in reported_times or dep_key not in reported_times:
                continue
            gap = reported_times[dep_key] - reported_times[arr_key]
            try:
                journey = provider_e2.get_journey_constant(o, d) + gap
            except KeyError:
                continue
            journeys_by_market.setdefault((o, d, conn["gun"]), []).append(journey)

        checked_e2 = set()
        for (o, d, gun) in list(journeys_by_market.keys()):
            if (o, d, gun) in checked_e2 or (d, o, gun) not in journeys_by_market:
                continue
            checked_e2.add((o, d, gun))
            checked_e2.add((d, o, gun))
            jbest_fwd = min(journeys_by_market[(o, d, gun)])
            jbest_bwd = min(journeys_by_market[(d, o, gun)])
            if abs(jbest_fwd - jbest_bwd) > gamma:
                violations.append(
                    f"E2 {o}-{d} Gün={gun}: |Jbest_fwd({jbest_fwd})-Jbest_bwd({jbest_bwd})| "
                    f"exceeds Gamma({gamma})"
                )

    if bucket_size_min is not None:
        # F: bağımsız kova-doluluk kontrolü. src.model.constraints_capacity'nin
        # MIP z-binary mekanizmasına gerek yok -- validator sadece reported_times'ın
        # KENDİ 10dk kovasını (t//bucket_size_min) sayar. Kapsam-dışı (modelin
        # hiç değişkeni olmayan, yani reported_times'ta OLMAYAN) TK bacakları
        # kendi ham baseline zamanlarında SABİT işgal ettikleri kabul edilir
        # (VARSAYIM, src.model.constraints_capacity.compute_residual_capacity
        # ile BİREBİR aynı mantık -- model tarafıyla tutarlı olmak ZORUNLU).
        dep_occupancy = {}
        arr_occupancy = {}
        seen_out_of_scope = set()
        for row in tk.itertuples():
            arr_key = ("IB", int(row.flno1), int(row.gun))
            if arr_key not in reported_times and arr_key not in seen_out_of_scope:
                seen_out_of_scope.add(arr_key)
                b = _epoch_min(row.arr_time, anchor) // bucket_size_min
                arr_occupancy[b] = arr_occupancy.get(b, 0) + 1
            dep_key = ("OB", int(row.flno2), int(row.gun))
            if dep_key not in reported_times and dep_key not in seen_out_of_scope:
                seen_out_of_scope.add(dep_key)
                b = _epoch_min(row.dep_time, anchor) // bucket_size_min
                dep_occupancy[b] = dep_occupancy.get(b, 0) + 1

        dep_counts = {}
        arr_counts = {}
        for (role, flno, gun), t in reported_times.items():
            b = t // bucket_size_min
            if role == "OB":
                dep_counts[b] = dep_counts.get(b, 0) + 1
            else:
                arr_counts[b] = arr_counts.get(b, 0) + 1

        for b, count in dep_counts.items():
            cap = max(0, capacity_departure - dep_occupancy.get(b, 0))
            if count > cap:
                violations.append(
                    f"F kova(departure) bucket={b}: {count} uçuş, kalan kapasite {cap} "
                    f"(taban={capacity_departure}, kapsam-dışı işgal={dep_occupancy.get(b, 0)})"
                )
        for b, count in arr_counts.items():
            cap = max(0, capacity_arrival - arr_occupancy.get(b, 0))
            if count > cap:
                violations.append(
                    f"F kova(arrival) bucket={b}: {count} uçuş, kalan kapasite {cap} "
                    f"(taban={capacity_arrival}, kapsam-dışı işgal={arr_occupancy.get(b, 0)})"
                )

    if x_dev is not None:
        # Kritik #1: reported_times ayni GLOBAL epoch_anchor'da (compute_epoch_anchor,
        # candidates/generate.py ile ayni sozlesme) -- farkli gun'ler ~1440dk
        # farkli epoch degerlerine sahip (farkli takvim gunu). Ham degerleri
        # dogrudan karsilastirmak, ayni saat-of-day'e sahip GECERLI bir cozumu
        # bile ~1440dk'lik SAHTE bir ihlal olarak bayraklardi -- her (role,flno,gun)
        # KENDI takvim gununun bir referans noktasina gore normalize edilir once.
        #
        # Kritik #2 (gece yarisi sarmasi -- "G check"): referans noktasi olarak
        # GERCEK gece yarisi (00:00) kullanmak, KENDI saati gece yarisina YAKIN
        # olan bir ucus icin YANLIS -- 23:55 (gun-ici=1435) ile 00:05 (gun-ici=5)
        # arasindaki GERCEK fark 10dk'dir ama gece-yarisi-capali temsilde
        # |1435-5|=1430, SAHTE bir ihlal. Referans noktasi bunun yerine o
        # ucusun KENDI baseline saatinin TAM 12 SAAT KARSISINA kaydirilir
        # (constraints_operations.py::_day_offsets / _flight_cut_points ile
        # BIREBIR ayni mantik, model tarafiyla tutarli olmasi ZORUNLU).
        baseline_ts = {}
        for (role, flno, gun) in reported_times:
            match = tk[(tk.flno1 == flno) & (tk.gun == gun)] if role == "IB" else tk[(tk.flno2 == flno) & (tk.gun == gun)]
            if match.empty:
                continue
            ref_col = "arr_time" if role == "IB" else "dep_time"
            baseline_ts[(role, flno, gun)] = match.iloc[0][ref_col]

        cuts = {}
        for (role, flno, gun), ts in baseline_ts.items():
            key = (role, flno)
            if key in cuts:
                continue
            tod = _epoch_min(ts, ts.normalize())
            cuts[key] = (tod + 720) % 1440

        by_role_flno = {}
        for (role, flno, gun), t in reported_times.items():
            if (role, flno, gun) not in baseline_ts:
                continue
            ts = baseline_ts[(role, flno, gun)]
            cut = cuts[(role, flno)]
            day_midnight = _epoch_min(ts.normalize(), anchor)
            tod = _epoch_min(ts, ts.normalize())
            day_offset = day_midnight + cut if tod >= cut else day_midnight + cut - 1440
            by_role_flno.setdefault((role, flno), {})[gun] = t - day_offset

        # M5 VARSAYIM-9 (ASSUMPTIONS.md, bkz. src.model.day_clustering docstring):
        # gerçek veride EN AZ BİR uçuş numarası (TK2841) TÜM günlerini TEK bir
        # X_dev bandına sığdıramıyor (baseline'ın kendisi uzlaştırılamaz).
        # Validator, modelin AYNI kümeleme kararını (baseline+pencere+X_dev'den,
        # RAPORLANAN zamanlardan DEĞİL) bağımsız olarak yeniden hesaplar --
        # yalnızca AYNI kümenin İÇİNDEKİ raporlanan zamanlar X_dev'e tabi;
        # kümeler ARASI karşılaştırma yapılmaz (model tarafıyla tutarlı olmak
        # ZORUNLU, aksi halde geçerli bir çözüm yanlışlıkla reddedilir YA DA
        # gerçek bir küme-içi ihlal kaçırılır).
        for (role, flno), by_gun in by_role_flno.items():
            if len(by_gun) < 2:
                continue
            occurrences = []
            for gun in by_gun:
                ts = baseline_ts[(role, flno, gun)]
                tod = _epoch_min(ts, ts.normalize())
                half_width = adjustable_window_min if adjustable_set == "all" else 0
                occurrences.append((gun, tod, half_width))
            for cluster in _cluster_flight_days_independent(occurrences, x_dev):
                if len(cluster) < 2:
                    continue
                cluster_values = {g: by_gun[g] for g in cluster}
                spread = max(cluster_values.values()) - min(cluster_values.values())
                if spread > x_dev:
                    violations.append(
                        f"regularity (x_dev) role={role} FlNo={flno} küme={sorted(cluster)}: "
                        f"gün-içi spread={spread}min exceeds X_dev={x_dev} "
                        f"(day-normalized times={cluster_values})"
                    )

    if flight_pairs_path is not None:
        pairs_df = load_flight_pairs(flight_pairs_path)
        provider_a = BlockTimeProvider(tk, L=L, U=U)
        for ob_flno, ib_flno, station in _rotation_subpairs(pairs_df):
            try:
                r_o = provider_a.get_rotation_constant(station)
            except KeyError:
                continue
            for gun in set(g for (_, f, g) in reported_times if f == ob_flno) | \
                       set(g for (_, f, g) in reported_times if f == ib_flno):
                dep_key = ("OB", ob_flno, gun)
                arr_key = ("IB", ib_flno, gun)
                if dep_key not in reported_times or arr_key not in reported_times:
                    continue
                min_arr = reported_times[dep_key] + r_o + tau
                if reported_times[arr_key] < min_arr:
                    violations.append(
                        f"rotation FlNo(OB)={ob_flno} FlNo(IB)={ib_flno} Gün={gun}: "
                        f"IST arrival {reported_times[arr_key]} < required minimum "
                        f"{min_arr} (dep {reported_times[dep_key]} + R_o({station})={r_o} + tau={tau})"
                    )

    ranking_results = data.get("ranking_results", [])
    if ranking_results:
        provider = BlockTimeProvider(tk, L=L, U=U)
        offered_by_market = {}
        for conn in data["selected_connections"]:
            o, d = conn["od"].split("-")
            arr_key = ("IB", conn["flno1"], conn["gun"])
            dep_key = ("OB", conn["flno2"], conn["gun"])
            if arr_key not in reported_times or dep_key not in reported_times:
                continue
            gap = reported_times[dep_key] - reported_times[arr_key]
            try:
                journey = provider.get_journey_constant(o, d) + gap
            except KeyError:
                continue
            offered_by_market.setdefault((o, d, conn["gun"]), []).append(journey)

        for entry in ranking_results:
            market = (entry["o"], entry["d"], entry["gun"])
            rivals = derive_rival_best_times(od_table, entry["o"], entry["d"], entry["gun"])
            journeys = offered_by_market.get(market, [])
            actual_beaten = {k for k, t_comp in rivals.items() if any(j <= t_comp for j in journeys)}
            claimed_beaten = set(entry["beaten_rivals"])

            for k in claimed_beaten - actual_beaten:
                violations.append(
                    f"ranking_results {entry['o']}-{entry['d']} Gün={entry['gun']}: "
                    f"claims rival {k} beaten but no offered connection actually beats it"
                )
            # NOTE: actual_beaten - claimed_beaten (under-claiming) is deliberately
            # NOT flagged as a violation. D's beat reification is forward-only when
            # W(r) is monotonic (docs/model.md §5 D) -- this makes claimed_beaten
            # a PROVABLE SUBSET of actual_beaten (over-claiming is structurally
            # impossible, per the check above), so the reported reward can only be
            # an equal-or-lower bound on the true achievable reward, never inflated.
            # Under-claiming happens legitimately when W has a flat (tied) segment
            # (e.g. beating N-1 vs N rivals both land on r=1 -- see
            # tests/fixtures/README.md "M2 eki"); it costs nothing structurally and
            # is not a disqualifying inconsistency, only a missed reporting detail.

            # Clamped at 1 (never 0): the real change_ranking_input.xlsx table
            # never defines a reward for r=0 (min observed r is always 1 --
            # confirmed by inspection); beating ALL rivals lands on the same
            # r=1 "best available" tier as beating all-but-one. Must match
            # src/model/constraints_competition.py::add_rank_onehot's clamp
            # exactly, or a correctly-full beaten_rivals list would be
            # wrongly flagged here.
            expected_rank = max(1, len(rivals) - len(claimed_beaten)) if rivals else 0
            if entry["rank"] != expected_rank:
                violations.append(
                    f"ranking_results {entry['o']}-{entry['d']} Gün={entry['gun']}: "
                    f"claimed rank={entry['rank']} inconsistent with max(1,N({len(rivals)})"
                    f"-beaten({len(claimed_beaten)}))={expected_rank}"
                )

    return ValidationResult(is_valid=not violations, violations=violations)


def recompute_objective(
    output_path: Path, od_table_path: Path, yolcu_path: Path, ranking_path: Path,
    L: int, U: int, breakdown_path: Path = None,
):
    """Doğruluk borcu: CLI'ın raporladığı objective_value'yu, output.json'un
    selected_connections + adjusted_flight_times alanlarından ve HAM veriden
    (src.model/src.candidates'a hiç dokunmadan) tamamen BAĞIMSIZ olarak
    yeniden hesaplar -- ranking_results'ın CLAIM ettiği rank'e bile güvenmez,
    beaten/rank'i kendi taze hesaplar (validate_output'un D-check'iyle aynı
    mantık, ama TAMAMEN ayrı bir giriş noktasından, ranking_results
    olmadan da çalışır).

    b_od per-(o,d) pazar sabiti main.py'nin KENDİ davranışıyla TUTARLI
    hesaplanır: main.py candidates'ı gün-sıralı üretir ve b_od'yi İLK
    karşılaşılan gün için hesaplar (bkz. main.py rival_data/b_od_data döngüsü)
    -- burada da aynı tutarlılık için EN KÜÇÜK gun değeri kullanılır."""
    data = json.loads(Path(output_path).read_text())
    od_table = load_od_table(od_table_path)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(yolcu_path)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking(ranking_path)
    weight_lookup = {(row.n, row.b, row.r): row.weight for row in ranking_table.itertuples()}
    provider = BlockTimeProvider(tk, L=L, U=U)

    reported_times = {
        (e["role"], e["flno"], e["gun"]): e["time_min"]
        for e in data.get("adjusted_flight_times", [])
    }

    gaps_by_market = {}
    for conn in data["selected_connections"]:
        o, d = conn["od"].split("-")
        arr_key = ("IB", conn["flno1"], conn["gun"])
        dep_key = ("OB", conn["flno2"], conn["gun"])
        gap = reported_times[dep_key] - reported_times[arr_key]
        gaps_by_market.setdefault((o, d, conn["gun"]), []).append(gap)

    b_od_cache = {}

    def b_od_for(o, d):
        if (o, d) not in b_od_cache:
            gun0 = min(gun for (mo, md, gun) in gaps_by_market if (mo, md) == (o, d))
            baseline_j = compute_baseline_best_journey(od_table, o, d, gun0, L=L, U=U)
            b_od_cache[(o, d)] = derive_b_od(od_table, o, d, gun0, baseline_j) if baseline_j is not None else 0
        return b_od_cache[(o, d)]

    connection_reward = 0.0
    ranking_reward = 0.0
    breakdown = {"markets": []}

    for (o, d, gun), gaps in sorted(gaps_by_market.items()):
        r = rho.get((o, d))
        if r is None:
            continue
        count = len(gaps)
        conn_component = r * sum(2 ** -(j - 1) for j in range(1, count + 1))
        connection_reward += conn_component

        rivals = derive_rival_best_times(od_table, o, d, gun)
        rank_component = 0.0
        rank = None
        if rivals:
            journey_const = provider.get_journey_constant(o, d)
            journeys = [journey_const + g for g in gaps]
            beaten = {k for k, tc in rivals.items() if any(j <= tc for j in journeys)}
            rank = max(1, len(rivals) - len(beaten))
            weight = weight_lookup.get((len(rivals), b_od_for(o, d), rank), 0.0)
            rank_component = r * weight
        ranking_reward += rank_component

        breakdown["markets"].append({
            "o": o, "d": d, "gun": gun, "count": count, "rank": rank,
            "connection_component": conn_component, "ranking_component": rank_component,
        })

    total = connection_reward + ranking_reward
    breakdown["connection_reward"] = connection_reward
    breakdown["ranking_reward"] = ranking_reward
    breakdown["total"] = total
    breakdown["claimed_objective_value"] = data.get("objective_value")

    if breakdown_path is not None:
        Path(breakdown_path).write_text(json.dumps(breakdown, indent=2, sort_keys=True, default=str))

    return total, breakdown
