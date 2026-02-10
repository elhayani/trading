# 📋 CHANGELOG — Empire Trading System

---

## V7.0 — "Unified Architecture" (2026-02-10) 🏛️

### 🔥 Refonte Majeure : Super-Lambda Unifiée

**Avant** : 4 Lambdas séparées (Crypto, Forex, Indices, Commodities) → conflits, throttling, coûts x4.
**Après** : 1 seule Lambda traite 8 actifs séquentiellement → zéro conflit, coût /4.

#### Architecture
- **Super-Lambda** : Boucle séquentielle `BTC → ETH → SOL → PAXG → XAG → OIL → SPX → NDX`
- **Smart Scheduling** : 4 règles CRON adaptatives (ECO / Standard AM / Turbo / Standard PM)
- **Turbo Mode** : Scan toutes les **1 minute** pendant l'ouverture US (14h-16h Paris)
- **Renommage** : `Crypto/` → `Empire/` (reflète l'architecture unifiée)

#### Actifs (8 au total)
| Classe | Actifs |
|--------|--------|
| Crypto | BTC/USDT, ETH/USDT, SOL/USDT |
| Commodities | PAXG/USDT (Or), XAG/USDT (Argent), OIL/USDT (Pétrole) |
| Indices | SPX/USDT (S&P 500), NDX/USDT (Nasdaq) |

#### Nettoyage
- Suppression de 40+ fichiers obsolètes (JSON de test, docs V6, scripts, backups)
- Suppression de 6 dossiers dupliqués (`lambda/`, `shared/`, `monitoring/`, `tests/`, `scripts/`, `docs/`)
- Destruction des 3 stacks AWS legacy (`CommoditiesTradingStack`, `ForexTradingStack`, `IndicesTradingStack`)
- Suppression du code mort (`predictability_index.py`, `trailing_stop.py`, `v4_hybrid_lambda_optimized.py`)

#### Code
- Fix `datetime.utcnow()` → `datetime.now(timezone.utc)` (deprecation warning)
- Suppression imports inutilisés (`predictability_index`)
- Nettoyage commentaires V5/V6 → standardisation V7
- Volume adaptatif par classe d'actif (Crypto 1.2x, Commodities 0.12x, Indices 0.24x)
- Corridors micro ajoutés pour PAXG, XAG, OIL, SPX, NDX
- Table DynamoDB unifiée : `EmpireTradesHistory`

#### Fichiers modifiés
- `Empire/lambda/v4_trader/v4_hybrid_lambda.py` — Moteur unifié
- `Empire/lambda/v4_trader/micro_corridors.py` — Corridors multi-actifs
- `Empire/lambda/v4_trader/macro_context.py` — Suppression GC=F, CL=F
- `Empire/infrastructure/cdk/stacks/v4_trading_stack.py` — 4 CRON rules + 8 SYMBOLS
- `Empire/scripts/deploy.sh` — Mise à jour chemins

---

## V6.2 — "P&L Fix Edition" (2026-02-08)

### 🚨 Correction Critique
- **Bug** : P&L calculé sur `Size` (quantité) au lieu de `Cost` (valeur USD)
- **Impact** : Profits affichés 1000x trop petits
- **Fix** : `pnl_dollars = (pnl_pct / 100) * position_value`

---

## V6.1 — "Maximum Performance" (2026-02-08)

### Optimisations R/R
- Crypto : R/R 1:1 → **1:2.3** (SL -3.5%, TP +8.0%)
- Forex : R/R 1:3.5 → **1:4.0**, Leverage 30x → 20x
- Indices : R/R 1:4.5 → **1:5.0**
- Commodities : R/R 1:3.0 → **1:4.5**, Trailing Stop ajouté

### Corrections
- Fix exit management (architecture two-phase)
- Fix Mock DynamoDB signature pour backtests
- Fix deployment scripts paths

---

## V6.0 — "Profit Maximizer" (2026-02-07)

- Trailing Stop universel pour tous les actifs
- SOL Turbo Mode (activation 6%, distance 2.5%)
- Dynamic Position Sizing (Kelly simplifié)

---

## V5.1 — "Fortress Edition" (2026-01-15)

- Micro-Corridors (paramètres adaptatifs par heure/actif)
- Circuit Breaker 3 niveaux (L1/L2/L3 sur BTC)
- Momentum Filter (EMA 20/50 cross)
- Correlation Check (limite exposition crypto)
- Reversal Trigger (Green Candle filter)

---

## V5.0 — "Bedrock AI" (2025-12-20)

- Intégration AWS Bedrock (Claude 3 Haiku)
- Devil's Advocate AI validation
- Multi-Timeframe confirmation (1h + 4h)
- VIX Filter (blocage si > 30)
- Golden Windows (heures de haute liquidité)

---

**© 2026 Empire Trading Systems**
