from imopt import returns


def test_total_return_real_growth_plus_net_yield():
    # preço real +10%/ano durante 5 anos; inflação de 2%/ano; renda de 5% bruta
    quarters = [f"{y}Q{q}" for y in range(2020, 2026) for q in range(1, 5)] + ["2026Q1"]
    real = {p: 1000 * 1.1 ** ((int(p[:4]) * 4 + int(p[-1]) - 1 - (2021 * 4)) / 4) for p in quarters}
    nominal = {p: v * 1.02 ** ((int(p[:4]) * 4 + int(p[-1]) - 1 - (2021 * 4)) / 4) for p, v in real.items()}
    def avg(y):
        xs = [v for p, v in nominal.items() if p.startswith(str(y))]
        return sum(xs) / len(xs)
    rent = [[str(y), avg(y) * 0.05 / 12] for y in range(2021, 2027)]
    r = returns.total_return([[p, v] for p, v in nominal.items()], [[p, v] for p, v in real.items()], rent)
    assert r["tr5_from"] == "2021Q1" and r["tr5_to"] == "2026Q1"
    assert abs(r["tr5_price_real"] - 0.10) < 1e-3 and abs(r["tr5_infl"] - 0.02) < 1e-3
    assert abs(r["tr5_yield_net"] - 0.05 * 0.75) < 1e-3
    assert abs(r["tr5_real"] - (0.10 + 0.0375)) < 2e-3


def test_total_return_needs_five_years_and_rents():
    s = [["2024Q1", 100.0], ["2026Q1", 110.0]]
    assert returns.total_return(s, s, [["2024", 1.0]]) is None
    assert returns.total_return([], [], []) is None
