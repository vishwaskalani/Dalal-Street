import math

class StockRanker:
    """
    Calculates a custom-weighted investment allocation metric (5-10) 
    based on 11 fundamental, technical, and qualitative parameters.
    """
    
    def __init__(self, weights: dict):
        """
        Initializes the ranker with a specific set of weights.
        The weights must sum to 1.0.
        """
        self.weights = weights
        self._validate_weights()

    def _validate_weights(self):
        """Ensures the weights sum to approximately 1.0."""
        total_weight = sum(self.weights.values())
        if not math.isclose(total_weight, 1.0):
            raise ValueError(f"Weights must sum to 1.0. Current sum: {total_weight}")

    # --- 1. Scoring Functions (Normalized to 0-100) ---
    # These functions convert raw data into a standardized 0-100 score.
    # 100 is "best" (e.g., low debt, high growth), 0 is "worst".

    def _score_pe_ratio(self, stock_pe: float, industry_pe: float) -> float:
        """
        Scores PE ratio relative to industry.
        Lower is better (value). Capped at 0.7x (score 100) and 2.0x (score 0).
        """
        if stock_pe <= 0 or industry_pe <= 0:
            return 0.0  # Loss-making or invalid data
        
        ratio = stock_pe / industry_pe
        
        if ratio <= 0.7:
            return 100.0
        if ratio >= 2.0:
            return 0.0
        
        # Linear interpolation between 0.7 (100) and 2.0 (0)
        return 100.0 * (2.0 - ratio) / (2.0 - 0.7)

    def _score_peg_ratio(self, peg_ratio: float) -> float:
        """
        Scores PEG ratio. Lower is better.
        Ideal <= 0.8 (score 100). Poor >= 2.0 (score 0).
        """
        if peg_ratio <= 0:
            return 0.0  # No growth or no earnings
        
        if peg_ratio <= 0.8:
            return 100.0
        if peg_ratio >= 2.0:
            return 0.0
            
        # Linear interpolation between 0.8 (100) and 2.0 (0)
        return 100.0 * (2.0 - peg_ratio) / (2.0 - 0.8)

    def _score_rsi(self, rsi: float) -> float:
        """
        Scores RSI. Lower (oversold) is a better *entry point*.
        Ideal <= 30 (score 100). Poor >= 70 (score 0).
        """
        if rsi <= 30.0:
            return 100.0
        if rsi >= 70.0:
            return 0.0
            
        # Linear interpolation between 30 (100) and 70 (0)
        return 100.0 * (70.0 - rsi) / (70.0 - 30.0)

    def _score_debt_to_equity(self, de_ratio: float) -> float:
        """
        Scores Debt-to-Equity. Lower is better.
        Ideal <= 0.1 (score 100). Poor >= 2.0 (score 0).
        (Note: This logic may not apply well to banking/NBFC stocks)
        """
        if de_ratio <= 0.1:
            return 100.0
        if de_ratio >= 2.0:
            return 0.0
            
        # Linear interpolation between 0.1 (100) and 2.0 (0)
        return 100.0 * (2.0 - de_ratio) / (2.0 - 0.1)

    def _score_profit_growth(self, profit_growth_3y_cagr: float) -> float:
        """
        Scores 3-year profit CAGR. Higher is better.
        Ideal >= 25% (score 100). Poor <= 0% (score 0).
        """
        if profit_growth_3y_cagr >= 25.0:
            return 100.0
        if profit_growth_3y_cagr <= 0.0:
            return 0.0
            
        # Linear interpolation between 0 (0) and 25 (100)
        return 100.0 * profit_growth_3y_cagr / 25.0

    def _score_human_rating_1_to_5(self, rating: int) -> float:
        """
        Generic helper to convert a 1-5 rating (where 5 is best) 
        to a 0-100 score.
        """
        if not 1 <= rating <= 5:
            raise ValueError(f"Rating must be between 1 and 5. Got: {rating}")
        
        # Maps 1->0, 2->25, 3->50, 4->75, 5->100
        return (rating - 1) * 25.0

    def _score_holdings(self, promoter: float, fii: float, dii: float) -> float:
        """
        Scores total "strong hands" holding. Higher is better.
        Total >= 80% (score 100). Total <= 40% (score 0).
        """
        total_strong_hands = promoter + fii + dii
        
        if total_strong_hands >= 80.0:
            return 100.0
        if total_strong_hands <= 40.0:
            return 0.0
            
        # Linear interpolation between 40 (0) and 80 (100)
        return 100.0 * (total_strong_hands - 40.0) / (80.0 - 40.0)

    def _score_holding_delta(self, promoter_delta: float, fii_delta: float, dii_delta: float) -> float:
        """
        Scores the change in holdings. Promoter buying is weighted most.
        Positive is good, negative is bad.
        """
        # Weighted delta: Promoter change is 2x as important as DII change.
        weighted_delta = (promoter_delta * 2.0) + (fii_delta * 1.5) + (dii_delta * 1.0)
        
        # Normalize: A score of +3.0 is 100, -3.0 is 0.
        if weighted_delta >= 3.0:
            return 100.0
        if weighted_delta <= -3.0:
            return 0.0
            
        # Linear interpolation between -3.0 (0) and 3.0 (100)
        return 100.0 * (weighted_delta + 3.0) / 6.0

    def _score_technicals(self, signal: str) -> float:
        """
        Scores a categorical technical signal.
        """
        signal_map = {
            "near support": 100.0,
            "nothing": 50.0,
            "near resistance": 0.0
        }
        
        if signal not in signal_map:
            raise ValueError(f"Invalid signal. Must be one of: {list(signal_map.keys())}")
            
        return signal_map.get(signal)

    # --- 2. Main Calculation Method ---

    def calculate_metric(self, data: dict) -> dict:
        """
        Calculates the final 5-10 allocation metric for a single stock.
        
        'data' dictionary must contain all 10 parameters:
        - stock_pe (float)
        - industry_pe (float)
        - peg_ratio (float)
        - rsi (float)
        - de_ratio (float)
        - profit_growth_3y_cagr (float)
        - consistency_rating (int 1-5)
        - promoter_holding (float)
        - fii_holding (float)
        - dii_holding (float)
        - promoter_delta (float)
        - fii_delta (float)
        - dii_delta (float)
        - capex_rating (int 1-5)
        - technical_signal (str: "near support", "near resistance", "nothing")
        """
        
        # --- A. Calculate normalized scores (0-100) for each parameter ---
        scores = {}
        try:
            scores['pe'] = self._score_pe_ratio(data['stock_pe'], data['industry_pe'])
            scores['peg'] = self._score_peg_ratio(data['peg_ratio'])
            scores['rsi'] = self._score_rsi(data['rsi'])
            scores['de'] = self._score_debt_to_equity(data['de_ratio'])
            scores['profit_growth'] = self._score_profit_growth(data['profit_growth_3y_cagr'])
            scores['consistency'] = self._score_human_rating_1_to_5(data['consistency_rating'])
            scores['holdings'] = self._score_holdings(data['promoter_holding'], data['fii_holding'], data['dii_holding'])
            scores['delta'] = self._score_holding_delta(data['promoter_delta'], data['fii_delta'], data['dii_delta'])
            scores['capex'] = self._score_human_rating_1_to_5(data['capex_rating'])
            scores['technicals'] = self._score_technicals(data['technical_signal'])
        
        except KeyError as e:
            print(f"Error: Missing data key: {e}")
            return None
        except ValueError as e:
            print(f"Error: Invalid data value: {e}")
            return None

        # --- B. Calculate the final weighted score (0-100) ---
        total_score = 0.0
        for key in self.weights:
            total_score += scores[key] * self.weights[key]
            
        # --- C. Scale the 0-100 score to the 5-10 allocation range ---
        # Formula: min_alloc + (score / 100) * (max_alloc - min_alloc)
        min_alloc = 5.0
        max_alloc = 10.0
        
        final_metric = min_alloc + (total_score / 100.0) * (max_alloc - min_alloc)
        
        # Return a full report
        return {
            "final_allocation_metric": round(final_metric, 2),
            "total_weighted_score": round(total_score, 2),
            "individual_scores": {k: round(v, 2) for k, v in scores.items()}
        }


# --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---
# --- --- --- --- ---  EXAMPLE USAGE  --- --- --- --- --- --- ---
# --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

if __name__ == "__main__":
    
    # --- STEP 1: Define your "human analysis" (the weights) ---
    # This is where you set your investment philosophy.
    # Weights MUST add up to 1.0
    
    my_weights = {
        # Fundamentals (Total: 0.55)
        'pe': 0.10,             # Value
        'peg': 0.10,            # Growth at a Reasonable Price
        'de': 0.10,             # Financial Risk
        'profit_growth': 0.10,  # Performance
        'consistency': 0.10,    # Quality (Human-rated)
        'holdings': 0.05,       # "Strong Hands"
        
        # Future / Delta (Total: 0.20)
        'delta': 0.10,          # Smart Money Movement
        'capex': 0.10,          # Future Growth (Human-rated)
        
        # Momentum / Timing (Total: 0.25 -> Adjusted for removal of hype)
        'rsi': 0.10,            # Technical Timing (Increased from 0.05)
        'technicals': 0.15      # Technical Timing (Increased from 0.10)
    }

    # --- STEP 2: Initialize the Ranker ---
    try:
        ranker = StockRanker(weights=my_weights)
    except ValueError as e:
        print(f"Error initializing ranker: {e}")
        exit()

    # --- STEP 3: Gather data for two different stocks ---
    
    # Example Stock 1: "GoodValueBuy"
    # A solid company that has been beaten down.
    stock_A_data = {
        "stock_pe": 15.0,
        "industry_pe": 25.0,         # (Good: lower than industry)
        "peg_ratio": 0.8,            # (Excellent)
        "rsi": 28.0,                 # (Good: oversold)
        "de_ratio": 0.3,             # (Excellent)
        "profit_growth_3y_cagr": 18.0, # (Good)
        "consistency_rating": 4,     # (Good: 4/5)
        "promoter_holding": 55.0,
        "fii_holding": 10.0,
        "dii_holding": 5.0,          # (Total: 70 - Good)
        "promoter_delta": 0.5,
        "fii_delta": 1.0,
        "dii_delta": 0.0,            # (Good: Promoter/FII buying)
        "capex_rating": 4,           # (Good: 4/5)
        "technical_signal": "near support" # (Excellent)
    }

    # Example Stock 2: "HypedGrowthStock"
    # A fast-growing company that everyone is talking about.
    stock_B_data = {
        "stock_pe": 60.0,
        "industry_pe": 30.0,         # (Bad: 2x industry)
        "peg_ratio": 2.1,            # (Bad)
        "rsi": 75.0,                 # (Bad: overbought)
        "de_ratio": 1.2,             # (Mediocre)
        "profit_growth_3y_cagr": 30.0, # (Excellent)
        "consistency_rating": 3,     # (Average: 3/5)
        "promoter_holding": 25.0,
        "fii_holding": 20.0,
        "dii_holding": 10.0,         # (Total: 55 - Average)
        "promoter_delta": -1.0,
        "fii_delta": 0.0,
        "dii_delta": -0.5,           # (Bad: Promoter/DII selling)
        "capex_rating": 5,           # (Excellent: 5/5)
        "technical_signal": "near resistance" # (Bad)
    }

    # --- STEP 4: Calculate metrics ---
    
    print("--- Calculating Metric for Stock A (GoodValueBuy) ---")
    metric_A = ranker.calculate_metric(stock_A_data)
    if metric_A:
        print(f"FINAL ALLOCATION METRIC: {metric_A['final_allocation_metric']}%")
        print(f"Total Weighted Score: {metric_A['total_weighted_score']} / 100")
        print("Individual Scores (0-100):")
        print(metric_A['individual_scores'])
    
    print("\n" + "---" * 20 + "\n")
    
    print("--- Calculating Metric for Stock B (HypedGrowthStock) ---")
    metric_B = ranker.calculate_metric(stock_B_data)
    if metric_B:
        print(f"FINAL ALLOCATION METRIC: {metric_B['final_allocation_metric']}%")
        print(f"Total Weighted Score: {metric_B['total_weighted_score']} / 100")
        print("Individual Scores (0-100):")
        print(metric_B['individual_scores'])