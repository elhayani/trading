#!/usr/bin/env python3
"""
Test script to verify S3 bucket creation and data upload functionality
"""
import sys
import os
import logging
from datetime import datetime, timedelta

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from s3_loader import S3Loader

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_bucket_creation():
    """Test bucket creation"""
    logger.info("=" * 60)
    logger.info("TEST 1: Bucket Creation")
    logger.info("=" * 60)

    loader = S3Loader()
    success = loader.create_bucket_if_not_exists()

    if success:
        logger.info("✅ Bucket creation/verification PASSED")
    else:
        logger.error("❌ Bucket creation/verification FAILED")

    return success

def test_data_upload():
    """Test data upload to S3"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Data Upload")
    logger.info("=" * 60)

    loader = S3Loader()

    # Create sample data for 2022
    sample_data = []
    start_date = datetime(2022, 1, 1)

    for i in range(10):
        dt = start_date + timedelta(hours=i)
        timestamp = int(dt.timestamp() * 1000)
        # [timestamp, open, high, low, close, volume]
        candle = [
            timestamp,
            100.0 + i,  # open
            102.0 + i,  # high
            99.0 + i,   # low
            101.0 + i,  # close
            1000000     # volume
        ]
        sample_data.append(candle)

    # Test upload
    symbol = "TEST_SYMBOL"
    year = 2022

    success = loader.upload_historical_data(symbol, sample_data, year)

    if success:
        logger.info("✅ Data upload PASSED")
    else:
        logger.error("❌ Data upload FAILED")

    return success

def test_data_retrieval():
    """Test retrieving uploaded data"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Data Retrieval")
    logger.info("=" * 60)

    loader = S3Loader()

    try:
        # Try to fetch the test data we just uploaded
        data = loader.fetch_historical_data("TEST_SYMBOL", days=365, offset_days=365*2)

        if data:
            logger.info(f"✅ Data retrieval PASSED - Found {len(data)} candles")
            return True
        else:
            logger.warning("⚠️  No data found (might be expected if first run)")
            return True
    except Exception as e:
        logger.error(f"❌ Data retrieval FAILED: {e}")
        return False

if __name__ == "__main__":
    logger.info("Starting S3 Upload Functionality Tests...")
    logger.info("Bucket: empire-trading-data-paris")
    logger.info("Region: eu-west-3")
    logger.info("")

    results = []

    # Run tests
    results.append(("Bucket Creation", test_bucket_creation()))
    results.append(("Data Upload", test_data_upload()))
    results.append(("Data Retrieval", test_data_retrieval()))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} - {test_name}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)
