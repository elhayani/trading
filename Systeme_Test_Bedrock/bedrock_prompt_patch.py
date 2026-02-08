"""
Patch pour améliorer le prompt Bedrock pour les Indices en mode Bull Market

À ajouter dans lambda_function.py, fonction ask_bedrock(),
AVANT la définition du prompt (ligne ~340)
"""

# ============================================================================
# PATCH À AJOUTER DANS ask_bedrock() - LIGNE ~340
# ============================================================================

def ask_bedrock_PATCHED(pair, signal_data, news_context, macro_data=None):
    """
    Validates the trade with Claude 3 Haiku using Technicals + News
    """
    # Define strategy-specific instructions
    strategy_instruction = "If news is conflicting (e.g. LONG signal but very BEARISH news), return CANCEL. If news is supportive or neutral, return CONFIRM."

    # Custom instruction for Momentum/Breakout (Nasdaq)
    if 'BOLLINGER_BREAKOUT' in signal_data.get('strategy', ''):
         strategy_instruction = "This is a MOMENTUM trade (High Volatility). Speed is critical. Only CANCEL if the news is EXTREMELY contradictory (e.g. Rate Hike for a Long). If news is just noise or mildly negative, CONFIRM to capture the momentum."

    # 🔥 NEW: Custom instruction for S&P 500 TREND_PULLBACK in Bull Markets
    if 'TREND_PULLBACK' in signal_data.get('strategy', '') and pair == '^GSPC':
        # Check if we're in bull mode (RSI > 50)
        rsi = signal_data.get('rsi', 50)

        if rsi > 50 and rsi <= 65:
            # Bull market pullback - be momentum-friendly
            strategy_instruction = """
            This is a PULLBACK in a BULL MARKET (RSI between 50-65).

            CONTEXT: The market is in an uptrend. Small pullbacks and lateral consolidations
            are HEALTHY and create buying opportunities.

            KEY RULES FOR CONFIRMATION:
            1. ✅ Lateral consolidation (sideways price action) → CONFIRM
               - Reason: Accumulation phase, not distribution

            2. ✅ Small pullback in uptrend (< 3% from recent high) → CONFIRM
               - Reason: Normal breathing in bull markets

            3. ✅ Neutral or mildly negative news → CONFIRM
               - Reason: Bull markets climb a wall of worry

            ONLY CANCEL IF:
            - Major bearish reversal pattern clearly forming (Head & Shoulders confirmed)
            - Extremely negative structural news (War outbreak, Bank crisis, Fed emergency hike)
            - VIX spike > 30 with negative news

            DEFAULT BIAS: In strong uptrends, prefer CONFIRM unless evidence is OVERWHELMING.
            Remember: Missing a bull run is more costly than a small stop loss.
            """

        elif rsi > 65:
            # Near overbought - be more cautious but not blocking
            strategy_instruction = """
            This is a LATE-STAGE PULLBACK (RSI > 65, near overbought).

            Be slightly more selective:
            - ✅ CONFIRM if pullback is significant (> 2%) and news neutral/positive
            - ⚠️  CANCEL if minor pullback (< 1%) with negative news (risk of reversal)
            - ⚠️  CANCEL if major divergence signals (volume dropping, momentum waning)

            Bias: Neutral to slightly cautious
            """

    # ... rest of the function remains the same
    # (macro context, corridor context, prompt building, etc.)


# ============================================================================
# ALTERNATIVE: Modification plus simple (si tu veux juste assouplir)
# ============================================================================

# Remplacer juste cette section (ligne ~334):
"""
AVANT:
    strategy_instruction = "If news is conflicting..."

APRÈS:
    # Default instruction (unchanged)
    strategy_instruction = "If news is conflicting (e.g. LONG signal but very BEARISH news), return CANCEL. If news is supportive or neutral, return CONFIRM."

    # 🔥 Assouplir pour tous les indices en général
    if pair in ['^GSPC', '^NDX']:
        strategy_instruction += "\\n\\nNOTE: Indices tend to trend strongly. In bull markets (RSI > 50), prefer CONFIRM on pullbacks unless news is catastrophic."
"""


# ============================================================================
# INSTRUCTIONS D'APPLICATION
# ============================================================================

"""
1. Ouvrir: /Users/zakaria/Trading/Indices/lambda/indices_trader/lambda_function.py

2. Trouver la fonction ask_bedrock() (ligne ~330)

3. Remplacer la section strategy_instruction par la version PATCHED ci-dessus

4. Sauvegarder

5. Tester avec backtest
"""


# ============================================================================
# TEST DE VALIDATION
# ============================================================================

def test_prompt_logic():
    """
    Test pour vérifier que la logique fonctionne
    """

    test_cases = [
        {'rsi': 55, 'pair': '^GSPC', 'strategy': 'TREND_PULLBACK', 'expected': 'momentum-friendly'},
        {'rsi': 68, 'pair': '^GSPC', 'strategy': 'TREND_PULLBACK', 'expected': 'slightly cautious'},
        {'rsi': 45, 'pair': '^GSPC', 'strategy': 'TREND_PULLBACK', 'expected': 'default'},
        {'rsi': 55, 'pair': '^NDX', 'strategy': 'BOLLINGER_BREAKOUT', 'expected': 'momentum'},
    ]

    for case in test_cases:
        print(f"RSI {case['rsi']}, {case['pair']}, {case['strategy']}")
        print(f"  Expected: {case['expected']}")
        print()

if __name__ == "__main__":
    test_prompt_logic()
