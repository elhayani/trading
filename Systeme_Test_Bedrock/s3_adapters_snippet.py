
# In s3_adapters.py, we missed defining the MockResponse class inside the file or importing it.
# The previous write_to_file defined MockResponse inside the block.
# Wait, I see S3RequestsMock refers to MockResponse.
# But there was a logic error in S3RequestsMock.get method: it needs to return an object having .json() method.
# In the previous step, I defined MockResponse class at the end.
# However, S3RequestsMock.get signature needs to match requests.get signature approximately.
# Let's refine S3RequestsMock to be more robust.

class MockResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data
        
    def json(self):
        return self._json_data

class S3RequestsMock:
    def __init__(self, macro_map):
        self.macro_map = macro_map
        self.current_timestamp = None
        
    def set_timestamp(self, ts):
        self.current_timestamp = ts
        
    def get(self, url, params=None, headers=None, timeout=None):
        # Initial parsing logic
        symbol = None
        if '/v8/finance/chart/' in url:
            parts = url.split('/v8/finance/chart/')
            if len(parts) > 1:
                raw_symbol = parts[1].split('?')[0]
                symbol = raw_symbol.replace('%5E', '^')
        
        if symbol and symbol in self.macro_map:
            # Find data
            data = self.macro_map[symbol]
            price = 0.0
            prev = 0.0
            
            # Binary search or scan
            # Assuming data sorted
            idx = -1
            for i, c in enumerate(data):
                if c[0] > self.current_timestamp:
                    break
                idx = i
                
            if idx >= 0:
                price = data[idx][4]
                prev = data[max(0, idx-1)][4]
                
            return MockResponse(200, {
                'chart': {
                    'result': [{
                        'meta': {
                            'regularMarketPrice': price,
                            'chartPreviousClose': prev
                        },
                        'timestamp': [self.current_timestamp/1000],
                        'indicators': {
                            'quote': [{'close': [price]}]
                        }
                    }]
                }
            })
            
        return MockResponse(404, {})
