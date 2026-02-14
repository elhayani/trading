**EMPIRE TRADING SYSTEM**

Nouvelle Stratégie --- Momentum Scalping 1 Min

Document de référence complet · Basé sur l\'analyse backtest et les
décisions de conception

**1. Pourquoi on change la stratégie**

**Résultats du backtest (ancien système)**

Le backtest sur 7 jours (168 bougies 1H, 14 actifs, \$1,000 capital) a
donné ces résultats :

  --------------------------------------------------------------
  **Métrique**        **Résultat**   **Cible**     **Verdict**
  ------------------- -------------- ------------- -------------
  Retour total        -28.26%        +7%/sem       ❌

  Win rate            21.7%          52%+          ❌

  Profit factor       0.20           1.5+          ❌

  Drawdown max        -24.8%         \<5%/jour     ❌

  Trades/jour         15.1           12/jour       ✅

  Sharpe ratio        -25.9          1.0+          ❌
  --------------------------------------------------------------

**Les 3 causes racines**

> **•** Mauvaise philosophie : l\'ancien système est Mean Reversion (RSI
> oversold/overbought = contre-tendance). Il achète quand l\'actif chute
> et vend quand il monte. Sur un marché en tendance, c\'est
> systématiquement perdant.
>
> **•** Granularité incorrecte : les signaux sur bougies 1H sont
> inutiles pour une stratégie de scalping à 20-40 secondes. Le backtest
> ne peut pas voir ce qui se passe à l\'intérieur d\'une bougie d\'1
> heure.
>
> **•** SL trop serré : SL fixe de 0.2% inférieur au bruit de marché
> normal (±0.3-0.5% par heure). 78.3% des trades touchaient le stop
> avant d\'avoir eu le temps de respirer.

**2. Nouvelle philosophie --- Momentum Pur**

> Principe fondamental : si le prix monte avec du volume → on achète. Si
> le prix baisse avec du volume → on vend. On sort rapidement avec un
> petit gain. Chaque gain s\'ajoute au capital (compound).

  -------------------------------------------------------------
  **Aspect**    **Ancien système (Mean  **Nouveau système
                Reversion)**            (Momentum)**
  ------------- ----------------------- -----------------------
  Signal        RSI oversold/overbought EMA5 croise EMA13 sur 1
                                        min

  Logique       Anticiper un            Suivre le mouvement en
                retournement            cours

  Timeframe     Bougies 1H              Bougies 1 minute
  signal                                

  Durée         1-3 heures              2-10 minutes max
  position                              

  TP/SL         ATR fixe ou % fixe      Dynamique basé sur ATR
                                        1min

  Tendance      Ignorée                 Filtrée via 4H
  macro                                 (obligatoire)

  Philosophie   Contre le marché        Avec le marché
  -------------------------------------------------------------

**3. Paramètres de configuration**

**config.py --- Valeurs cibles**

> CAPITAL = float(os.getenv(\'CAPITAL\', \'10000\'))
>
> LEVERAGE = 5
>
> MAX_OPEN_TRADES = 3
>
> MIN_VOLUME_24H = 5_000_000 \# \$5M minimum
>
> \# Momentum TP/SL dynamiques (basés sur ATR 1min)
>
> TP_MULTIPLIER = 2.0 \# TP = 2 × ATR_1min
>
> SL_MULTIPLIER = 1.0 \# SL = 1 × ATR_1min
>
> MAX_HOLD_CANDLES = 10 \# Timeout : 10 minutes max
>
> \# Indicateurs momentum
>
> EMA_FAST = 5 \# EMA rapide 1min
>
> EMA_SLOW = 13 \# EMA lente 1min
>
> VOLUME_SURGE_RATIO = 1.5 \# Volume 1.5x la moyenne
>
> MIN_MOMENTUM_SCORE = 60 \# Score minimum pour ouvrir
>
> MIN_ATR_PCT_1MIN = 0.25 \# ATR minimum après frais
>
> \# Compound
>
> USE_COMPOUND = True
>
> \# Liquidité / scaling
>
> MAX_NOTIONAL_PCT_OF_VOLUME = 0.005 \# Max 0.5% du volume 24h

**Pourquoi \$5M de volume minimum**

  -------------------------------------------------------------
  **Seuil        **Actifs       **Win rate       **Verdict**
  volume**       éligibles**    observé**        
  -------------- -------------- ---------------- --------------
  \$10M          14 actifs      44%              ✅ Profitable

  \$5M           \~25 actifs    \~40% estimé     ✅ Objectif

  \$3M           41 actifs      \~30%            ⚠️ Limite

  \$2M           61 actifs      10%              ❌ Déficitaire
  -------------------------------------------------------------

À \$2M, des micro-caps entrent (POWER, CLO, ZAMA, FHE) avec ATR de 3-9%.
Un seul SL sur ces actifs (-13%) efface 10 TP sur BTC (+2%). \$5M est le
sweet spot entre volume de setups et qualité des actifs.

**4. Architecture des signaux**

**Pré-filtre mobilité (AVANT analyze_momentum)**

Appliqué sur 25 bougies 1min. Si une étape échoue → skip immédiat, pas
de calcul lourd.

**Étape 1 --- ATR récent (volatilité suffisante)**

> atr_10 = calculate_atr(high, low, close, period=10).iloc\[-1\]
>
> atr_pct = (atr_10 / close.iloc\[-1\]) \* 100
>
> if atr_pct \< 0.25: return \'SKIP_FLAT\' \# Trop stable, frais \> gain

**Étape 2 --- Volume surge (participants actifs)**

> vol_recent = volume.iloc\[-3:\].mean()
>
> vol_avg = volume.iloc\[-23:-3\].mean()
>
> vol_ratio = vol_recent / vol_avg
>
> if vol_ratio \< 1.3: return \'SKIP_NO_VOLUME\'

**Étape 3 --- Price thrust (mouvement directionnel)**

> thrust = abs(close.iloc\[-1\] - close.iloc\[-6\]) / close.iloc\[-6\]
> \* 100
>
> if thrust \< 0.20: return \'SKIP_NO_THRUST\'

**Scoring momentum (analyze_momentum)**

  ------------------------------------------------------
  **Critère**        **Condition**          **Points**
  ------------------ ---------------------- ------------
  EMA crossover UP   EMA5 croise au-dessus  +40 (signal
                     EMA13                  LONG)

  EMA crossover DOWN EMA5 croise en-dessous +40 (signal
                     EMA13                  SHORT)

  Confirmation prix  price_change_3 dans la +20
                     direction              

  Volume surge ≥     Explosion de volume    +35
  2.0x                                      

  Volume surge ≥     Volume correct         +25
  1.5x                                      

  Volume surge \<    Volume faible          -20
  1.0x                                      

  ATR ≥ 0.15%        Volatilité suffisante  +15

  ATR \< 0.10%       Trop plat              SKIP

  Score minimum      Seuil d\'ouverture     ≥ 60
  ------------------------------------------------------

**Filtre tendance 4H (obligatoire)**

> **•** Calculer SMA10 et SMA20 sur les bougies 4H resamplées depuis les
> bougies 1H
>
> **•** Si SMA10 \> SMA20 → tendance BULL → autoriser LONG seulement
>
> **•** Si SMA10 \< SMA20 → tendance BEAR → autoriser SHORT seulement
>
> **•** Ce filtre seul aurait éliminé 50-60% des mauvais trades du
> backtest

**Tri des actifs par mobilité (optimisation scanner)**

Au lieu de scanner les 415 actifs dans l\'ordre aléatoire :

> **•** Fetch ultra-léger 5 bougies sur tous les 415 actifs (\~2
> secondes total)
>
> **•** Calculer last_move = \|close\[-1\] - close\[-5\]\| / close\[-5\]
> \* 100
>
> **•** Trier par last_move décroissant
>
> **•** Scanner en profondeur uniquement les TOP 50 actifs les plus
> mobiles

  --------------------------------------------------------------
  **Métrique**            **Sans            **Avec pré-filtre**
                          pré-filtre**      
  ----------------------- ----------------- --------------------
  Actifs analysés en      415               \~30-50
  profondeur                                

  Temps de scan total     \~45s             \~8s

  Appels API Binance      415 × 50 = 20,750 415×5 + 50×50 =
  (bougies)                                 4,575

  Faux signaux (actifs    Nombreux          Quasi nuls
  plats)                                    
  --------------------------------------------------------------

**5. Architecture Lambda**

  -------------------------------------------------------------------
  **Lambda**     **Fréquence**   **Rôle**         **Changements**
  -------------- --------------- ---------------- -------------------
  Lambda 1       1 minute        Scan 415         Fetch 1min,
  SCANNER                        actifs + ouvre   analyze_momentum,
                                 positions        pré-filtre mobilité

  Lambda 2       10 secondes     Check            Timeout 10min
  CLOSER_10S                     TP/SL/TIMEOUT    ajouté

  Lambda 3       20 secondes     Check            Identique Lambda 2
  CLOSER_20S                     TP/SL/TIMEOUT    

  Lambda 4       30 secondes     Check            Identique Lambda 2
  CLOSER_30S                     TP/SL/TIMEOUT    
  -------------------------------------------------------------------

> Passage de 2 à 3 closers : latence de détection réduite de 40s à 10s.
> Critique pour capturer les TP sur une stratégie dont les positions
> durent 2-10 minutes. Coût AWS : \~\$0.10/jour.

**Timeout position (nouveau --- lambda2_closer.py)**

> entry_time = datetime.fromisoformat(position\[\'timestamp\'\])
>
> age_minutes = (datetime.now(timezone.utc) -
> entry_time).total_seconds() / 60
>
> if age_minutes \> TradingConfig.MAX_HOLD_CANDLES: \# 10 minutes
>
> \# Fermer au prix marché
>
> exit_reason = \'TIMEOUT\'

**Jitter anti-congestion DynamoDB**

> import random
>
> jitter = random.uniform(0, 2) \# 0 à 2 secondes
>
> time.sleep(jitter) \# Étale les 3 Lambdas sur DynamoDB

**6. Fichiers à modifier**

  -----------------------------------------------------------------------
  **Fichier**             **Action**                       **Priorité**
  ----------------------- -------------------------------- --------------
  config.py               Nouveaux paramètres (capital,    🔴 CRITIQUE
                          TP/SL multipliers, ATR min,      
                          scaling)                         

  market_analysis.py      Ajouter mobility_score() et      🔴 CRITIQUE
                          analyze_momentum()               

  exchange_connector.py   Ajouter fetch_ohlcv_1min() via   🔴 CRITIQUE
                          API Binance Futures directe      

  trading_engine.py       Modifier run_cycle() pour        🔴 CRITIQUE
                          utiliser analyze_momentum()      

  risk_manager.py         Activer compound + cap liquidité 🟠 HAUTE
                          MAX_NOTIONAL_PCT_OF_VOLUME       

  lambda2_closer.py       Ajouter timeout 10min + jitter   🟠 HAUTE
                          0-2s                             

  decision_engine.py      Simplifier evaluate() :          🟡 MOYENNE
                          supprimer Bedrock et filtre      
                          macro                            

  lambda1_scanner.py      Ajouter pré-tri par mobilité     🟡 MOYENNE
                          avant la boucle principale       

  atomic_persistence.py   Aucun changement                 ✅ NE PAS
                                                           TOUCHER

  anti_spam_helpers.py    Aucun changement                 ✅ NE PAS
                                                           TOUCHER

  models.py               Aucun changement                 ✅ NE PAS
                                                           TOUCHER

  claude_analyzer.py      Aucun changement                 ✅ NE PAS
                                                           TOUCHER
  -----------------------------------------------------------------------

**7. Compound effect et capital**

**Mécanique du compound**

> \# Dans risk_manager.py
>
> capital_actuel = TradingConfig.COMPOUND_BASE_CAPITAL +
> self.risk_manager.daily_pnl
>
> margin_par_trade = capital_actuel / MAX_OPEN_TRADES \# Recalculé à
> chaque trade

**Projection à \$10,000 de départ (+1%/jour)**

  --------------------------------------------------------------
  **Période**    **Capital**    **Gain/jour**   **Gain/mois**
  -------------- -------------- --------------- ----------------
  Départ         \$10,000       +\$100          +\$3,000

  Mois 1         \$13,000       +\$130          +\$3,900

  Mois 3         \$20,000       +\$200          +\$6,000

  Mois 6         \$40,000       +\$400          +\$12,000

  Mois 12        \$160,000      +\$1,600        +\$48,000
  --------------------------------------------------------------

**8. Plan de scaling automatique**

Ajouter get_scaling_config(capital) dans config.py --- le système
s\'adapte seul :

  -------------------------------------------------------------------------------------------
  **Zone**   **Capital**   **MIN_VOLUME**   **Actifs**   **Leverage**   **Note**
  ---------- ------------- ---------------- ------------ -------------- ---------------------
  Zone 1 ✅  \$10K --      \$5M             \~115        x5             Config actuelle ---
             \$60K                                                      full universe

  Zone 2 ✅  \$60K --      \$20M            \~55         x5             Liquid mid-cap
             \$150K                                                     

  Zone 3 ⚠️  \$150K --     \$50M            \~15         x3             Large cap only
             \$500K                                                     

  Zone 4 🔴  \$500K --     \$200M           \~5          x2             BTC ETH SOL XRP BNB
             \$2M                                                       
  -------------------------------------------------------------------------------------------

> Avec 415 actifs scannés, la config actuelle tient jusqu\'à \$60,000
> sans aucune modification. C\'est la première milestone de scaling.

**Règle de liquidité automatique**

> \# Notionnel max = 0.5% du volume 24h de l\'actif
>
> max_notional = volume_24h \* 0.005
>
> if (margin \* leverage) \> max_notional:
>
> margin = max_notional / leverage
>
> logger.warning(f\'\[LIQUIDITY CAP\] {symbol} capped at
> \${max_notional:.0f}\')

Cette règle protège automatiquement quand le capital grossit et force la
migration vers des actifs plus liquides.

**9. Économie du trade à \$10,000**

  --------------------------------------------------------------
  **Paramètre**              **Valeur**
  -------------------------- -----------------------------------
  Capital                    \$10,000

  Marge par trade (3 slots)  \$3,333

  Notionnel par trade (x5)   \$16,667

  Commission (0.1% × 2 legs) \$33.33 par trade

  ATR minimum requis         0.25% (pour couvrir les frais)

  TP visé (ATR 0.40% × 2)    +0.80% → +\$133 brut → +\$100 net

  SL (ATR 0.40% × 1)         -0.40% → -\$67 brut → -\$100 net

  Breakeven win rate         50% (R:R 1:1 après frais)

  Win rate cible             55-60%

  P&L journalier cible       +\$100 (+1%)
  --------------------------------------------------------------

**10. Tests à effectuer après implémentation**

> **•** Test fetch_ohlcv_1min() isolé sur BTCUSDT --- vérifier 50
> bougies avec colonnes correctes
>
> **•** Test analyze_momentum() avec données réelles --- vérifier que le
> signal change selon la direction
>
> **•** Test mobility_score() --- vérifier que les actifs plats
> retournent score=0
>
> **•** Test end-to-end LIVE_MODE=False --- vérifier dans les logs que
> signal_type vient de analyze_momentum
>
> **•** Test compound --- ouvrir un trade fictif +\$5, vérifier que le
> capital suivant est \$10,005
>
> **•** Test timeout --- créer une position avec timestamp -15min,
> vérifier que CLOSER la ferme avec raison TIMEOUT
>
> **•** Test scaling --- simuler capital=\$70,000, vérifier que
> MIN_VOLUME_24H passe à \$20M automatiquement

**RÉSUMÉ EN UNE LIGNE**

> Remplacer la logique RSI mean-reversion sur 1H par un momentum
> EMA5/EMA13 sur 1 minute, avec pré-filtre de mobilité sur les 415
> actifs, 3 closers à 10/20/30s, TP/SL dynamiques basés sur l\'ATR,
> compound activé, et scaling automatique de \$10K à \$2M.
