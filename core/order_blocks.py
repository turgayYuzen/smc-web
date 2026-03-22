"""
core/order_blocks.py — Kurumsal Order Block tespiti
Büyük bir hareketten önceki son karşı yönlü mum = order block.
Fiyat geri geldiğinde buradan limit emir açılır.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import pandas as pd
import numpy as np


class OBType(Enum):
    BULLISH = "bullish"   # Alış order block (destek)
    BEARISH = "bearish"   # Satış order block (direnç)


class OBStatus(Enum):
    ACTIVE = "active"         # Henüz test edilmedi
    TESTED = "tested"         # Bir kez ziyaret edildi
    MITIGATED = "mitigated"   # İçinden geçildi, geçersiz
    BREACHED = "breached"     # Tamamen kırıldı


@dataclass
class OrderBlock:
    ob_type: OBType
    top: float              # Kutunun üst kenarı
    bottom: float           # Kutunun alt kenarı
    origin_index: int       # Hangi mumdan oluştu
    origin_time: pd.Timestamp
    status: OBStatus = OBStatus.ACTIVE
    strength: float = 1.0   # OB'dan çıkan hareketin büyüklüğü (puan olarak)
    confluence_score: int = 0  # FVG/Liq gibi ek onaylar ekledikçe artar

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains_price(self, price: float, tolerance: float = 0.0) -> bool:
        return (self.bottom - tolerance) <= price <= (self.top + tolerance)

    def is_touched(self, low: float, high: float) -> bool:
        """Mum OB kutusuna girdi mi?"""
        return low <= self.top and high >= self.bottom


def detect_order_blocks(df: pd.DataFrame, lookback: int = 50) -> list[OrderBlock]:
    """
    Son `lookback` mum içinde order block tespiti yapar.

    Algoritma:
    1. Güçlü yukarı hareketi bul (bullish OB öncesindeki son bearish mum)
    2. Güçlü aşağı hareketi bul (bearish OB öncesindeki son bullish mum)
    3. OB hala aktif mi kontrol et (fiyat içinden geçmediyse)
    """
    obs: list[OrderBlock] = []
    window = df.tail(lookback).reset_index()

    for i in range(3, len(window) - 1):
        o = window["open"].iloc[i]
        h = window["high"].iloc[i]
        l = window["low"].iloc[i]
        c = window["close"].iloc[i]
        ts = window["timestamp"].iloc[i] if "timestamp" in window.columns else window.index[i]

        # --- Bullish OB ---
        # Bu mum bearish (kırmızı), sonraki mumlar güçlü yukarı gidiyorsa
        is_bearish_candle = c < o
        if is_bearish_candle:
            # Sonraki 3 mum içinde güçlü yukarı hareket var mı?
            future = window.iloc[i + 1: i + 4]
            if len(future) >= 1:
                max_future_close = future["close"].max()
                move_pct = (max_future_close - h) / h
                if move_pct > 0.003:  # en az %0.3 yukarı hareket
                    ob = OrderBlock(
                        ob_type=OBType.BULLISH,
                        top=o,      # Bearish mumun open'ı üst kenar
                        bottom=l,   # Low alt kenar
                        origin_index=i,
                        origin_time=ts,
                        strength=move_pct * 100
                    )
                    # Fiyat OB içinden geçti mi? (geçtiyse geçersiz)
                    future_lows = window.iloc[i + 1:]["low"]
                    if not any(future_lows < l):  # Alt kenarı kırmadıysa aktif
                        obs.append(ob)

        # --- Bearish OB ---
        # Bu mum bullish (yeşil), sonraki mumlar güçlü aşağı gidiyorsa
        is_bullish_candle = c > o
        if is_bullish_candle:
            future = window.iloc[i + 1: i + 4]
            if len(future) >= 1:
                min_future_close = future["close"].min()
                move_pct = (o - min_future_close) / o
                if move_pct > 0.003:
                    ob = OrderBlock(
                        ob_type=OBType.BEARISH,
                        top=h,      # High üst kenar
                        bottom=o,   # Bullish mumun open'ı alt kenar
                        origin_index=i,
                        origin_time=ts,
                        strength=move_pct * 100
                    )
                    future_highs = window.iloc[i + 1:]["high"]
                    if not any(future_highs > h):
                        obs.append(ob)

    return _update_ob_statuses(obs, df)


def _update_ob_statuses(obs: list[OrderBlock], df: pd.DataFrame) -> list[OrderBlock]:
    """
    Mevcut fiyat hareketlerine göre OB durumlarını günceller.
    Kırılmış OB'lar listeden çıkarılır.
    """
    if df.empty or not obs:
        return obs

    current_close = df["close"].iloc[-1]
    active_obs = []

    for ob in obs:
        if ob.ob_type == OBType.BULLISH:
            # Alt kenarın altına kapandıysa kırılmış
            if current_close < ob.bottom:
                ob.status = OBStatus.BREACHED
            elif ob.contains_price(current_close):
                ob.status = OBStatus.TESTED
            else:
                active_obs.append(ob)
                continue
        elif ob.ob_type == OBType.BEARISH:
            # Üst kenarın üstüne kapandıysa kırılmış
            if current_close > ob.top:
                ob.status = OBStatus.BREACHED
            elif ob.contains_price(current_close):
                ob.status = OBStatus.TESTED
            else:
                active_obs.append(ob)
                continue

        if ob.status != OBStatus.BREACHED:
            active_obs.append(ob)

    return active_obs


def find_nearest_ob(price: float, obs: list[OrderBlock], ob_type: OBType, max_distance_pct: float = 0.02) -> Optional[OrderBlock]:
    """
    Verilen fiyata en yakın aktif OB'u bulur.
    max_distance_pct: fiyatın %kaçı uzaklıkta arar
    """
    candidates = [ob for ob in obs if ob.ob_type == ob_type and ob.status == OBStatus.ACTIVE]
    if not candidates:
        return None

    best = None
    best_dist = float("inf")

    for ob in candidates:
        dist = abs(price - ob.midpoint) / price
        if dist < best_dist and dist <= max_distance_pct:
            best_dist = dist
            best = ob

    return best
