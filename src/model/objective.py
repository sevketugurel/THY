"""Amaç fonksiyonu bileşenleri -- her biri ayrı Pyomo Expression olarak
loglanır (plan §9 TDD sözleşmesi: "amaç fonksiyonu bileşen bileşen loglanır").

M1: bağlantı-sayısı ödülü (Modül 5). M2: sıralama ödülü eklenir -- ikisi
birlikte kullanıldığında model.objective bunların TOPLAMI olacak şekilde
yeniden kurulur (add_ranking_reward_objective, connection_reward zaten
tanımlıysa onu da toplama dahil eder).
"""
import pyomo.environ as pyo


def w_c(j: int) -> float:
    """Azalan getiri ağırlığı: ilk bağlantı 1 puan, sonraki her biri yarısı."""
    return 2 ** (-(j - 1))


def add_connection_reward_objective(model, rho: dict):
    model.connection_reward = pyo.Expression(
        expr=sum(rho[(o, d)] * w_c(j) * model.s[o, d, gun, j] for (o, d, gun, j) in model.SLOTS)
    )
    model.objective = pyo.Objective(expr=model.connection_reward, sense=pyo.maximize)


def add_ranking_reward_objective(model, rho: dict, b_od_data: dict, ranking_table, n_by_market: dict):
    weight_lookup = {(row.n, row.b, row.r): row.weight for row in ranking_table.itertuples()}

    def get_weight(o, d, gun, r):
        n = n_by_market[(o, d, gun)]
        b = b_od_data[(o, d)]
        return weight_lookup.get((n, b, r), 0.0)

    model.ranking_reward = pyo.Expression(
        expr=sum(
            rho[(o, d)] * get_weight(o, d, gun, r) * model.rank_onehot[o, d, gun, r]
            for (o, d, gun, r) in model.RANK_ONEHOT
        )
    )

    if hasattr(model, "objective"):
        model.del_component(model.objective)
    connection_reward = model.connection_reward if hasattr(model, "connection_reward") else 0
    model.objective = pyo.Objective(expr=connection_reward + model.ranking_reward, sense=pyo.maximize)
