"""
core/fair_value_gap.py — FVG / İmbalance tespiti
3 mumlu formasyonda ortanın gölgelerinin örtüşmediği bölge = FVG.
Kurumlar bu boşlukları kapatmaya gelir.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pandas as pd


class FVGType(Enum):
    BULLISH = "bullish"   # Yukarı FVG (destek görevi görür)
    BEARISH = "bearish"   # Aşağı FVG (direnç görevi görür)


class FVGStatus(Enum):
    OPEN = "open"           # Henüz kapatılmadı
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"       # Tamamen kapatıldı


@dataclass
class FairValueGap:
    fvg_type: FVGType
    top: float
    bottom: float
    origin_index: int
    origin_time: pd.Timestamp
    status: FVGStatus = FVGStatus.OPEN
    fill_pct: float = 0.0   # Yüzde kaçı doldu

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains_price(self, price: float) -> bool:
        return self.bottom <= price <= self.top


def detect_fvg(df: pd.DataFrame, min_size_pct: float = 0.0005) -> list[FairValueGap]:
    """
    Üç mumlu FVG tespiti:
    - Bullish FVG: mum[i-2].high < mum[i].low → arada boşluk var
    - Bearish FVG: mum[i-2].low > mum[i].high → arada boşluk var

    min_size_pct: FVG'nin fiyata oranla minimum büyüklüğü
    """
    fvgs: list[FairValueGap] = []

    for i in range(2, len(df)):
        prev2_high = df["high"].iloc[i - 2]
        prev2_low = df["low"].iloc[i - 2]
        current_high = df["high"].iloc[i]
        current_low = df["low"].iloc[i]
        mid_close = df["close"].iloc[i - 1]
        ts = df.index[i - 1]  # Ortadaki mumun zamanı = FVG'nin zamanı

        # Bullish FVG: önceki mumun high'ı < mevcut mumun low'u
        if prev2_high < current_low:
            gap_top = current_low
            gap_bottom = prev2_high
            gap_size = gap_top - gap_bottom
            if gap_size / mid_close >= min_size_pct:
                fvgs.append(FairValueGap(
                    fvg_type=FVGType.BULLISH,
                    top=gap_top,
                    bottom=gap_bottom,
                    origin_index=i - 1,
                    origin_time=ts
                ))

        # Bearish FVG: önceki mumun low'u > mevcut mumun high'ı
        elif prev2_low > current_high:
            gap_top = prev2_low
            gap_bottom = current_high
            gap_size = gap_top - gap_bottom
            if gap_size / mid_close >= min_size_pct:
                fvgs.append(FairValueGap(
                    fvg_type=FVGType.BEARISH,
                    top=gap_top,
                    bottom=gap_bottom,
                    origin_index=i - 1,
                    origin_time=ts
                ))

    return _update_fvg_statuses(fvgs, df)


def _update_fvg_statuses(fvgs: list[FairValueGap], df: pd.DataFrame) -> list[FairValueGap]:
    """FVG'lerin dolma durumunu günceller."""
    open_fvgs = []

    for fvg in fvgs:
        # FVG oluştuktan sonraki mumları kontrol et
        future_df = df.iloc[fvg.origin_index + 1:]

        if future_df.empty:
            open_fvgs.append(fvg)
            continue

        if fvg.fvg_type == FVGType.BULLISH:
            # Fiyat FVG'nin altına indi mi?
            min_low = future_df["low"].min()
            if min_low <= fvg.bottom:
                fvg.status = FVGStatus.FILLED
                fvg.fill_pct = 100.0
            elif min_low <= fvg.midpoint:
                fvg.status = FVGStatus.PARTIALLY_FILLED
                fvg.fill_pct = (fvg.top - min_low) / fvg.size * 100

        elif fvg.fvg_type == FVGType.BEARISH:
            # Fiyat FVG'nin üstüne çıktı mı?
            max_high = future_df["high"].max()
            if max_high >= fvg.top:
                fvg.status = FVGStatus.FILLED
                fvg.fill_pct = 100.0
            elif max_high >= fvg.midpoint:
                fvg.status = FVGStatus.PARTIALLY_FILLED
                fvg.fill_pct = (max_high - fvg.bottom) / fvg.size * 100

        # Sadece açık olanları sakla
        if fvg.status != FVGStatus.FILLED:
            open_fvgs.append(fvg)

    return open_fvgs


def find_overlapping_fvg_ob(fvg: FairValueGap, top_ob: float, bottom_ob: float) -> bool:
    """
    FVG ile Order Block örtüşüyor mu?
    Bu örtüşme = çok güçlü confluence bölgesi.
    """
    return not (fvg.top < bottom_ob or fvg.bottom > top_ob)
