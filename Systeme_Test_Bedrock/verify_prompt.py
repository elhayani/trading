
import sys
import os
import logging
import json

# Add module path
sys.path.append('/Users/zakaria/Trading/Crypto/lambda/v4_trader')

# Mock environment variables needed for import
os.environ['SYMBOL'] = 'BTC/USDT'
os.environ['CAPITAL'] = '1000'

# Import the function
try:
    from v4_hybrid_lambda import ask_bedrock
except ImportError as e:
    print(f"Error importing: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_bedrock_prompt():
    print("--- Testing Bedrock Prompt Fix ---")

    # Case 1: RSI 25 (Buy), Neutral/Minor News -> Should CONFIRM
    print("\nCase 1: RSI 25, Minor News")
    symbol = "BTC/USDT"
    rsi = 25.0
    news_context = """
    ASSET NEWS:
    - Bitcoin holds steady above $60k support.
    - Minor network congestion reported, fees slightly up.
    - Analyst predicts potential rebound.
    """
    portfolio_stats = {'dynamic_threshold': 40}
    history = []

    response = ask_bedrock(symbol, rsi, news_context, portfolio_stats, history)
    print(f"Response: {json.dumps(response, indent=2)}")
    
    if response.get('decision') == 'CONFIRM':
        print("✅ SUCCESS: Confirmed on minor news.")
    else:
        print("❌ FAILURE: Cancelled on minor news.")

    # Case 2: RSI 25 (Buy), CATASTROPHIC News -> Should CANCEL
    print("\nCase 2: RSI 25, Major Hack News")
    news_context_bad = """
    ASSET NEWS:
    - BREAKING: Major exchange hacked, 50,000 BTC stolen.
    - Panic selling across crypto markets.
    - Regulators announce immediate crackdown on Bitcoin trading.
    """
    
    response_bad = ask_bedrock(symbol, rsi, news_context_bad, portfolio_stats, history)
    print(f"Response: {json.dumps(response_bad, indent=2)}")

    if response_bad.get('decision') == 'CANCEL':
        print("✅ SUCCESS: Cancelled on catastrophic news.")
    else:
        print("❌ FAILURE: Confirmed despite catastrophic news.")

if __name__ == "__main__":
    test_bedrock_prompt()
