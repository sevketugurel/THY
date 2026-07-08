"""Amaç fonksiyonu bileşenleri -- her biri ayrı Pyomo Expression olarak
loglanır (plan §9 TDD sözleşmesi: "amaç fonksiyonu bileşen bileşen loglanır").

M1 scope: yalnızca bağlantı-sayısı ödülü (Modül 5). Sıralama ödülü M2'de eklenir.
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
