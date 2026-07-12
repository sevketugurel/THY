"""M5i RCR Engine C1 under-claim floor mantığı (spec §3.2) -- SİGORTA ARTEFAKTI üretimi.

UYARI (spec §0.1/§8): bu mekanizma docs/model.md'nin B semantiğiyle ("uygun
olan sunulmak zorunda", çift yönlü reifikasyon) bilinçli olarak çelişir --
validator'ın seçim-bazlı E1/E2 aktivasyonundan yararlanır. Teslim paketine
ana çözüm olarak GİRMEZ; scripts/make_underclaim_floor.py sidecar notunda
risk paragrafı zorunludur."""


def choose_directions_to_drop(records):
    """Her ihlalli çift için DÜŞÜK reward_contribution'lı yönü seç.
    Eşitlik kırıcı: önce daha az n_selected, sonra yön tuple'ı (determinizm).
    records: build_residual_records çıktısı (JSON round-trip'i de kabul)."""
    drops = []
    for r in records:
        options = []
        for tag in ("fwd", "bwd"):
            d = r["directions"][tag]
            options.append((d["reward_contribution"], d["n_selected"], tuple(d["direction"])))
        options.sort()
        drops.append(options[0][2])
    return drops


def drop_directions(data, directions):
    """Output-şemalı dict'ten verilen yönlerin selected_connections +
    ranking_results girdilerini düşürür. adjusted_flight_times'a DOKUNMAZ
    (zamanlar aynen uçar -- under-claim'in tanımı). Girdiyi mutate etmez.
    Returns (new_data, n_connections_dropped, n_ranking_dropped)."""
    dirset = {tuple(d) for d in directions}

    def _hit(od_str, gun):
        o, d = od_str.split("-")
        return (o, d, gun) in dirset

    new_sc, n_conn = [], 0
    for conn in data["selected_connections"]:
        if _hit(conn["od"], conn["gun"]):
            n_conn += 1
        else:
            new_sc.append(conn)

    new_rr, n_rank = [], 0
    for entry in data.get("ranking_results", []):
        if "od" in entry and "gun" in entry and _hit(entry["od"], entry["gun"]):
            n_rank += 1
        else:
            new_rr.append(entry)

    new_data = dict(data)
    new_data["selected_connections"] = new_sc
    new_data["ranking_results"] = new_rr
    return new_data, n_conn, n_rank
