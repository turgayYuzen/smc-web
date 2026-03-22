"""
core/htf_bias.py — Higher Timeframe Bias + Premium/Discount bölgeleri
Sadece HTF yönüne uygun trade'ler açılır.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pandas as pd

from core.market_structure import analyze_market_structure, Bias


class PriceZone(Enum):
    PREMIUM = "premium"       # Range'in üst yarısı — short için ideal
    EQUILIBRIUM = "equilibrium"  # Orta nokta
    DISCOUNT = "discount"     # Range'in alt yarısı — long için ideal


@dataclass
class HTFContext:
    bias: Bias
    price_zone: PriceZone
    range_high: float
    range_low: float
    equilibrium: float
    fib_levels: dict        # 0.5, 0.618, 0.705, 0.786 seviyeleri
    premium_threshold: float
    discount_threshold: float
    trend_strength: float   # 0-1 arası, 1 = çok güçlü trend

    def allows_long(self) -> bool:
        """Long için: bullish bias + discount zone"""
        return self.bias == Bias.BULLISH and self.price_zone == PriceZone.DISCOUNT

    def allows_short(self) -> bool:
        """Short için: bearish bias + premium zone"""
        return self.bias == Bias.BEARISH and self.price_zone == PriceZone.PREMIUM


def analyze_htf_bias(df_htf: pd.DataFrame, lookback_swing: int = 10) -> HTFContext:
    """
    HTF (4H/1D) verisiyle bias ve bölge analizi yapar.
    """
    ms = analyze_market_structure(df_htf, lookback=lookback_swing)

    # Range belirleme — son önemli swing high ve low
    highs = ms.swing_highs
    lows = ms.swing_lows

    if not highs or not lows:
        # Yetersiz veri — neutral döndür
        last_price = df_htf["close"].iloc[-1]
        return HTFContext(
            bias=Bias.NEUTRAL,
            price_zone=PriceZone.EQUILIBRIUM,
            range_high=last_price * 1.02,
            range_low=last_price * 0.98,
            equilibrium=last_price,
            fib_levels={},
            premium_threshold=last_price * 1.01,
            discount_threshold=last_price * 0.99,
            trend_strength=0.0
        )

    range_high = max(h.price for h in highs[-5:])
    range_low = min(l.price for l in lows[-5:])
    current_price = df_htf["close"].iloc[-1]

    # Fibonacci seviyeleri (range içinde)
    fib_levels = _calculate_fib_levels(range_high, range_low)
    eq = fib_levels[0.5]  # Equilibrium = %50 seviyesi

    # Premium / Discount eşiği
    premium_threshold = fib_levels[0.5]  # Üstü premium
    discount_threshold = fib_levels[0.5]  # Altı discount

    # Mevcut fiyatın bölgesini belirle
    if current_price > premium_threshold:
        zone = PriceZone.PREMIUM
    elif current_price < discount_threshold:
        zone = PriceZone.DISCOUNT
    else:
        zone = PriceZone.EQUILIBRIUM

    # Trend gücü: swing high/low değişim hızı
    trend_strength = _calculate_trend_strength(ms, range_high, range_low)

    return HTFContext(
        bias=ms.bias,
        price_zone=zone,
        range_high=range_high,
        range_low=range_low,
        equilibrium=eq,
        fib_levels=fib_levels,
        premium_threshold=premium_threshold,
        discount_threshold=discount_threshold,
        trend_strength=trend_strength
    )


def _calculate_fib_levels(high: float, low: float) -> dict:
    """
    Klasik fib retracement seviyeleri.
    Bullish için: low'dan high'a doğru.
    """
    diff = high - low
    return {
        0.0:   high,
        0.236: high - diff * 0.236,
        0.382: high - diff * 0.382,
        0.5:   high - diff * 0.5,
        0.618: high - diff * 0.618,
        0.705: high - diff * 0.705,
        0.786: high - diff * 0.786,
        1.0:   low
    }


def _calculate_trend_strength(ms, range_high: float, range_low: float) -> float:
    """
    Swing noktalarından trend momentumu tahmini. 0-1 arası döndürür.
    """
    if ms.bias == Bias.NEUTRAL:
        return 0.0

    # Son birkaç swing değişim büyüklüğü
    if ms.bias == Bias.BULLISH and ms.last_hh and ms.last_hl:
        progress = (ms.last_hh - ms.last_hl) / (range_high - range_low + 1e-9)
        return min(progress, 1.0)

    if ms.bias == Bias.BEARISH and ms.last_lh and ms.last_ll:
        progress = (ms.last_lh - ms.last_ll) / (range_high - range_low + 1e-9)
        return min(progress, 1.0)

    return 0.3


def is_session_active(timestamp: pd.Timestamp, session: str = "london_ny") -> bool:
    """
    Sadece aktif seans saatlerinde trade — boş saatlerde kurumsal hareket olmaz.
    London: 08:00-17:00 UTC
    New York: 13:00-22:00 UTC
    Asian Kill Zone: 00:00-04:00 UTC
    """
    hour = timestamp.hour

    sessions = {
        "london": (8, 17),
        "new_york": (13, 22),
        "asian": (0, 4),
        "london_ny": (8, 22),  # Overlap dahil
        "all": (0, 24)
    }

    start, end = sessions.get(session, (8, 22))
    return start <= hour < end
