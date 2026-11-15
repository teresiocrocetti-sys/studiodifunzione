"""Modalità Borsa Italiana, con fonti dati finte (nessuna rete)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import analyze_italia as it

ROME = ZoneInfo("Europe/Rome")


def _serie(gap, giorni=260, crescita=1.004):
    rows, d, p = [], date(2025, 11, 3), 10.0
    while len(rows) < giorni:
        if d.weekday() < 5:
            p *= crescita
            rows.append({"date": d.isoformat(), "open": p, "high": p, "low": p, "close": p, "volume": 1e6})
        d += timedelta(days=1)
    risultati = rows[-3]["date"]
    rows[-2]["open"] = rows[-2]["close"] = rows[-3]["close"] * gap
    rows[-1]["open"] = rows[-1]["close"] = rows[-2]["close"]
    return list(reversed(rows)), risultati


def test_timing_da_orario_milano():
    assert it.timing_da_orario(datetime(2026, 11, 5, 7, 30, tzinfo=ROME)) == "bmo"
    assert it.timing_da_orario(datetime(2026, 11, 5, 18, 0, tzinfo=ROME)) == "amc"
    assert it.timing_da_orario(datetime(2026, 11, 5, 12, 0, tzinfo=ROME)) == "unknown"
    assert it.timing_da_orario(datetime(2026, 11, 5, 0, 0, tzinfo=ROME)) == "unknown"
    # Yahoo spesso usa l'ora di New York: 13:00 NY = 19:00 Milano -> dopo chiusura
    assert it.timing_da_orario(datetime(2026, 11, 5, 13, 0, tzinfo=ZoneInfo("America/New_York"))) == "amc"


def test_date_manuali():
    m = it.leggi_date_manuali(["eni.mi=2026-10-30:amc", "ISP.MI=2026-11-04"])
    assert m == {"ENI.MI": ("2026-10-30", "amc"), "ISP.MI": ("2026-11-04", "unknown")}


def test_analisi_gap_su_e_gap_giu():
    su, d_su = _serie(1.08)
    giu, d_giu = _serie(0.88)
    prezzi = {"SU.MI": su, "GIU.MI": giu}
    eventi = {
        "SU.MI": [datetime.fromisoformat(d_su + "T18:00:00").replace(tzinfo=ROME)],
        "GIU.MI": [datetime.fromisoformat(d_giu + "T18:00:00").replace(tzinfo=ROME)],
    }
    as_of = date.fromisoformat(su[0]["date"])
    ris, scart = it.analizza(["SU.MI", "GIU.MI", "VUOTO.MI"], as_of, 7, {},
                             fonte_date=lambda t: eventi.get(t, []),
                             fonte_prezzi=lambda t: prezzi[t])
    per = {r["ticker"]: r for r in ris}
    assert set(per) == {"SU.MI", "GIU.MI"}
    assert per["SU.MI"]["direzione"] == "up" and per["SU.MI"]["voto"] in ("A", "B", "C")
    assert per["GIU.MI"]["direzione"] == "down" and per["GIU.MI"]["voto"] == "D"
    assert ris[0]["ticker"] == "SU.MI"
    assert scart == []


def test_data_manuale_ha_priorita_e_errori_yahoo_non_bloccano(tmp_path):
    serie, d = _serie(1.06)
    as_of = date.fromisoformat(serie[0]["date"])

    def date_rotte(t):
        raise RuntimeError("yahoo giù")

    ris, _ = it.analizza(["ENI.MI", "ISP.MI"], as_of, 7, {"ENI.MI": (d, "amc")},
                         fonte_date=date_rotte, fonte_prezzi=lambda t: serie)
    assert [r["ticker"] for r in ris] == ["ENI.MI"]
    assert ris[0]["origine_data"] == "manuale"
    j, m = it.scrivi_report(ris, [], {"dal": "x", "al": "y", "titoli_esaminati": 2}, str(tmp_path))
    testo = open(m, encoding="utf-8").read()
    assert "ENI.MI" in testo and "non consiglio d'investimento" in testo


def test_storico_corto_viene_scartato():
    serie, d = _serie(1.06, giorni=120)
    as_of = date.fromisoformat(serie[0]["date"])
    ris, scart = it.analizza(["X.MI"], as_of, 7, {"X.MI": (d, "amc")}, fonte_prezzi=lambda t: serie)
    assert ris == [] and "storico troppo corto" in scart[0]["motivo"]


def test_elenco_ftse_mib_si_legge():
    t = it.leggi_tickers(None, None)
    assert "ENI.MI" in t and all(x.endswith(".MI") for x in t) and len(t) >= 35


def test_fonte_guasta_non_diventa_giornata_tranquilla(monkeypatch, tmp_path):
    def rotto(t):
        raise ConnectionError("rete giù")

    monkeypatch.setattr(it, "yf_date_risultati", rotto)
    monkeypatch.setattr(it.analizza, "__defaults__", (rotto, rotto, 0.0))
    codice = it.main(["--tickers", "ENI.MI,ISP.MI", "--output-dir", str(tmp_path)])
    assert codice == 1
    md = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "ATTENZIONE" in md
