"""
core/risk_manager.py — Pozisyon büyüklüğü ve risk kontrolü
Her trade sabit risk yüzdesi ile açılır. Hesap korunur.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np


@dataclass
class TradeSetup:
    symbol: str
    direction: str          # "long" | "short"
    entry_price: float
    stop_loss: float
    take_profit_1: float    # %50 kapatma
    take_profit_2: float    # %50 kapatma veya trailing
    position_size: float    # USDT cinsinden
    quantity: float         # Coin miktarı
    risk_amount: float      # Bu trade'de riske atılan USDT
    rr_ratio: float         # Risk/Reward oranı
    confidence: float       # 0-1 arası confluence skoru


@dataclass
class RiskState:
    """Günlük ve anlık risk durumu takibi."""
    account_balance: float
    daily_pnl: float = 0.0
    open_positions: int = 0
    daily_trades: int = 0
    max_daily_loss_hit: bool = False
    consecutive_losses: int = 0


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """ATR (Average True Range) hesapla."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]


def calculate_position_size(
    account_balance: float,
    entry_price: float,
    stop_loss: float,
    risk_pct: float = 0.01
) -> tuple[float, float]:
    """
    Sabit risk yüzdesi ile pozisyon büyüklüğü hesapla.

    Dönüş: (usdt_miktarı, coin_miktarı)
    """
    risk_amount = account_balance * risk_pct
    sl_distance = abs(entry_price - stop_loss)

    if sl_distance == 0:
        return 0.0, 0.0

    quantity = risk_amount / sl_distance
    usdt_size = quantity * entry_price
    return usdt_size, quantity


def build_trade_setup(
    symbol: str,
    direction: str,
    entry_price: float,
    df: pd.DataFrame,
    account_balance: float,
    risk_pct: float = 0.01,
    atr_multiplier: float = 1.5,
    min_rr: float = 2.0,
    confluence_score: float = 0.5
) -> Optional[TradeSetup]:
    """
    ATR'dan SL hesapla, SL/RR'den TP hesapla, pozisyon büyüklüğü belirle.
    Minimum RR sağlanmıyorsa None döndür.
    """
    atr = calculate_atr(df)
    sl_distance = atr * atr_multiplier

    if direction == "long":
        stop_loss = entry_price - sl_distance
        take_profit_1 = entry_price + sl_distance * min_rr * 0.6   # İlk TP
        take_profit_2 = entry_price + sl_distance * min_rr          # İkinci TP
    elif direction == "short":
        stop_loss = entry_price + sl_distance
        take_profit_1 = entry_price - sl_distance * min_rr * 0.6
        take_profit_2 = entry_price - sl_distance * min_rr
    else:
        return None

    # RR kontrolü
    rr = abs(entry_price - take_profit_2) / abs(entry_price - stop_loss)
    if rr < min_rr:
        return None

    usdt_size, quantity = calculate_position_size(
        account_balance, entry_price, stop_loss, risk_pct
    )

    risk_amount = account_balance * risk_pct

    return TradeSetup(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        position_size=usdt_size,
        quantity=round(quantity, 6),
        risk_amount=risk_amount,
        rr_ratio=rr,
        confidence=confluence_score
    )


def check_risk_limits(state: RiskState, settings) -> tuple[bool, str]:
    """
    Trade açmadan önce tüm risk limitlerini kontrol eder.
    Dönüş: (izin_var_mı, red_sebebi)
    """
    # Günlük kayıp limiti
    if state.max_daily_loss_hit:
        return False, "Günlük max kayıp limitine ulaşıldı"

    max_daily_loss = state.account_balance * settings.MAX_DAILY_LOSS
    if state.daily_pnl < -max_daily_loss:
        state.max_daily_loss_hit = True
        return False, f"Günlük kayıp limiti aşıldı: {state.daily_pnl:.2f} USDT"

    # Max açık pozisyon
    if state.open_positions >= settings.MAX_OPEN_POSITIONS:
        return False, f"Max açık pozisyon sayısına ulaşıldı: {settings.MAX_OPEN_POSITIONS}"

    # Ardışık kayıp koruması (4 üst üste kayıp = dur)
    if state.consecutive_losses >= 4:
        return False, "4 ardışık kayıp — gün içi trading durdu"

    return True, "ok"


def update_trailing_stop(
    current_price: float,
    direction: str,
    original_stop: float,
    atr: float,
    atr_multiplier: float = 1.0
) -> float:
    """
    Trailing stop güncelleme.
    Long: fiyat yükselince SL de yükselir.
    Short: fiyat düşünce SL de düşer.
    """
    trail_distance = atr * atr_multiplier

    if direction == "long":
        new_stop = current_price - trail_distance
        return max(new_stop, original_stop)  # Sadece yukarı hareket eder

    elif direction == "short":
        new_stop = current_price + trail_distance
        return min(new_stop, original_stop)  # Sadece aşağı hareket eder

    return original_stop
