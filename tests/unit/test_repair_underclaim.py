"""M5i RCR Engine C1 (spec §3.2): under-claim floor mantığı -- saf Python, IO/solver yok."""
from src.repair.underclaim import choose_directions_to_drop, drop_directions


def _record(o, d, gun, fwd_contrib, bwd_contrib, fwd_sel=2, bwd_sel=2):
    return {
        "pair": [o, d, gun], "e1": 0.0, "e2": 50.0, "total": 50.0,
        "directions": {
            "fwd": {"direction": [o, d, gun], "killable": True, "n_candidates": 3,
                    "n_selected": fwd_sel, "has_forced_on": False, "rho": 1,
                    "reward_contribution": fwd_contrib},
            "bwd": {"direction": [d, o, gun], "killable": True, "n_candidates": 3,
                    "n_selected": bwd_sel, "has_forced_on": False, "rho": 1,
                    "reward_contribution": bwd_contrib},
        },
        "both_unkillable": False,
    }


def test_chooses_lower_contribution_side_per_pair():
    records = [_record("AAA", "BBB", 1, 500.0, 40.0), _record("CCC", "DDD", 2, 10.0, 90.0)]
    drops = choose_directions_to_drop(records)
    assert drops == [("BBB", "AAA", 1), ("CCC", "DDD", 2)]


def test_tie_breaks_on_fewer_selected_then_tuple():
    r = _record("AAA", "BBB", 1, 100.0, 100.0, fwd_sel=1, bwd_sel=5)
    assert choose_directions_to_drop([r]) == [("AAA", "BBB", 1)]
    r2 = _record("AAA", "BBB", 1, 100.0, 100.0, fwd_sel=2, bwd_sel=2)
    assert choose_directions_to_drop([r2]) == [("AAA", "BBB", 1)]  # tuple sırası


def test_drop_directions_filters_connections_and_rankings_only():
    data = {
        "adjusted_flight_times": [{"role": "IB", "flno": 1, "gun": 1, "time_min": 100}],
        "selected_connections": [
            {"od": "AAA-BBB", "flno1": 1, "flno2": 2, "gap_min": 90, "gun": 1},
            {"od": "BBB-AAA", "flno1": 3, "flno2": 4, "gap_min": 90, "gun": 1},
            {"od": "AAA-BBB", "flno1": 5, "flno2": 6, "gap_min": 90, "gun": 2},  # farklı gün -- kalır
        ],
        "ranking_results": [{"od": "AAA-BBB", "gun": 1, "rank": 1, "beaten_rivals": []}],
        "objective_value": 123.0,
    }
    new_data, n_conn, n_rank = drop_directions(data, [("AAA", "BBB", 1)])
    assert n_conn == 1 and n_rank == 1
    assert len(new_data["selected_connections"]) == 2
    assert all(not (c["od"] == "AAA-BBB" and c["gun"] == 1)
               for c in new_data["selected_connections"])
    assert new_data["ranking_results"] == []
    assert new_data["adjusted_flight_times"] == data["adjusted_flight_times"]  # DOKUNULMAZ
    assert data["selected_connections"][0]["od"] == "AAA-BBB"  # girdi mutate edilmedi
    assert len(data["selected_connections"]) == 3
