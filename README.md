# SMC Web Dashboard

SMC botunun web arayüzü. Flask + WebSocket ile canlı sinyal takibi.

## Kurulum

```bash
cd smc_web

python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt
```

## Çalıştırma

```bash
python app.py
```

Tarayıcıda aç: **http://localhost:5000**

## Özellikler

- Canlı SMC analizi (her 15 dakika otomatik güncelleme)
- 5 sembol takibi: BTC, ETH, SOL, BNB, XRP
- HTF bias + Order Block + FVG + Liquidity sweep
- WebSocket ile anlık güncelleme (sayfa yenilemeye gerek yok)
- Light/dark mode otomatik

## Deployment (Railway)

1. GitHub'a yükle
2. railway.app → New Project → GitHub repo seç
3. Otomatik deploy olur
4. Ücretsiz plan yeterli başlangıç için

## Klasör Yapısı

```
smc_web/
├── app.py              # Flask + SocketIO backend
├── requirements.txt
├── core/               # SMC analiz motoru (smc_bot'tan kopyalandı)
├── strategy/
├── config/
├── templates/
│   └── index.html      # Ana dashboard
└── static/
    ├── css/style.css   # Tüm stiller
    └── js/dashboard.js # WebSocket + rendering
```
