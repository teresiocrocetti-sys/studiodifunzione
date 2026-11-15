#!/usr/bin/env python3
"""
Earnings Trade Analyzer - modalità Borsa Italiana (Euronext Milan)

Usa gli stessi 5 fattori e lo stesso punteggio dello script USA (con la
correzione sui gap ribassisti), ma prende i dati da Yahoo Finance tramite la
libreria `yfinance`, che è gratuita e non richiede chiavi. FMP copre i titoli
italiani solo con il piano più costoso.

Limiti da conoscere:
  - yfinance non è un'API ufficiale: può smettere di funzionare o restituire
    date dei risultati mancanti/sbagliate per i titoli italiani. Per questo le
    date si possono indicare a mano con --date (vedi sotto), e hanno la priorità.
  - I prezzi non sono rettificati per i dividendi (auto_adjust=False): se lo
    stacco del dividendo cade il giorno dopo i risultati, il gap risulta più
    basso del reale.
  - Il filtro "entry" della versione USA (prezzo < 30 $) non ha senso in euro
    per Piazza Affari e qui non viene applicato.

Esempi:
    python3 analyze_italia.py --output-dir reports/
    python3 analyze_italia.py --lookback-days 10 --tickers ENI.MI,ISP.MI,UCG.MI
    python3 analyze_italia.py --date ENI.MI=2026-10-30:amc --date ISP.MI=2026-11-04:bmo
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))

from analyze_earnings_trades import analyze_stock  # noqa: E402

ROME = ZoneInfo("Europe/Rome")
APERTURA = time(9, 0)
CHIUSURA = time(17, 30)
DEFAULT_TICKERS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "references", "ftse_mib_tickers.txt"
)

GIUDIZI = {
    "A": "Reazione forte ai risultati. Da valutare, solo con analisi e gestione del rischio proprie.",
    "B": "Reazione buona. Da seguire: attendere conferme.",
    "C": "Segnali misti. Serve altra analisi.",
    "D": "Impostazione debole o gap ribassista: nessun segnale d'acquisto.",
}


# ---------------------------------------------------------------- input

def leggi_tickers(arg: Optional[str], file: Optional[str]) -> list[str]:
    if arg:
        return [t.strip().upper() for t in arg.split(",") if t.strip()]
    path = file or DEFAULT_TICKERS_FILE
    with open(path, encoding="utf-8") as f:
        return [
            line.split("#")[0].strip().upper()
            for line in f
            if line.split("#")[0].strip()
        ]


def leggi_date_manuali(valori: list[str]) -> dict[str, tuple[str, str]]:
    """--date TICKER=AAAA-MM-GG[:bmo|amc] -> {ticker: (data, timing)}"""
    out = {}
    for v in valori or []:
        try:
            ticker, resto = v.split("=", 1)
            data, _, timing = resto.partition(":")
            date.fromisoformat(data)
        except ValueError:
            raise SystemExit(f"Formato --date non valido: {v!r} (atteso TICKER=AAAA-MM-GG[:bmo|amc])")
        timing = timing.lower() or "unknown"
        if timing not in ("bmo", "amc", "unknown"):
            raise SystemExit(f"Orario non valido in {v!r}: usa bmo, amc o niente")
        out[ticker.strip().upper()] = (data, timing)
    return out


def timing_da_orario(ts: datetime) -> str:
    """bmo se prima dell'apertura, amc se dopo la chiusura (ora di Milano)."""
    if ts.tzinfo is None:
        return "unknown"
    t = ts.astimezone(ROME).time()
    if t == time(0, 0):
        return "unknown"  # Yahoo spesso mette mezzanotte quando l'ora non è nota
    if t < APERTURA:
        return "bmo"
    if t >= CHIUSURA:
        return "amc"
    return "unknown"


# ---------------------------------------------------------------- dati (yfinance)

def _yf():
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("Manca yfinance: esegui  pip install yfinance")
    return yf


def yf_date_risultati(ticker: str) -> list[datetime]:
    df = _yf().Ticker(ticker).get_earnings_dates(limit=12)
    if df is None or len(df) == 0:
        return []
    return [ts.to_pydatetime() for ts in df.index]


def yf_prezzi(ticker: str) -> list[dict]:
    df = _yf().Ticker(ticker).history(period="2y", interval="1d", auto_adjust=False)
    if df is None or len(df) == 0:
        return []
    rows = [
        {
            "date": idx.date().isoformat(),
            "open": float(r["Open"]),
            "high": float(r["High"]),
            "low": float(r["Low"]),
            "close": float(r["Close"]),
            "volume": float(r["Volume"]),
        }
        for idx, r in df.iterrows()
    ]
    return list(reversed(rows))  # i calcolatori vogliono il più recente per primo


# ---------------------------------------------------------------- analisi

class FonteNonDisponibile(Exception):
    """Yahoo non ha risposto: non va confuso con 'nessun risultato pubblicato'."""


def trova_risultati(
    ticker: str,
    inizio: date,
    fine: date,
    manuali: dict,
    fonte_date: Callable[[str], list[datetime]],
) -> Optional[tuple[str, str, str]]:
    """Restituisce (data, timing, origine) dei risultati nella finestra, o None."""
    if ticker in manuali:
        d, timing = manuali[ticker]
        if inizio <= date.fromisoformat(d) <= fine:
            return d, timing, "manuale"
        return None
    try:
        eventi = fonte_date(ticker)
    except Exception as exc:  # yfinance solleva eccezioni molto varie
        raise FonteNonDisponibile(f"date dei risultati non disponibili ({exc.__class__.__name__})") from exc
    candidati = []
    for ts in eventi:
        giorno = ts.astimezone(ROME).date() if ts.tzinfo else ts.date()
        if inizio <= giorno <= fine:
            candidati.append((giorno, ts))
    if not candidati:
        return None
    giorno, ts = max(candidati)
    return giorno.isoformat(), timing_da_orario(ts), "yahoo"


def analizza(
    tickers: list[str],
    as_of: date,
    lookback_days: int,
    manuali: dict,
    fonte_date: Callable[[str], list[datetime]] = yf_date_risultati,
    fonte_prezzi: Callable[[str], list[dict]] = yf_prezzi,
    min_gap: float = 0.0,
) -> tuple[list[dict], list[dict]]:
    inizio = as_of - timedelta(days=lookback_days)
    risultati, scartati = [], []
    for ticker in tickers:
        try:
            evento = trova_risultati(ticker, inizio, as_of, manuali, fonte_date)
        except FonteNonDisponibile as exc:
            scartati.append({"ticker": ticker, "motivo": str(exc), "errore_fonte": True})
            print(f"  {ticker}: {exc}", file=sys.stderr)
            continue
        if not evento:
            continue
        data, timing, origine = evento
        try:
            prezzi = fonte_prezzi(ticker)
        except Exception as exc:
            scartati.append({"ticker": ticker, "motivo": f"prezzi non disponibili ({exc.__class__.__name__})",
                             "errore_fonte": True})
            continue
        if len(prezzi) < 200:
            scartati.append({"ticker": ticker, "motivo": f"storico troppo corto ({len(prezzi)} sedute, servono 200)"})
            continue
        a = analyze_stock(prezzi, data, timing)
        if a["gap"].get("warning"):
            scartati.append({"ticker": ticker, "motivo": a["gap"]["warning"]})
            continue
        if abs(a["gap"]["gap_pct"]) < min_gap:
            continue
        c = a["composite"]
        risultati.append({
            "ticker": ticker,
            "data_risultati": data,
            "orario": timing,
            "origine_data": origine,
            "gap_pct": a["gap"]["gap_pct"],
            "direzione": a["gap"]["gap_type"],
            "punteggio": c["composite_score"],
            "voto": c["grade"],
            "giudizio": GIUDIZI[c["grade"]],
            "fattore_debole": c["weakest_component"],
            "fattore_forte": c["strongest_component"],
            "dettaglio": c["component_breakdown"],
            "ultimo_prezzo_eur": round(prezzi[0]["close"], 3),
            "trend_20gg_pct": a["pre_earnings_trend"].get("return_20d_pct"),
            "volumi_20_su_60": a["volume_trend"].get("vol_ratio_20_60"),
        })
    risultati.sort(key=lambda r: r["punteggio"], reverse=True)
    return risultati, scartati


# ---------------------------------------------------------------- report

ORARI = {"bmo": "prima apertura", "amc": "dopo chiusura", "unknown": "non noto*"}


def scrivi_report(risultati, scartati, meta, out_dir) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(ROME).strftime("%Y-%m-%d_%H%M%S")
    jpath = os.path.join(out_dir, f"earnings_italia_{stamp}.json")
    mpath = os.path.join(out_dir, f"earnings_italia_{stamp}.md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "risultati": risultati, "scartati": scartati}, f, ensure_ascii=False, indent=2)

    righe = [
        "# Reazioni ai risultati – Borsa Italiana",
        "",
        f"Finestra: dal {meta['dal']} al {meta['al']} · Titoli esaminati: {meta['titoli_esaminati']} · "
        f"Con risultati nella finestra: {len(risultati)}",
        "",
        "> Strumento di screening, non consiglio d'investimento. Pesi e soglie del punteggio sono "
        "scelte dell'autore originale e non sono stati verificati sui titoli italiani.",
        "",
    ]
    n_err = sum(1 for s in scartati if s.get("errore_fonte"))
    if n_err:
        righe += [f"> **ATTENZIONE:** per {n_err} titoli la fonte dati non ha risposto. "
                  "L'elenco qui sotto può essere incompleto.", ""]
    if risultati:
        righe += [
            "| Titolo | Data | Orario | Gap | Voto | Punti | Trend 20gg | Vol 20/60 | Prezzo € |",
            "|---|---|---|---:|:---:|---:|---:|---:|---:|",
        ]
        for r in risultati:
            trend = f"{r['trend_20gg_pct']:+.1f}%" if r["trend_20gg_pct"] is not None else "–"
            vol = f"{r['volumi_20_su_60']:.2f}" if r["volumi_20_su_60"] is not None else "–"
            righe.append(
                f"| {r['ticker']} | {r['data_risultati']} | {ORARI[r['orario']]} | {r['gap_pct']:+.1f}% | "
                f"**{r['voto']}** | {r['punteggio']:.1f} | {trend} | {vol} | {r['ultimo_prezzo_eur']} |"
            )
        righe += ["", "\\* orario non noto: il gap è misurato come se i risultati fossero usciti dopo la chiusura.", ""]
        righe += ["## Dettaglio", ""]
        for r in risultati:
            righe.append(f"**{r['ticker']}** – voto {r['voto']} ({r['punteggio']:.1f}). {r['giudizio']} "
                         f"Punto più forte: {r['fattore_forte']}; più debole: {r['fattore_debole']}. "
                         f"Data risultati: fonte {r['origine_data']}.")
            righe.append("")
    else:
        righe += ["Nessun titolo con risultati nella finestra (o date non trovate su Yahoo: indicarle con --date).", ""]
    if scartati:
        righe += ["## Esclusi", ""] + [f"- {s['ticker']}: {s['motivo']}" for s in scartati] + [""]
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(righe))
    return jpath, mpath


def main(argv=None):
    ap = argparse.ArgumentParser(description="Earnings Trade Analyzer – Borsa Italiana (dati Yahoo Finance)")
    ap.add_argument("--output-dir", default="reports/")
    ap.add_argument("--lookback-days", type=int, default=7, help="giorni di calendario all'indietro (default 7)")
    ap.add_argument("--as-of", help="data di riferimento AAAA-MM-GG (default: oggi, ora di Milano)")
    ap.add_argument("--tickers", help="elenco separato da virgole, es. ENI.MI,ISP.MI")
    ap.add_argument("--tickers-file", help="file con un ticker per riga (default: FTSE MIB)")
    ap.add_argument("--date", action="append", default=[], metavar="TICKER=AAAA-MM-GG[:bmo|amc]",
                    help="data dei risultati indicata a mano; ripetibile; ha priorità su Yahoo")
    ap.add_argument("--min-gap", type=float, default=0.0, help="gap minimo in %% (valore assoluto)")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(ROME).date()
    tickers = leggi_tickers(args.tickers, args.tickers_file)
    manuali = leggi_date_manuali(args.date)
    for t in manuali:
        if t not in tickers:
            tickers.append(t)

    print(f"Analizzo {len(tickers)} titoli, risultati dal {as_of - timedelta(days=args.lookback_days)} al {as_of}…",
          file=sys.stderr)
    risultati, scartati = analizza(tickers, as_of, args.lookback_days, manuali, min_gap=args.min_gap)
    meta = {
        "mercato": "Euronext Milan",
        "fonte_dati": "Yahoo Finance (yfinance)",
        "dal": (as_of - timedelta(days=args.lookback_days)).isoformat(),
        "al": as_of.isoformat(),
        "titoli_esaminati": len(tickers),
        "generato": datetime.now(ROME).isoformat(timespec="seconds"),
    }
    errori = sum(1 for s in scartati if s.get("errore_fonte"))
    meta["errori_fonte_dati"] = errori
    j, m = scrivi_report(risultati[: args.top], scartati, meta, args.output_dir)
    print(f"Report: {m}\nJSON:   {j}", file=sys.stderr)
    if errori and errori >= len(tickers) - len(manuali):
        # Come nella versione USA: una fonte guasta non va presentata come "giornata tranquilla".
        print(f"ERRORE: Yahoo Finance non ha risposto per {errori} titoli su {len(tickers)}. "
              "Il report vuoto NON significa che non ci siano stati risultati. Riprova più tardi "
              "o indica le date con --date.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
