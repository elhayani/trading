# 🏛️ Trading Windows & Micro-Corridors Documentation
## Empire V5.1 - Adaptive Scalping System

Ce document décrit le système de filtrage temporel de l'Empire V5, composé de deux modules :
1. **Trading Windows** - Golden Windows par session
2. **Micro-Corridors** - Adaptation par tranche de 30-60 minutes

---

## 📊 Vue d'ensemble

### Principe
Le marché a une "personnalité" différente selon l'heure. Au lieu d'un seul set de paramètres pour toute la journée, on adapte :
- **TP/SL** : Plus courts en mode scalping (gains rapides)
- **Risk Multiplier** : Plus agressif pendant les fenêtres de haute liquidité
- **RSI Threshold** : Adaptatif selon le régime de marché

---

## 🎯 Micro-Corridors par Classe d'Actif

### 📈 INDICES (Nasdaq, S&P 500)

| Corridor | Horaires (Paris) | Régime | TP Mult | Risk Mult |
|----------|------------------|--------|---------|-----------|
| 💥 Impact Zone | 15:30 - 16:00 | AGGRESSIVE_BREAKOUT | 0.4x | 1.5x |
| 📉 First Pullback | 16:00 - 16:30 | PULLBACK_SNIPER | 0.5x | 1.2x |
| 🏛️ Institutional Flow | 16:30 - 18:00 | TREND_FOLLOWING | 0.6x | 1.0x |
| 🍔 US Lunch (Lull) | 18:00 - 19:00 | SCALPING | 0.3x | 0.8x |
| 🚀 Afternoon Push | 19:00 - 20:00 | TREND_FOLLOWING | 0.5x | 1.1x |
| 💰 Profit Taking | 20:00 - 21:00 | CAUTIOUS_REVERSAL | 0.4x | 0.7x |
| 🔚 Final Hour | 21:00 - 22:00 | LOW_LIQUIDITY | 0.3x | 0.5x |

### 💱 FOREX EUR/GBP (EUR/USD, GBP/USD)

| Corridor | Horaires (Paris) | Régime | TP Mult | Risk Mult |
|----------|------------------|--------|---------|-----------|
| 🇬🇧 London Open | 08:00 - 09:00 | AGGRESSIVE_BREAKOUT | 0.4x | 1.3x |
| ☕ London Morning | 09:00 - 12:00 | TREND_FOLLOWING | 0.5x | 1.0x |
| 🥐 London Lunch | 12:00 - 14:00 | SCALPING | 0.3x | 0.7x |
| 🔥 NY Overlap | 14:00 - 16:00 | AGGRESSIVE_BREAKOUT | 0.5x | 1.5x |
| 🇺🇸 NY Afternoon | 16:00 - 18:00 | TREND_FOLLOWING | 0.4x | 1.0x |

### 💱 FOREX JPY (USD/JPY)

| Corridor | Horaires (Paris) | Régime | TP Mult | Risk Mult |
|----------|------------------|--------|---------|-----------|
| 🇯🇵 Tokyo Open | 01:00 - 03:00 | AGGRESSIVE_BREAKOUT | 0.5x | 1.3x |
| 🌸 Tokyo Morning | 03:00 - 07:00 | TREND_FOLLOWING | 0.4x | 1.0x |
| 🌅 Tokyo Close | 07:00 - 09:00 | CAUTIOUS_REVERSAL | 0.3x | 0.7x |
| 🗽 NY JPY Rush | 14:00 - 16:00 | AGGRESSIVE_BREAKOUT | 0.5x | 1.4x |
| 📊 NY JPY Core | 16:00 - 21:00 | TREND_FOLLOWING | 0.5x | 1.0x |

### 🛢️ COMMODITIES (Gold, Oil)

| Corridor | Horaires (Paris) | Régime | TP Mult | Risk Mult |
|----------|------------------|--------|---------|-----------|
| 🥇 COMEX Pre-Open | 14:00 - 15:30 | PULLBACK_SNIPER | 0.4x | 1.0x |
| ⛏️ Commodities Core | 15:30 - 18:00 | TREND_FOLLOWING | 0.5x | 1.2x |
| 🌆 Commodities Close | 18:00 - 21:00 | CAUTIOUS_REVERSAL | 0.4x | 0.8x |

### ₿ CRYPTO (SOL, BTC, ETH)

| Corridor | Horaires (Paris) | Régime | TP Mult | Risk Mult |
|----------|------------------|--------|---------|-----------|
| 🌏 Asia Morning | 01:00 - 05:00 | TREND_FOLLOWING | 0.5x | 1.0x |
| 💀 Dead Zone | 05:00 - 08:00 | LOW_LIQUIDITY | 0.3x | 0.5x |
| 🇪🇺 Europe Active | 08:00 - 14:00 | TREND_FOLLOWING | 0.5x | 1.0x |
| 🇺🇸 US Crypto Rush | 14:00 - 18:00 | AGGRESSIVE_BREAKOUT | 0.6x | 1.5x |
| 🌙 US Evening | 18:00 - 22:00 | TREND_FOLLOWING | 0.5x | 1.1x |
| 🌌 Late Night | 22:00 - 01:00 | SCALPING | 0.3x | 0.8x |

---

## 🤖 Régimes de Marché

| Régime | Description | Comportement |
|--------|-------------|--------------|
| `AGGRESSIVE_BREAKOUT` | Haute volatilité, breakouts | TP court, risk élevé |
| `TREND_FOLLOWING` | Tendance établie | TP moyen, risk standard |
| `PULLBACK_SNIPER` | Replis dans la tendance | Entrée précise |
| `SCALPING` | Micro-mouvements | TP très court, fréquence élevée |
| `CAUTIOUS_REVERSAL` | Prises de profits | Risk réduit |
| `LOW_LIQUIDITY` | Basse liquidité | Risk minimal |

---

## 📁 Fichiers

| Fichier | Description |
|---------|-------------|
| `/shared/trading_windows.py` | Module source - Golden Windows |
| `/shared/micro_corridors.py` | Module source - Micro-Corridors |
| `/*/lambda/*/trading_windows.py` | Copies pour chaque Lambda |
| `/*/lambda/*/micro_corridors.py` | Copies pour chaque Lambda |

---

## 🚀 Impact sur le Trading

### Mode Scalping (Gains Fréquents)
- **TP classique** : 3-5% → **TP adaptatif** : 0.5-1.5%
- Plus de trades par jour (5-15 au lieu de 1-2)
- Compounding accéléré

### Exemple de Signal avec Micro-Corridors
```json
{
    "pair": "EURUSD",
    "signal": "LONG",
    "entry": 1.0850,
    "tp": 1.0865,           // +0.14% (au lieu de +0.7%)
    "sl": 1.0840,           // -0.09% (au lieu de -0.35%)
    "corridor": "🔥 NY Overlap",
    "regime": "AGGRESSIVE_BREAKOUT",
    "scalping_mode": true,
    "risk_multiplier": 1.5,
    "tp_multiplier": 0.5,
    "sl_multiplier": 0.5
}
```

---

## 🚀 V5.1 - Nouvelles Fonctionnalités (2026-02-06)

### ✅ 1. Horloge Biologique Centralisée (`get_session_phase()`)
```python
from trading_windows import get_session_phase

phase = get_session_phase('GC=F')
# Returns: {"session": "COMEX_SESSION", "phase": "OPENING", "aggressiveness": "HIGH", "is_tradeable": True}
```

### ✅ 2. Position Sizing Cumulatif (`position_sizing.py`)
```python
from position_sizing import calculate_position_size

position = calculate_position_size(
    symbol='GC=F',
    initial_capital=1000.0,
    dynamo_table='EmpireCommoditiesHistory',
    asset_class='Commodities'
)
# La taille de position augmente avec le capital = Compound Interest!
```

### ✅ 3. Veto de Volume (`check_volume_veto()`)
```python
from micro_corridors import check_volume_veto

veto = check_volume_veto('^NDX', current_volume=100, avg_volume=200)
if veto['veto']:
    print(veto['reason'])  # "🛑 VETO VOLUME: 0.50x < 1.0x requis"
```

### ✅ 4. Prompt Bedrock Enrichi
L'IA reçoit maintenant :
- Le corridor actuel (ex: "💥 Impact Zone")
- Le régime de marché (ex: "AGGRESSIVE_BREAKOUT")
- Le niveau d'agressivité (ex: "HIGH")
- Des instructions adaptées au régime

---

## 🔄 Déploiement

Pour déployer les modifications sur AWS Lambda :

```bash
# Forex
cd /Users/zakaria/Trading/Forex && ./scripts/deploy.sh

# Indices  
cd /Users/zakaria/Trading/Indices && ./scripts/deploy.sh

# Commodities
cd /Users/zakaria/Trading/Commodities && ./scripts/deploy.sh
```

---

*Dernière mise à jour : 2026-02-06 (V5.1)*
