
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "latest.json"

MARKETS = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "DAX": "^GDAXI",
    "Euro Stoxx 50": "^STOXX50E",
    "FTSE 100": "^FTSE",
    "Nikkei 225": "^N225",
    "Hang Seng": "^HSI",
}


def download_close(ticker, period="2y"):
    data = yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )

    if data.empty:
        raise ValueError(f"Keine Kursdaten für {ticker}")

    close = data["Close"]

    # Unterstützt verschiedene yfinance-Spaltenformate.
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    return close.dropna().astype(float)


def analyze_market(name, ticker):
    close = download_close(ticker)

    if len(close) < 50:
        raise ValueError("Zu wenige Kursdaten")

    last = float(close.iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1])
    ma200 = (
        float(close.rolling(200).mean().iloc[-1])
        if len(close) >= 200
        else None
    )

    ret20 = (
        float(close.iloc[-1] / close.iloc[-21] - 1)
        if len(close) >= 21
        else 0.0
    )

    signals = [float(last < ma50)]

    if ma200 is not None:
        signals.append(float(last < ma200))

    # Schwache 20-Tage-Renditen erhöhen den Teilscore.
    signals.append(float(np.clip((0.03 - ret20) / 0.13, 0, 1)))

    return {
        "name": name,
        "ticker": ticker,
        "close": round(last, 2),
        "return_20d_pct": round(ret20 * 100, 2),
        "below_50d": last < ma50,
        "below_200d": (
            last < ma200 if ma200 is not None else None
        ),
        "score": round(float(np.mean(signals) * 100), 1),
    }


def analyze_vix():
    close = download_close("^VIX", period="3mo")

    if len(close) < 6:
        raise ValueError("Zu wenige VIX-Daten")

    current = float(close.iloc[-1])
    previous = float(close.iloc[-6])
    change = current / previous - 1 if previous else 0.0

    level = np.clip((current - 15) / 35, 0, 1) * 100
    jump = np.clip(change / 0.50, 0, 1) * 100
    score = 0.65 * level + 0.35 * jump

    return {
        "value": round(current, 2),
        "change_5_sessions_pct": round(change * 100, 2),
        "score": round(float(score), 1),
    }


def fetch_news():
    query = (
        '"stock market" OR recession OR "bank crisis" OR '
        '"financial crisis" OR inflation OR tariffs OR '
        '"central bank" OR "credit market"'
    )

    response = requests.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": 50,
            "sort": "HybridRel",
        },
        headers={"User-Agent": "MarketWarning/1.0"},
        timeout=25,
    )
    response.raise_for_status()

    articles = response.json().get("articles", [])
    seen = set()
    result = []

    for article in articles:
        title = (article.get("title") or "").strip()
        if not title or title.lower() in seen:
            continue

        seen.add(title.lower())
        text = title.lower()

        # Einfache Schlüsselwörter, keine echte Sentiment-KI.
        risk_terms = [
            "market crash", "bank crisis", "bank failure",
            "recession", "default", "liquidity crisis",
            "debt crisis", "selloff", "financial crisis",
            "war escalation", "emergency rate hike",
        ]

        relief_terms = [
            "inflation cools", "ceasefire",
            "strong earnings", "market rally",
        ]

        result.append({
            "title": title,
            "url": article.get("url", ""),
            "source": article.get("domain", ""),
            "date": article.get("seendate", ""),
            "risk_hits": sum(term in text for term in risk_terms),
            "relief_hits": sum(term in text for term in relief_terms),
        })

    return result


def main():
    markets = []
    errors = []

    for name, ticker in MARKETS.items():
        try:
            markets.append(analyze_market(name, ticker))
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:150]}")

    try:
        vix = analyze_vix()
    except Exception as exc:
        vix = None
        errors.append(f"VIX: {str(exc)[:150]}")

    try:
        news = fetch_news()
        news_error = None
    except Exception as exc:
        news = []
        news_error = str(exc)[:200]

    # Fehlende Daten werden nicht als Nullrisiko gewertet.
    trend_score = (
        float(np.mean([m["score"] for m in markets]))
        if markets else None
    )

    news_score = None
    if news:
        risk_share = sum(a["risk_hits"] > 0 for a in news) / len(news)
        relief_share = sum(a["relief_hits"] > 0 for a in news) / len(news)
        news_score = float(
            np.clip(50 + 100 * (risk_share - relief_share), 0, 100)
        )

    components = [
        ("Markttrend", trend_score, 0.45),
        ("VIX", vix["score"] if vix else None, 0.30),
        ("Nachrichten", news_score, 0.25),
    ]

    available = [
        (name, value, weight)
        for name, value, weight in components
        if value is not None
    ]

    if not available:
        raise RuntimeError("Alle Datenquellen sind ausgefallen.")

    score = sum(value * weight for _, value, weight in available)
    score /= sum(weight for _, _, weight in available)

    missing = [
        name for name, value, _ in components if value is None
    ]

    if score < 25:
        level = "GRUEN"
    elif score < 45:
        level = "GELB"
    elif score < 65:
        level = "ORANGE"
    elif score < 80:
        level = "ROT"
    else:
        level = "KRITISCH"

    reasons = []

    if trend_score is not None and trend_score >= 50:
        reasons.append("Mehrere Markttrend-Signale sind schwach.")

    if vix is not None and vix["score"] >= 50:
        reasons.append("Der VIX zeigt erhöhte Marktanspannung.")

    if news_score is not None and news_score >= 60:
        reasons.append("Die Nachrichtenstichprobe enthält viele Risikobegriffe.")

    if not reasons:
        reasons.append(
            "Keine definierte Warnschwelle erreicht. "
            "Das schließt einen plötzlichen Rückgang nicht aus."
        )

    if missing:
        reasons.append(
            "Daten fehlen für: " + ", ".join(missing)
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "score": round(float(score), 1),
        "level": level,
        "components": {
            name: {
                "score": round(float(value), 1) if value is not None else None,
                "weight": weight,
            }
            for name, value, weight in components
        },
        "markets": markets,
        "vix": vix,
        "news": news[:20],
        "reasons": reasons,
        "data_errors": errors,
        "news_error": news_error,
        "missing_components": missing,
        "method": "Heuristik, nicht als Crashprognose validiert",
    }

    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Analyse abgeschlossen")
    print("Score:", report["score"])
    print("Warnstufe:", report["level"])
    print("Datei:", OUTPUT)


if __name__ == "__main__":
    main()
