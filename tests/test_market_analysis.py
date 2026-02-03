
import unittest
import pandas as pd
import numpy as np
import sys
import os

# Ajout du path pour importer le module market_analysis
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/data_fetcher')))
from market_analysis import analyze_market

class TestMarketAnalysis(unittest.TestCase):
    
    def create_fake_ohlcv(self, prices):
        """Helper pour créer des données OHLCV à partir d'une liste de prix de clôture"""
        data = []
        base_time = 1700000000000
        for i, price in enumerate(prices):
            # [timestamp, open, high, low, close, volume]
            # On met high/low/open proches du close pour simplifier
            data.append([
                base_time + i*3600000, 
                price, 
                price * 1.001, 
                price * 0.999, 
                price, 
                1000
            ])
        return data

    def test_detection_double_top(self):
        print("\n🧪 TEST: Double Top")
        # Simulation: Montée -> Sommet 1 -> Baisse -> Sommet 2 (niv S1) -> Baisse
        prices = [
            100, 110, 120, 130, 140, 150, # Montée
            150, 140, 130, 120,          # Baisse
            130, 140, 149.5, 140, 130     # Remontée vers 150 (149.5) puis baisse
        ]
        ohlcv = self.create_fake_ohlcv(prices)
        result = analyze_market(ohlcv)
        
        print(f"Patterns trouvés : {result['patterns']}")
        self.assertIn("DOUBLE_TOP_POTENTIAL", result['patterns'])

    def test_detection_ete(self):
        print("\n🧪 TEST: Épaule-Tête-Épaule (ETE)")
        # ETE Parfaite : S1(140) - Tête(160) - S2(141)
        prices = [
            100, 120, 140, 130, 120,      # Épaule Gauche (Pic à 140)
            130, 150, 160, 150, 130,      # Tête (Pic à 160)
            120, 130, 141, 130, 110       # Épaule Droite (Pic à 141 ~ 140)
        ]
        # Note: Scipy find_peaks a besoin d'assez de points auteur pour définir un pic.
        # On ajoute du "bruit" autour pour aider la détection
        
        ohlcv = self.create_fake_ohlcv(prices)
        result = analyze_market(ohlcv)
        
        print(f"Patterns trouvés : {result['patterns']}")
        self.assertIn("ETE_BEARISH_POTENTIAL", result['patterns'])

    def test_no_pattern(self):
        print("\n🧪 TEST: Tendance Haussière Simple (Pas de pattern)")
        prices = [100, 110, 120, 130, 140, 150, 160, 170, 180]
        ohlcv = self.create_fake_ohlcv(prices)
        result = analyze_market(ohlcv)
        
        print(f"Patterns trouvés : {result['patterns']}")
        self.assertEqual(result['patterns'], [])

if __name__ == '__main__':
    unittest.main()
