"""
config/settings.py — Merkezi ayar yönetimi
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # API
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    TESTNET: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Trade
    TRADE_MODE: str = os.getenv("TRADE_MODE", "paper")
    MAX_OPEN_POSITIONS: int = int(os.getenv("MAX_OPEN_POSITIONS", 3))
    RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE", 0.01))
    MAX_DAILY_LOSS: float = float(os.getenv("MAX_DAILY_LOSS", 0.03))

    # Symbols & timeframes
    SYMBOLS: list = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
    HTF: str = os.getenv("HTF", "4h")
    LTF: str = os.getenv("LTF", "15m")

    # SMC parametreleri
    SWING_LOOKBACK: int = 10          # Swing high/low tespiti için kaç mum bakılır
    OB_LOOKBACK: int = 50             # Order block arama penceresi
    FVG_MIN_SIZE: float = 0.0005      # Min FVG büyüklüğü (fiyatın %0.05'i)
    LIQUIDITY_TOLERANCE: float = 0.002 # Liquidity zone eşleşme toleransı (%0.2)
    MIN_RR: float = 2.0               # Minimum risk/reward oranı
    ATR_SL_MULTIPLIER: float = 1.5    # SL = ATR × bu çarpan
    ATR_PERIOD: int = 14

    # Confluences — kaç tane SMC sinyali üst üste gelmeli?
    MIN_CONFLUENCE: int = 2           # OB + FVG = 2, OB + FVG + Liq = 3 gibi

    @property
    def is_live(self) -> bool:
        return self.TRADE_MODE == "live"

    @property
    def is_paper(self) -> bool:
        return self.TRADE_MODE == "paper"


settings = Settings()
