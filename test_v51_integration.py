#!/usr/bin/env python3
"""
🧪 V5.1 Integration Test Script
Tests all modules across all traders
"""
import sys
import os

# Add paths
traders = [
    ('Commodities', '/Users/zakaria/Trading/Commodities/lambda/commodities_trader'),
    ('Indices', '/Users/zakaria/Trading/Indices/lambda/indices_trader'),
    ('Forex', '/Users/zakaria/Trading/Forex/lambda/forex_trader'),
]

def test_trader(name, path):
    print(f"\n{'='*60}")
    print(f"🧪 TESTING {name.upper()} V5.1")
    print('='*60)
    
    # Add to path
    sys.path.insert(0, path)
    os.chdir(path)
    
    errors = []
    
    # 1. Test imports
    print("\n1️⃣ Testing imports...")
    
    try:
        from trading_windows import get_session_phase, is_within_golden_window
        print("   ✅ trading_windows OK")
    except Exception as e:
        print(f"   ❌ trading_windows: {e}")
        errors.append(f"trading_windows: {e}")
    
    try:
        from micro_corridors import get_adaptive_params, check_volume_veto
        print("   ✅ micro_corridors OK")
    except Exception as e:
        print(f"   ❌ micro_corridors: {e}")
        errors.append(f"micro_corridors: {e}")
    
    try:
        from position_sizing import calculate_position_size_from_capital
        print("   ✅ position_sizing OK")
    except Exception as e:
        print(f"   ❌ position_sizing: {e}")
        errors.append(f"position_sizing: {e}")
    
    try:
        from strategies import ForexStrategies, MICRO_CORRIDORS_AVAILABLE, SESSION_PHASE_AVAILABLE
        mc_status = "✅" if MICRO_CORRIDORS_AVAILABLE else "⚠️"
        sp_status = "✅" if SESSION_PHASE_AVAILABLE else "⚠️"
        print(f"   ✅ strategies OK (Corridors: {mc_status}, SessionPhase: {sp_status})")
    except Exception as e:
        print(f"   ❌ strategies: {e}")
        errors.append(f"strategies: {e}")
    
    # 2. Test Session Phase
    print(f"\n2️⃣ Session Phase for {name}:")
    try:
        from trading_windows import get_session_phase
        
        if name == 'Commodities':
            symbols = ['GC=F', 'CL=F']
        elif name == 'Indices':
            symbols = ['^NDX', '^GSPC', '^DJI']
        else:  # Forex
            symbols = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X']
        
        for symbol in symbols:
            phase = get_session_phase(symbol)
            print(f"   {symbol:12}: {phase['session']:15} | {phase['phase']:8} | "
                  f"Aggr={phase['aggressiveness']:6} | Trade={phase['is_tradeable']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        errors.append(f"session_phase: {e}")
    
    # 3. Test Adaptive Params
    print(f"\n3️⃣ Adaptive Params for {name}:")
    try:
        from micro_corridors import get_adaptive_params
        
        for symbol in symbols[:2]:  # Just first 2
            params = get_adaptive_params(symbol)
            print(f"   {symbol:12}: {params['corridor_name']:25} | "
                  f"Risk={params['risk_multiplier']}x | Scalp={params['scalping_mode']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        errors.append(f"adaptive_params: {e}")
    
    # 4. Test Position Sizing
    print(f"\n4️⃣ Position Sizing (Capital=$1000):")
    try:
        from position_sizing import calculate_position_size_from_capital
        
        pos = calculate_position_size_from_capital(symbols[0], 1000, 2)
        print(f"   {symbols[0]}: Position=${pos['position_usd']:.2f} | "
              f"Aggr={pos['aggressiveness']} | Corridor={pos['corridor_name']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        errors.append(f"position_sizing: {e}")
    
    # Clean up sys.path
    sys.path.remove(path)
    
    # Summary
    if errors:
        print(f"\n❌ {name} has {len(errors)} error(s)")
        return False
    else:
        print(f"\n✅ {name} V5.1 READY!")
        return True

def main():
    print("\n" + "="*60)
    print("🏛️ EMPIRE V5.1 - INTEGRATION TEST")
    print("="*60)
    print(f"📅 Time: {__import__('datetime').datetime.now()}")
    
    results = {}
    for name, path in traders:
        if os.path.exists(path):
            results[name] = test_trader(name, path)
        else:
            print(f"\n⚠️ {name} path not found: {path}")
            results[name] = False
    
    # Final Summary
    print("\n" + "="*60)
    print("📊 FINAL SUMMARY")
    print("="*60)
    
    all_ok = True
    for name, ok in results.items():
        status = "✅ READY" if ok else "❌ FAILED"
        print(f"   {name:15}: {status}")
        if not ok:
            all_ok = False
    
    if all_ok:
        print("\n🎉 ALL TRADERS V5.1 READY FOR DEPLOYMENT!")
    else:
        print("\n⚠️ Some traders need attention")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
