import os
import zipfile

# Mapping des Bots et fichiers
BOTS = [
    {
        'name': 'Indices',
        'source_dir': '/Users/zakaria/Trading/Indices/lambda/indices_trader',
        'zip_path': '/Users/zakaria/Trading/Indices/lambda/indices_trader.zip',
        'files': [
            'lambda_function.py', 'config.py', 'strategies.py', 'data_loader.py',
            'macro_context.py', 'predictability_index.py', 'position_sizing.py',
            'trading_windows.py', 'trailing_stop.py', 'micro_corridors.py', 'news_fetcher.py'
        ]
    },
    {
        'name': 'Forex',
        'source_dir': '/Users/zakaria/Trading/Forex/lambda/forex_trader',
        'zip_path': '/Users/zakaria/Trading/Forex/lambda/forex_trader.zip',
        'files': [
            'lambda_function.py', 'config.py', 'strategies.py', 'data_loader.py',
            'macro_context.py', 'predictability_index.py', 'position_sizing.py',
            'trading_windows.py', 'trailing_stop.py', 'micro_corridors.py', 'news_fetcher.py'
        ]
    },
    {
        'name': 'Commodities',
        'source_dir': '/Users/zakaria/Trading/Commodities/lambda/commodities_trader',
        'zip_path': '/Users/zakaria/Trading/Commodities/lambda/commodities_trader.zip',
        'files': [
            'lambda_function.py', 'config.py', 'strategies.py', 'data_loader.py',
            'macro_context.py', 'predictability_index.py', 'position_sizing.py',
            'trading_windows.py', 'trailing_stop.py', 'micro_corridors.py', 'news_fetcher.py'
        ]
    },
    # Crypto structure is slightly different (v4_hybrid_lambda.py)
    {
        'name': 'Crypto',
        'source_dir': '/Users/zakaria/Trading/Crypto', # Root or lambda?
        # Based on file search: ./Crypto/lambda/v4_trader.zip
        # And source likely v4_hybrid_lambda.py needs to be renamed to lambda_function.py inside zip? 
        # Let's check Crypto folder content first.
        'zip_path': '/Users/zakaria/Trading/Crypto/lambda/v4_trader.zip',
        'files': [] # To be determined
    }
]

def update_zip(bot):
    if bot['name'] == 'Crypto':
        return # Skip Crypto for now, need verification
        
    print(f"📦 Updating {bot['name']} ZIP at {bot['zip_path']}...")
    try:
        with zipfile.ZipFile(bot['zip_path'], 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename in bot['files']:
                file_path = os.path.join(bot['source_dir'], filename)
                if os.path.exists(file_path):
                    zf.write(file_path, arcname=filename)
                    print(f"  - Added {filename}")
                else:
                    print(f"  ⚠️ File not found: {file_path}")
        print(f"✅ {bot['name']} ZIP Updated.")
    except Exception as e:
        print(f"❌ Error updating {bot['name']}: {e}")

if __name__ == "__main__":
    for bot in BOTS:
        update_zip(bot)
