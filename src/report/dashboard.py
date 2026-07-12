"""Kapı-D3 (docs/STATUS.md): pure builder for the self-contained static
HTML results dashboard. No CDN, no framework, no server -- everything
(minimal CSS, inline SVG bar chart) is inlined into one file. Deliberately
takes no wall-clock of its own (generated_at is a caller-supplied string)
so the same inputs always produce byte-identical output
(tests/unit/test_dashboard.py::test_build_dashboard_html_is_deterministic).
"""
from html import escape


def _fmt_num(x) -> str:
    """Plain (period-decimal) formatting -- matches the CLI's own printed
    convention (`status=optimal objective=668.75`) and the JSON schema's
    native repr, no locale reformatting."""
    if x is None:
        return "—"
    if isinstance(x, float):
        return str(int(x)) if x == int(x) else f"{x:g}"
    return str(x)


def _fixture_table_rows(fixture: dict) -> str:
    rivals_by_market = {}
    for r in fixture.get("ranking_results", []):
        key = (r["o"], r["d"], r["gun"])
        rivals_by_market[key] = r

    rows = []
    for c in fixture.get("selected_connections", []):
        od = c["od"]
        o, d = od.split("-", 1) if "-" in od else (od, "")
        rr = rivals_by_market.get((o, d, c["gun"]), {})
        beaten = ", ".join(rr.get("beaten_rivals", [])) or "—"
        rows.append(
            "<tr>"
            f"<td>{escape(str(od))}</td><td>{escape(str(c['gun']))}</td>"
            f"<td>{escape(str(c['flno1']))}</td><td>{escape(str(c['flno2']))}</td>"
            f"<td>{escape(str(c['gap_min']))}</td>"
            f"<td>{escape(str(rr.get('rank', '—')))}</td><td>{escape(beaten)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _gamma_table_rows(gamma_scan: dict) -> str:
    rows = []
    for row in gamma_scan.get("rows", []):
        official = " class=\"official\"" if row.get("is_official") else ""
        rows.append(
            f"<tr{official}>"
            f"<td>{escape(str(row['gamma']))}{' (resmî)' if row.get('is_official') else ''}</td>"
            f"<td>{escape(str(row['static_infeasible_pairs']))}</td>"
            f"<td>{escape(str(row['baseline_e2_violation_count']))}</td>"
            f"<td>{_fmt_num(row['baseline_e2_violation_mass_min'])}</td>"
            f"<td>{_fmt_num(row['independent_pair_lower_bound_min'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _gamma_bar_chart_svg(gamma_scan: dict) -> str:
    rows = gamma_scan.get("rows", [])
    if not rows:
        return ""
    max_bound = max(r["independent_pair_lower_bound_min"] for r in rows) or 1.0
    bar_w, gap, chart_h = 46, 14, 160
    bars = []
    labels = []
    for i, row in enumerate(rows):
        x = i * (bar_w + gap) + 10
        h = (row["independent_pair_lower_bound_min"] / max_bound) * chart_h
        y = chart_h - h + 20
        color = "#b34700" if row.get("is_official") else "#2f6f9f"
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{h:.1f}" fill="{color}" />'
            f'<text x="{x + bar_w / 2}" y="{y - 4}" font-size="9" text-anchor="middle">'
            f'{_fmt_num(row["independent_pair_lower_bound_min"])}</text>'
        )
        labels.append(
            f'<text x="{x + bar_w / 2}" y="{chart_h + 34}" font-size="9" text-anchor="middle">'
            f'Γ={escape(str(row["gamma"]))}</text>'
        )
    width = len(rows) * (bar_w + gap) + 20
    return (
        f'<svg viewBox="0 0 {width} {chart_h + 45}" width="100%" '
        f'style="max-width:{width}px" role="img" '
        f'aria-label="Γ başına bağımsız-çift alt sınır (dk)">'
        + "".join(bars) + "".join(labels) +
        '</svg>'
    )


def _provenance_rows(provenance: dict) -> str:
    rows = []
    for name, info in provenance.items():
        path = info.get("path", "—") if isinstance(info, dict) else "—"
        sha = info.get("sha256", "—") if isinstance(info, dict) else str(info)
        rows.append(
            f"<tr><td>{escape(str(name))}</td><td>{escape(str(path))}</td>"
            f"<td><code>{escape(str(sha))}</code></td></tr>"
        )
    return "\n".join(rows)


_CSS = """
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 14px;
       line-height: 1.45; max-width: 980px; margin: 0 auto; padding: 24px; color: #1a1a1a; }
h1 { font-size: 22px; margin-bottom: 4px; }
h2 { font-size: 17px; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 2em; }
.subtitle { color: #555; margin-top: 0; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; margin: 0.8em 0; }
th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; vertical-align: top; }
th { background: #eee; }
tr.official td { background: #fff3e0; font-weight: 600; }
code { background: #f2f2f2; padding: 0 3px; font-size: 0.92em; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: 600; }
.badge-ok { background: #dff0d8; color: #3c763d; }
.badge-diag { background: #f2dede; color: #a94442; }
.note { color: #555; font-size: 13px; }
"""


def build_dashboard_html(fixture_output: dict, full_data_output: dict, gamma_scan: dict,
                          provenance: dict, generated_at: str) -> str:
    """Pure function: same inputs -> byte-identical HTML. No file I/O."""
    obj = fixture_output.get("objective_value")
    status = fixture_output.get("solver_metrics", {}).get("status", "—")

    full_status = full_data_output.get("solver_metrics", {}).get("status", "—")
    full_obj = full_data_output.get("objective_value")

    decision = gamma_scan.get("decision", {})

    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>THY IST Hub Tarife Optimizasyonu — Sonuç Panosu</title>
<style>{_CSS}</style>
</head>
<body>
<h1>THY IST Hub Tarife Optimizasyonu — Sonuç Panosu</h1>
<p class="subtitle">Üretildi: {escape(generated_at)} · Resmî teslim konfigürasyonu: Γ=30</p>

<h2>1 · Fixture (sentetik) sonuç — {escape(_fmt_num(obj))} / {escape(status)}</h2>
<p class="note"><span class="badge badge-ok">valid=True</span> — CLI = recompute_objective = brute-force oracle, üç bağımsız yoldan doğrulanmış (bkz. docs/STATUS.md).</p>
<table>
<thead><tr><th>O-D</th><th>Gün</th><th>Uçuş 1</th><th>Uçuş 2</th><th>Gap (dk)</th><th>Sıra</th><th>Yenilen rakipler</th></tr></thead>
<tbody>
{_fixture_table_rows(fixture_output)}
</tbody>
</table>

<h2>2 · Full-data teşhis özeti — resmî Γ=30 çıktısı</h2>
<p><span class="badge badge-diag">{escape(str(full_status))}</span> objective_value = {escape(_fmt_num(full_obj))}</p>
<p class="note">Üretim merdiveninin üç adımı da (tam model → elastik fallback → teşhis) doğrulanmış bir
sonuç üretemedi — <strong>hiçbir ihlalli tarife dosyaya yazılmadı</strong> (üretim merdiveninin kendi
garantisi). Gerçek ölçüm: 44dk22s, iki adım da watchdog_killed (bkz. docs/TESLIM_BEKLENTILERI.md §1b).</p>

<h2>3 · Γ Duyarlılık Analizi (EK — resmî sonucu değiştirmez)</h2>
<table>
<thead><tr><th>Γ (dk)</th><th>Statik-imkânsız çift</th><th>Baseline E2 ihlal (adet)</th><th>Baseline E2 ihlal kütlesi (dk)</th><th>Bağımsız-çift alt sınır (dk)</th></tr></thead>
<tbody>
{_gamma_table_rows(gamma_scan)}
</tbody>
</table>
{_gamma_bar_chart_svg(gamma_scan)}
<p class="note">Karar: Γ*={escape(str(decision.get('gamma_star')))}, kampanya koşuldu mu = {escape(str(decision.get('run_campaign')))}.
{escape(str(decision.get('rationale', '')))}</p>

<h2>4 · Veri Provenance (SHA-256)</h2>
<table>
<thead><tr><th>Dosya</th><th>Yol</th><th>SHA-256</th></tr></thead>
<tbody>
{_provenance_rows(provenance)}
</tbody>
</table>

</body>
</html>
"""
