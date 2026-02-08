#!/usr/bin/env python3
"""
Test the complete fallback + upload workflow with a real symbol
"""
import sys
import os
import logging

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from run_test_v2 import fetch_market_data_with_fallback

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_symbol(symbol, days=7):
    """
    Test fallback and upload for a specific symbol

    Args:
        symbol: Trading symbol to test (e.g., ^GSPC, EURUSD)
        days: Number of days to fetch
    """
    logger.info("=" * 80)
    logger.info(f"Testing: {symbol} ({days} days)")
    logger.info("=" * 80)

    try:
        # This should:
        # 1. Try S3 first (likely fail since bucket is new/empty)
        # 2. Fallback to YFinance
        # 3. Upload to S3
        data = fetch_market_data_with_fallback(symbol, days=days, offset_days=0)

        if data:
            logger.info(f"✅ SUCCESS: Retrieved {len(data)} candles for {symbol}")
            logger.info(f"   First candle timestamp: {data[0][0]}")
            logger.info(f"   Last candle timestamp: {data[-1][0]}")
            return True
        else:
            logger.error(f"❌ FAILED: No data retrieved for {symbol}")
            return False

    except Exception as e:
        logger.error(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    logger.info("Testing Fallback + S3 Upload Workflow")
    logger.info("")

    # Test with a few different asset classes
    test_cases = [
        ("^GSPC", 7),    # S&P 500 Index (should use 1d interval)
        # ("EURUSD", 7),   # Forex (would use 1h interval)
        # ("BTCUSDT", 2),  # Crypto (would use Binance API)
    ]

    results = []

    for symbol, days in test_cases:
        success = test_symbol(symbol, days)
        results.append((symbol, success))
        logger.info("")

    # Summary
    logger.info("=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for symbol, result in results:
        status = "✅" if result else "❌"
        logger.info(f"{status} {symbol}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n🎉 All tests passed! Data should now be in S3.")
        sys.exit(0)
    else:
        logger.error(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)
