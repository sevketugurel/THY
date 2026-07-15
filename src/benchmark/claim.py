"""Claim-complete connection and ranking derivation for the benchmark pipeline."""

from src.data.competitors import derive_rival_best_times


def derive_market_universe(tk, rho, provider):
    """Return scorable markets and K_od source labels for the claim universe."""
    market_k_od = {}
    dropped = []
    sources = {}
    for o, d in sorted(rho):
        try:
            market_k_od[(o, d)] = provider.get_journey_constant(o, d)
            sources[(o, d)] = "direct"
        except KeyError:
            try:
                market_k_od[(o, d)] = provider.get_journey_constant_estimate(o, d)
                sources[(o, d)] = "estimated"
            except KeyError:
                dropped.append((o, d))
    return market_k_od, dropped, sources


def build_full_claim(tk, market_k_od: dict, times: dict, L: int, U: int) -> list:
    """Derive every supported connection from final times.

    The raw table lists itineraries, but a claim-complete solution is the full
    inbound-by-origin x outbound-by-destination cross product for scorable
    markets and days. Each leg must exist independently in the raw TK rows.
    """
    connections = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        day = tk[tk["gun"] == gun]
        inbound_by_o = {}
        outbound_by_d = {}
        for row in day.itertuples():
            inbound_by_o.setdefault(row.dep1, set()).add(int(row.flno1))
            outbound_by_d.setdefault(row.arr2, set()).add(int(row.flno2))
        for o, d in sorted(market_k_od):
            for f1 in sorted(inbound_by_o.get(o, ())):
                t_arr = times.get(("IB", f1, gun))
                if t_arr is None:
                    continue
                for f2 in sorted(outbound_by_d.get(d, ())):
                    t_dep = times.get(("OB", f2, gun))
                    if t_dep is None:
                        continue
                    gap = t_dep - t_arr
                    if L <= gap <= U:
                        connections.append({
                            "od": f"{o}-{d}",
                            "flno1": f1,
                            "flno2": f2,
                            "gun": gun,
                            "gap_min": gap,
                        })
    connections.sort(key=lambda c: (c["od"], c["flno1"], c["flno2"], c["gun"]))
    return connections


def derive_ranking_from_claim(od_table, market_k_od: dict, connections: list) -> list:
    """Derive actual rank/beaten-rivals claims from the full connection claim."""
    gaps_by_market = {}
    for conn in connections:
        o, d = conn["od"].split("-")
        gaps_by_market.setdefault((o, d, conn["gun"]), []).append(conn["gap_min"])

    results = []
    for (o, d, gun), gaps in sorted(gaps_by_market.items()):
        rivals = derive_rival_best_times(od_table, o, d, gun)
        if not rivals:
            continue
        k_od = market_k_od[(o, d)]
        journeys = [k_od + gap for gap in gaps]
        beaten = sorted(k for k, t_comp in rivals.items() if any(j <= t_comp for j in journeys))
        rank = max(1, len(rivals) - len(beaten))
        results.append({"o": o, "d": d, "gun": gun, "rank": rank, "beaten_rivals": beaten})
    return results
