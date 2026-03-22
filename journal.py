"""
utils/journal.py — Trade kayıt defteri
Her trade CSV'ye yazılır. Backtest veya performans analizinde kullanılır.
"""
import csv
import os
from datetime import datetime
from pathlib import Path


JOURNAL_PATH = Path("logs/trade_journal.csv")
HEADERS = [
    "date", "symbol", "direction", "entry_price", "stop_loss",
    "tp1", "tp2", "quantity", "risk_usdt", "rr_ratio",
    "pnl_usdt", "result", "confluence_score", "confluence_reasons",
    "duration_min", "close_reason"
]


def init_journal():
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not JOURNAL_PATH.exists():
        with open(JOURNAL_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()


def log_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    tp1: float,
    tp2: float,
    quantity: float,
    risk_usdt: float,
    rr_ratio: float,
    pnl_usdt: float,
    confluence_score: int,
    confluence_reasons: list[str],
    duration_min: float = 0,
    close_reason: str = ""
):
    result = "WIN" if pnl_usdt > 0 else "LOSS" if pnl_usdt < 0 else "BE"

    row = {
        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "direction": direction,
        "entry_price": round(entry_price, 6),
        "stop_loss": round(stop_loss, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "quantity": round(quantity, 6),
        "risk_usdt": round(risk_usdt, 2),
        "rr_ratio": round(rr_ratio, 2),
        "pnl_usdt": round(pnl_usdt, 2),
        "result": result,
        "confluence_score": confluence_score,
        "confluence_reasons": " | ".join(confluence_reasons),
        "duration_min": round(duration_min, 1),
        "close_reason": close_reason
    }

    with open(JOURNAL_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writerow(row)
