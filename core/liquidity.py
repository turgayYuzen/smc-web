"""
core/liquidity.py — Liquidity zone tespiti
EQH / EQL ve swing stop cluster'ları — akıllı para bu seviyelere stop avı yapar.
"""
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np


class LiquidityType(Enum):
    BUYSIDE = "buyside"    # Yukarıda — swing high'ların üzerindeki stop'lar
    SELLSIDE = "sellside"  # Aşağıda — swing low'ların altındaki stop'lar


class LiquidityStatus(Enum):
    INTACT = "intact"       # Henüz süpürülmedi
    SWEPT = "swept"         # Süpürüldü (stop avı yapıldı)


@dataclass
class LiquidityZone:
    liq_type: LiquidityType
    price: float            # Likidite seviyesi
    cluster_count: int      # Kaç swing noktası bu bölgede kümelendi
    tolerance: float        # Eşleşme toleransı
    origin_time: pd.Timestamp
    status: LiquidityStatus = LiquidityStatus.INTACT

    @property
    def zone_top(self) -> float:
        return self.price + self.tolerance

    @property
    def zone_bottom(self) -> float:
        return self.price - self.tolerance


def detect_liquidity_zones(
    df: pd.DataFrame,
    swing_highs: list,
    swing_lows: list,
    tolerance_pct: float = 0.002
) -> list[LiquidityZone]:
    """
    Swing high/low kümelerinden likidite bölgeleri oluşturur.

    Eşit yüksekler (EQH) = buyside liquidity
    Eşit dipler (EQL) = sellside liquidity
    """
    zones: list[LiquidityZone] = []
    current_price = df["close"].iloc[-1]
    tolerance = current_price * tolerance_pct

    # --- Buyside Liquidity (EQH) ---
    high_prices = [s.price for s in swing_highs]
    high_clusters = _find_price_clusters(high_prices, tolerance)

    for cluster_price, count, members in high_clusters:
        if count >= 2:  # En az 2 swing aynı seviyede
            # En son swing'in zamanını al
            latest_swing = max(
                [s for s in swing_highs if abs(s.price - cluster_price) <= tolerance],
                key=lambda s: s.index
            )
            # Mevcut fiyatın üzerindeyse buyside liquidity
            if cluster_price > current_price:
                zone = LiquidityZone(
                    liq_type=LiquidityType.BUYSIDE,
                    price=cluster_price,
                    cluster_count=count,
                    tolerance=tolerance,
                    origin_time=latest_swing.timestamp
                )
                zones.append(zone)

    # --- Sellside Liquidity (EQL) ---
    low_prices = [s.price for s in swing_lows]
    low_clusters = _find_price_clusters(low_prices, tolerance)

    for cluster_price, count, members in low_clusters:
        if count >= 2:
            latest_swing = max(
                [s for s in swing_lows if abs(s.price - cluster_price) <= tolerance],
                key=lambda s: s.index
            )
            if cluster_price < current_price:
                zone = LiquidityZone(
                    liq_type=LiquidityType.SELLSIDE,
                    price=cluster_price,
                    cluster_count=count,
                    tolerance=tolerance,
                    origin_time=latest_swing.timestamp
                )
                zones.append(zone)

    return _update_liquidity_statuses(zones, df)


def _find_price_clusters(prices: list[float], tolerance: float) -> list[tuple]:
    """
    Birbirine yakın fiyatları kümelere ayırır.
    Döndürür: [(küme_merkezi, eleman_sayısı, elemanlar), ...]
    """
    if not prices:
        return []

    sorted_prices = sorted(prices)
    clusters = []
    used = [False] * len(sorted_prices)

    for i, price in enumerate(sorted_prices):
        if used[i]:
            continue
        cluster_members = [price]
        used[i] = True

        for j in range(i + 1, len(sorted_prices)):
            if not used[j] and abs(sorted_prices[j] - price) <= tolerance:
                cluster_members.append(sorted_prices[j])
                used[j] = True

        cluster_center = np.mean(cluster_members)
        clusters.append((cluster_center, len(cluster_members), cluster_members))

    return clusters


def _update_liquidity_statuses(zones: list[LiquidityZone], df: pd.DataFrame) -> list[LiquidityZone]:
    """Liquidity sweep kontrolü — fiyat zonu geçti mi?"""
    active_zones = []

    for zone in zones:
        if zone.liq_type == LiquidityType.BUYSIDE:
            # Fiyat bu seviyenin üzerine çıktı mı?
            if df["high"].max() > zone.zone_top:
                zone.status = LiquidityStatus.SWEPT
        elif zone.liq_type == LiquidityType.SELLSIDE:
            # Fiyat bu seviyenin altına indi mi?
            if df["low"].min() < zone.zone_bottom:
                zone.status = LiquidityStatus.SWEPT

        active_zones.append(zone)

    return active_zones


def check_liquidity_sweep(df: pd.DataFrame, zone: LiquidityZone, lookback_candles: int = 3) -> bool:
    """
    Son `lookback_candles` mumda likidite süpürüldü mü ve fiyat geri döndü mü?
    Bu = kurumsal el işareti.
    """
    recent = df.tail(lookback_candles)

    if zone.liq_type == LiquidityType.BUYSIDE:
        # Fiyat zone üstüne çıktı (sweep) ama close altında kapandı
        swept = any(recent["high"] > zone.zone_top)
        reversed_back = recent["close"].iloc[-1] < zone.price
        return swept and reversed_back

    elif zone.liq_type == LiquidityType.SELLSIDE:
        # Fiyat zone altına indi ama close üstünde kapandı
        swept = any(recent["low"] < zone.zone_bottom)
        reversed_back = recent["close"].iloc[-1] > zone.price
        return swept and reversed_back

    return False
