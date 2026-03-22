"""
strategy/smc_signal.py — Tüm SMC konseptlerini birleştirir ve sinyal üretir.
Pipeline: HTF bias → Market structure → OB → FVG → Liq sweep → Confluence skoru → Karar
"""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from core.market_structure import analyze_market_structure, Bias
from core.order_blocks import detect_order_blocks, find_nearest_ob, OBType, OrderBlock
from core.fair_value_gap import detect_fvg, FVGType, FairValueGap, find_overlapping_fvg_ob
from core.liquidity import detect_liquidity_zones, check_liquidity_sweep, LiquidityType
from core.htf_bias import analyze_htf_bias, is_session_active, PriceZone
from core.risk_manager import build_trade_setup, TradeSetup


@dataclass
class SMCSignal:
    symbol: str
    direction: str            # "long" | "short"
    confluence_score: int     # Kaç SMC katmanı onayladı
    confluence_reasons: list[str] = field(default_factory=list)
    setup: Optional[TradeSetup] = None

    # Detaylar
    htf_bias: str = ""
    active_ob: Optional[OrderBlock] = None
    active_fvg: Optional[FairValueGap] = None
    liq_swept: bool = False

    @property
    def is_valid(self) -> bool:
        return self.confluence_score >= 2 and self.setup is not None


def generate_signal(
    symbol: str,
    df_ltf: pd.DataFrame,     # Entry timeframe (15m)
    df_htf: pd.DataFrame,     # Bias timeframe (4H)
    account_balance: float,
    settings,
    now: pd.Timestamp = None
) -> Optional[SMCSignal]:
    """
    Ana sinyal üretici.
    Her mum kapanışında çağrılır.
    None döndürürse trade yok.
    """
    if now is None:
        now = df_ltf.index[-1]

    # 1. Seans filtresi
    if not is_session_active(now, session="london_ny"):
        return None

    # 2. HTF Bias
    htf = analyze_htf_bias(df_htf, lookback_swing=settings.SWING_LOOKBACK)

    if htf.bias == Bias.NEUTRAL:
        return None

    # 3. LTF market structure
    ms_ltf = analyze_market_structure(df_ltf, lookback=settings.SWING_LOOKBACK)

    # 4. Order blocks
    obs = detect_order_blocks(df_ltf, lookback=settings.OB_LOOKBACK)

    # 5. FVG
    fvgs = detect_fvg(df_ltf, min_size_pct=settings.FVG_MIN_SIZE)

    # 6. Liquidity zones
    liq_zones = detect_liquidity_zones(
        df_ltf,
        ms_ltf.swing_highs,
        ms_ltf.swing_lows,
        tolerance_pct=settings.LIQUIDITY_TOLERANCE
    )

    current_price = df_ltf["close"].iloc[-1]

    # --- LONG sinyali kontrolü ---
    if htf.allows_long() and ms_ltf.bias == Bias.BULLISH:
        signal = _check_long_setup(
            symbol, current_price, obs, fvgs, liq_zones,
            htf, df_ltf, account_balance, settings, now
        )
        if signal and signal.is_valid:
            return signal

    # --- SHORT sinyali kontrolü ---
    if htf.allows_short() and ms_ltf.bias == Bias.BEARISH:
        signal = _check_short_setup(
            symbol, current_price, obs, fvgs, liq_zones,
            htf, df_ltf, account_balance, settings, now
        )
        if signal and signal.is_valid:
            return signal

    return None


def _check_long_setup(
    symbol, price, obs, fvgs, liq_zones, htf, df, balance, settings, now
) -> Optional[SMCSignal]:
    """Long için confluence kontrolü."""
    score = 0
    reasons = []
    active_ob = None
    active_fvg = None
    liq_swept = False

    # HTF bias onayı
    score += 1
    reasons.append(f"HTF bullish bias (zone: {htf.price_zone.value})")

    # Bullish OB'a yakın mı?
    ob = find_nearest_ob(price, obs, OBType.BULLISH, max_distance_pct=0.005)
    if ob:
        score += 1
        reasons.append(f"Bullish OB @ {ob.bottom:.4f}-{ob.top:.4f}")
        active_ob = ob

    # Bullish FVG var mı yakında?
    for fvg in fvgs:
        if fvg.fvg_type == FVGType.BULLISH and fvg.contains_price(price):
            score += 1
            reasons.append(f"Bullish FVG @ {fvg.bottom:.4f}-{fvg.top:.4f}")
            active_fvg = fvg

            # OB + FVG örtüşüyor mu? Extra puan
            if active_ob and find_overlapping_fvg_ob(fvg, active_ob.top, active_ob.bottom):
                score += 1
                reasons.append("OB + FVG confluence!")
            break

    # Sellside liquidity sweep oldu mu? (Stop avı yapılıp geri döndü mü)
    for zone in liq_zones:
        if zone.liq_type == LiquidityType.SELLSIDE:
            if check_liquidity_sweep(df, zone, lookback_candles=3):
                score += 1
                reasons.append(f"Sellside liq sweep @ {zone.price:.4f}")
                liq_swept = True
                break

    if score < settings.MIN_CONFLUENCE:
        return None

    # Trade setup oluştur
    entry = active_ob.midpoint if active_ob else price
    setup = build_trade_setup(
        symbol=symbol,
        direction="long",
        entry_price=entry,
        df=df,
        account_balance=balance,
        risk_pct=settings.RISK_PER_TRADE,
        atr_multiplier=settings.ATR_SL_MULTIPLIER,
        min_rr=settings.MIN_RR,
        confluence_score=score / 5.0
    )

    return SMCSignal(
        symbol=symbol,
        direction="long",
        confluence_score=score,
        confluence_reasons=reasons,
        setup=setup,
        htf_bias="bullish",
        active_ob=active_ob,
        active_fvg=active_fvg,
        liq_swept=liq_swept
    )


def _check_short_setup(
    symbol, price, obs, fvgs, liq_zones, htf, df, balance, settings, now
) -> Optional[SMCSignal]:
    """Short için confluence kontrolü."""
    score = 0
    reasons = []
    active_ob = None
    active_fvg = None
    liq_swept = False

    score += 1
    reasons.append(f"HTF bearish bias (zone: {htf.price_zone.value})")

    ob = find_nearest_ob(price, obs, OBType.BEARISH, max_distance_pct=0.005)
    if ob:
        score += 1
        reasons.append(f"Bearish OB @ {ob.bottom:.4f}-{ob.top:.4f}")
        active_ob = ob

    for fvg in fvgs:
        if fvg.fvg_type == FVGType.BEARISH and fvg.contains_price(price):
            score += 1
            reasons.append(f"Bearish FVG @ {fvg.bottom:.4f}-{fvg.top:.4f}")
            active_fvg = fvg
            if active_ob and find_overlapping_fvg_ob(fvg, active_ob.top, active_ob.bottom):
                score += 1
                reasons.append("OB + FVG confluence!")
            break

    for zone in liq_zones:
        if zone.liq_type == LiquidityType.BUYSIDE:
            if check_liquidity_sweep(df, zone, lookback_candles=3):
                score += 1
                reasons.append(f"Buyside liq sweep @ {zone.price:.4f}")
                liq_swept = True
                break

    if score < settings.MIN_CONFLUENCE:
        return None

    entry = active_ob.midpoint if active_ob else price
    setup = build_trade_setup(
        symbol=symbol,
        direction="short",
        entry_price=entry,
        df=df,
        account_balance=balance,
        risk_pct=settings.RISK_PER_TRADE,
        atr_multiplier=settings.ATR_SL_MULTIPLIER,
        min_rr=settings.MIN_RR,
        confluence_score=score / 5.0
    )

    return SMCSignal(
        symbol=symbol,
        direction="short",
        confluence_score=score,
        confluence_reasons=reasons,
        setup=setup,
        htf_bias="bearish",
        active_ob=active_ob,
        active_fvg=active_fvg,
        liq_swept=liq_swept
    )
