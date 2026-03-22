"""
app.py — Flask + SocketIO backend
Her 15 dakikada bir SMC analizi yapar, WebSocket ile frontend'e iter.
"""
import time
import threading
import requests
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.market_structure import analyze_market_structure, Bias
from core.order_blocks import detect_order_blocks, OBType
from core.fair_value_gap import detect_fvg, FVGType
from core.liquidity import detect_liquidity_zones, LiquidityType, check_liquidity_sweep
from core.htf_bias import analyze_htf_bias, PriceZone
from core.risk_manager import calculate_atr

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
HTF = "4h"
LTF = "15m"

# Bellekte tutulan state
state = {
    "signals": [],
    "bias": {},
    "order_blocks": {},
    "fvgs": {},
    "trades": [],
    "stats": {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0,
        "daily_pnl": 0.0,
        "balance": 1000.0
    },
    "last_update": None
}


# ── Veri çekme ──────────────────────────────────────────────────────────────

def fetch_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    url = "https://api.binance.com/api/v3/klines"
    try:
        resp = requests.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=10)
        raw = resp.json()
        if not isinstance(raw, list):
            return pd.DataFrame()
        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.error(f"Veri çekme hatası {symbol}: {e}")
        return pd.DataFrame()


def fetch_price(symbol: str) -> float:
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol}, timeout=5
        )
        return float(resp.json()["price"])
    except:
        return 0.0


# ── SMC Analiz ──────────────────────────────────────────────────────────────

def analyze_symbol(symbol: str) -> dict:
    df_ltf = fetch_klines(symbol, LTF, limit=300)
    df_htf = fetch_klines(symbol, HTF, limit=200)

    if df_ltf.empty or df_htf.empty:
        return {}

    current_price = df_ltf["close"].iloc[-1]
    atr = calculate_atr(df_ltf)

    # HTF Bias
    htf = analyze_htf_bias(df_htf)

    # LTF Market Structure
    ms = analyze_market_structure(df_ltf, lookback=5)

    # Order Blocks
    obs = detect_order_blocks(df_ltf, lookback=50)
    bullish_obs = [o for o in obs if o.ob_type == OBType.BULLISH]
    bearish_obs = [o for o in obs if o.ob_type == OBType.BEARISH]

    # FVG
    fvgs = detect_fvg(df_ltf, min_size_pct=0.0002)
    bullish_fvgs = [f for f in fvgs if f.fvg_type == FVGType.BULLISH]
    bearish_fvgs = [f for f in fvgs if f.fvg_type == FVGType.BEARISH]

    # Liquidity
    liq_zones = detect_liquidity_zones(df_ltf, ms.swing_highs, ms.swing_lows)

    # Sinyal skoru
    signal = None
    score = 0
    reasons = []
    direction = None

    if htf.allows_long():
        score = 1
        reasons = ["HTF Bullish"]
        direction = "LONG"

        near_ob = next((o for o in bullish_obs if abs(current_price - o.midpoint) / current_price < 0.01), None)
        if near_ob:
            score += 1
            reasons.append("Bullish OB")

        near_fvg = next((f for f in bullish_fvgs if f.contains_price(current_price)), None)
        if near_fvg:
            score += 1
            reasons.append("Bullish FVG")

        for zone in liq_zones:
            if zone.liq_type == LiquidityType.SELLSIDE:
                if check_liquidity_sweep(df_ltf, zone, lookback_candles=3):
                    score += 1
                    reasons.append("Sellside Sweep")
                    break

    elif htf.allows_short():
        score = 1
        reasons = ["HTF Bearish"]
        direction = "SHORT"

        near_ob = next((o for o in bearish_obs if abs(current_price - o.midpoint) / current_price < 0.01), None)
        if near_ob:
            score += 1
            reasons.append("Bearish OB")

        near_fvg = next((f for f in bearish_fvgs if f.contains_price(current_price)), None)
        if near_fvg:
            score += 1
            reasons.append("Bearish FVG")

        for zone in liq_zones:
            if zone.liq_type == LiquidityType.BUYSIDE:
                if check_liquidity_sweep(df_ltf, zone, lookback_candles=3):
                    score += 1
                    reasons.append("Buyside Sweep")
                    break

    if direction and score >= 2:
        sl_dist = atr * 1.5
        if direction == "LONG":
            sl = current_price - sl_dist
            tp = current_price + sl_dist * 2.0
        else:
            sl = current_price + sl_dist
            tp = current_price - sl_dist * 2.0

        rr = round(abs(tp - current_price) / abs(sl - current_price), 1)

        signal = {
            "symbol": symbol,
            "direction": direction,
            "price": round(current_price, 4),
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "rr": rr,
            "score": score,
            "reasons": reasons,
            "time": datetime.now(timezone.utc).strftime("%H:%M")
        }

    return {
        "symbol": symbol,
        "price": round(current_price, 4),
        "bias": htf.bias.value,
        "zone": htf.price_zone.value,
        "ltf_bias": ms.bias.value,
        "atr": round(atr, 4),
        "bullish_obs": [{"top": round(o.top, 4), "bottom": round(o.bottom, 4)} for o in bullish_obs[-3:]],
        "bearish_obs": [{"top": round(o.top, 4), "bottom": round(o.bottom, 4)} for o in bearish_obs[-3:]],
        "bullish_fvgs": [{"top": round(f.top, 4), "bottom": round(f.bottom, 4)} for f in bullish_fvgs[-3:]],
        "bearish_fvgs": [{"top": round(f.top, 4), "bottom": round(f.bottom, 4)} for f in bearish_fvgs[-3:]],
        "signal": signal
    }


# ── Periyodik güncelleme ─────────────────────────────────────────────────────

def run_analysis():
    logger.info("Analiz başlıyor...")
    new_signals = []
    new_bias = {}
    new_obs = {}
    new_fvgs = {}

    for symbol in SYMBOLS:
        try:
            result = analyze_symbol(symbol)
            if not result:
                continue

            new_bias[symbol] = {
                "bias": result["bias"],
                "zone": result["zone"],
                "ltf_bias": result["ltf_bias"],
                "price": result["price"]
            }

            new_obs[symbol] = {
                "bullish": result["bullish_obs"],
                "bearish": result["bearish_obs"]
            }

            new_fvgs[symbol] = {
                "bullish": result["bullish_fvgs"],
                "bearish": result["bearish_fvgs"]
            }

            if result.get("signal"):
                # Aynı sembol zaten listede varsa güncelle
                new_signals = [s for s in state["signals"] if s["symbol"] != symbol]
                new_signals.append(result["signal"])
                state["signals"] = new_signals[-20:]

            time.sleep(0.5)

        except Exception as e:
            logger.error(f"{symbol} analiz hatası: {e}")

    state["bias"] = new_bias
    state["order_blocks"] = new_obs
    state["fvgs"] = new_fvgs
    state["last_update"] = datetime.now(timezone.utc).strftime("%H:%M:%S")

    # WebSocket ile tüm bağlı clientlara bildir
    socketio.emit("update", {
        "signals": state["signals"],
        "bias": state["bias"],
        "order_blocks": state["order_blocks"],
        "stats": state["stats"],
        "last_update": state["last_update"]
    })
    logger.info(f"Analiz tamamlandı. {len(state['signals'])} aktif sinyal.")


# ── API Endpoint'leri ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def get_state():
    return jsonify({
        "signals": state["signals"],
        "bias": state["bias"],
        "order_blocks": state["order_blocks"],
        "fvgs": state["fvgs"],
        "stats": state["stats"],
        "last_update": state["last_update"],
        "symbols": SYMBOLS
    })


@app.route("/api/signals")
def get_signals():
    return jsonify(state["signals"])


@app.route("/api/bias")
def get_bias():
    return jsonify(state["bias"])


@app.route("/api/trades")
def get_trades():
    return jsonify(state["trades"][-50:])


@app.route("/api/analyze/<symbol>")
def analyze_single(symbol):
    result = analyze_symbol(symbol.upper())
    return jsonify(result)


@app.route("/api/price/<symbol>")
def get_price(symbol):
    price = fetch_price(symbol.upper())
    return jsonify({"symbol": symbol.upper(), "price": price})


# ── SocketIO ─────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("update", {
        "signals": state["signals"],
        "bias": state["bias"],
        "order_blocks": state["order_blocks"],
        "stats": state["stats"],
        "last_update": state["last_update"]
    })


@socketio.on("request_analysis")
def on_request(data):
    symbol = data.get("symbol", "BTCUSDT").upper()
    result = analyze_symbol(symbol)
    emit("symbol_analysis", result)


# ── Başlatma ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("SMC Web Dashboard başlatılıyor...")

    # İlk analizi hemen çalıştır
    threading.Thread(target=run_analysis, daemon=True).start()

    # Her 15 dakikada otomatik güncelle
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_analysis, "interval", minutes=15, id="smc_analysis")
    scheduler.start()

    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
