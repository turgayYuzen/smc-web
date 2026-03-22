"""
core/market_structure.py — BOS / CHoCH / Swing tespiti
Smart Money Concept'te her şey market structure'dan başlar.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import pandas as pd
import numpy as np


class Bias(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class StructureEvent(Enum):
    BOS_BULLISH = "bos_bullish"      # Break of Structure — trend devam (yukarı)
    BOS_BEARISH = "bos_bearish"      # Break of Structure — trend devam (aşağı)
    CHOCH_BULLISH = "choch_bullish"  # Change of Character — dönüş (yukarı)
    CHOCH_BEARISH = "choch_bearish"  # Change of Character — dönüş (aşağı)


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: str          # "high" | "low"
    timestamp: pd.Timestamp


@dataclass
class StructureBreak:
    event: StructureEvent
    price: float       # kırılan seviye
    candle_index: int
    timestamp: pd.Timestamp
    confirmed: bool = False


@dataclass
class MarketStructure:
    bias: Bias = Bias.NEUTRAL
    swing_highs: list = field(default_factory=list)
    swing_lows: list = field(default_factory=list)
    last_hh: Optional[float] = None    # Higher High
    last_hl: Optional[float] = None    # Higher Low
    last_lh: Optional[float] = None    # Lower High
    last_ll: Optional[float] = None    # Lower Low
    recent_breaks: list = field(default_factory=list)


def detect_swing_points(df: pd.DataFrame, lookback: int = 10) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """
    Pivot-based swing high/low tespiti.
    df kolonları: open, high, low, close, volume + timestamp index
    """
    highs, lows = [], []
    n = len(df)

    for i in range(lookback, n - lookback):
        # Swing High: sağa ve sola lookback kadar en yüksek
        if df["high"].iloc[i] == df["high"].iloc[i - lookback:i + lookback + 1].max():
            highs.append(SwingPoint(
                index=i,
                price=df["high"].iloc[i],
                kind="high",
                timestamp=df.index[i]
            ))
        # Swing Low
        if df["low"].iloc[i] == df["low"].iloc[i - lookback:i + lookback + 1].min():
            lows.append(SwingPoint(
                index=i,
                price=df["low"].iloc[i],
                kind="low",
                timestamp=df.index[i]
            ))

    return highs, lows


def analyze_market_structure(df: pd.DataFrame, lookback: int = 10) -> MarketStructure:
    """
    Swing noktalarından HH/HL/LH/LL zinciri kurar,
    BOS ve CHoCH olaylarını tespit eder.
    """
    ms = MarketStructure()
    swing_highs, swing_lows = detect_swing_points(df, lookback)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return ms

    ms.swing_highs = swing_highs
    ms.swing_lows = swing_lows

    # Son 4 swing noktasından yapıyı oku
    recent_highs = swing_highs[-4:]
    recent_lows = swing_lows[-4:]

    # Bias belirleme: son iki swing high ve low karşılaştırması
    if len(recent_highs) >= 2 and len(recent_lows) >= 2:
        hh = recent_highs[-1].price > recent_highs[-2].price
        hl = recent_lows[-1].price > recent_lows[-2].price
        lh = recent_highs[-1].price < recent_highs[-2].price
        ll = recent_lows[-1].price < recent_lows[-2].price

        if hh and hl:
            ms.bias = Bias.BULLISH
            ms.last_hh = recent_highs[-1].price
            ms.last_hl = recent_lows[-1].price
        elif lh and ll:
            ms.bias = Bias.BEARISH
            ms.last_lh = recent_highs[-1].price
            ms.last_ll = recent_lows[-1].price

    # BOS / CHoCH tespiti (son mumlar üzerinde)
    close = df["close"]
    for i in range(lookback * 2, len(df)):
        current_close = close.iloc[i]

        # Bullish BOS: bullish bias'ta son HH kırıldı
        if ms.bias == Bias.BULLISH and ms.last_hh and current_close > ms.last_hh:
            ms.recent_breaks.append(StructureBreak(
                event=StructureEvent.BOS_BULLISH,
                price=ms.last_hh,
                candle_index=i,
                timestamp=df.index[i],
                confirmed=True
            ))

        # Bearish BOS
        elif ms.bias == Bias.BEARISH and ms.last_ll and current_close < ms.last_ll:
            ms.recent_breaks.append(StructureBreak(
                event=StructureEvent.BOS_BEARISH,
                price=ms.last_ll,
                candle_index=i,
                timestamp=df.index[i],
                confirmed=True
            ))

        # CHoCH: Bullish trend'de HL kırılırsa dönüş sinyali
        if ms.bias == Bias.BULLISH and ms.last_hl and current_close < ms.last_hl:
            ms.recent_breaks.append(StructureBreak(
                event=StructureEvent.CHOCH_BEARISH,
                price=ms.last_hl,
                candle_index=i,
                timestamp=df.index[i],
                confirmed=True
            ))
            ms.bias = Bias.BEARISH  # Bias güncelle

        # CHoCH: Bearish trend'de LH kırılırsa dönüş sinyali
        elif ms.bias == Bias.BEARISH and ms.last_lh and current_close > ms.last_lh:
            ms.recent_breaks.append(StructureBreak(
                event=StructureEvent.CHOCH_BULLISH,
                price=ms.last_lh,
                candle_index=i,
                timestamp=df.index[i],
                confirmed=True
            ))
            ms.bias = Bias.BULLISH

    # Son 10 kırılmayı tut
    ms.recent_breaks = ms.recent_breaks[-10:]
    return ms
