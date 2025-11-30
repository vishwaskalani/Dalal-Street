import streamlit as st
import math

# --- 1. The Core Logic (Your Class) ---
class StockRanker:
    """
    Calculates a custom-weighted investment allocation metric (5-10) 
    based on 10 fundamental, technical, and qualitative parameters.
    """
    
    def __init__(self, weights: dict):
        self.weights = weights
        self._validate_weights()

    def _validate_weights(self):
        total_weight = sum(self.weights.values())
        if not math.isclose(total_weight, 1.0, rel_tol=1e-5):
            st.error(f"⚠️ Configuration Error: Weights must sum to 1.0. Current sum: {total_weight}")
            st.stop()

    # --- Scoring Functions (0-100) ---
    def _score_pe_ratio(self, stock_pe: float, industry_pe: float) -> float:
        if stock_pe <= 0 or industry_pe <= 0: return 0.0
        ratio = stock_pe / industry_pe
        if ratio <= 0.7: return 100.0
        if ratio >= 2.0: return 0.0
        return 100.0 * (2.0 - ratio) / (2.0 - 0.7)

    def _score_peg_ratio(self, peg_ratio: float) -> float:
        if peg_ratio <= 0: return 0.0
        if peg_ratio <= 0.8: return 100.0
        if peg_ratio >= 2.0: return 0.0
        return 100.0 * (2.0 - peg_ratio) / (2.0 - 0.8)

    def _score_rsi(self, rsi: float) -> float:
        if rsi <= 30.0: return 100.0
        if rsi >= 70.0: return 0.0
        return 100.0 * (70.0 - rsi) / (70.0 - 30.0)

    def _score_debt_to_equity(self, de_ratio: float) -> float:
        if de_ratio <= 0.1: return 100.0
        if de_ratio >= 2.0: return 0.0
        return 100.0 * (2.0 - de_ratio) / (2.0 - 0.1)

    def _score_profit_growth(self, profit_growth: float) -> float:
        if profit_growth >= 25.0: return 100.0
        if profit_growth <= 0.0: return 0.0
        return 100.0 * profit_growth / 25.0

    def _score_human_rating(self, rating: int) -> float:
        return (rating - 1) * 25.0

    def _score_holdings(self, promoter: float, fii: float, dii: float) -> float:
        total = promoter + fii + dii
        if total >= 80.0: return 100.0
        if total <= 40.0: return 0.0
        return 100.0 * (total - 40.0) / (80.0 - 40.0)

    def _score_holding_delta(self, p_delta: float, f_delta: float, d_delta: float) -> float:
        weighted = (p_delta * 2.0) + (f_delta * 1.5) + (d_delta * 1.0)
        if weighted >= 3.0: return 100.0
        if weighted <= -3.0: return 0.0
        return 100.0 * (weighted + 3.0) / 6.0

    def _score_technicals(self, signal: str) -> float:
        mapping = {"near support": 100.0, "nothing": 50.0, "near resistance": 0.0}
        return mapping.get(signal, 50.0)

    # --- Calculation ---
    def calculate_metric(self, data: dict) -> dict:
        scores = {}
        scores['pe'] = self._score_pe_ratio(data['stock_pe'], data['industry_pe'])
        scores['peg'] = self._score_peg_ratio(data['peg_ratio'])
        scores['rsi'] = self._score_rsi(data['rsi'])
        scores['de'] = self._score_debt_to_equity(data['de_ratio'])
        scores['profit_growth'] = self._score_profit_growth(data['profit_growth_3y_cagr'])
        scores['consistency'] = self._score_human_rating(data['consistency_rating'])
        scores['holdings'] = self._score_holdings(data['promoter_holding'], data['fii_holding'], data['dii_holding'])
        scores['delta'] = self._score_holding_delta(data['promoter_delta'], data['fii_delta'], data['dii_delta'])
        scores['capex'] = self._score_human_rating(data['capex_rating'])
        scores['technicals'] = self._score_technicals(data['technical_signal'])

        total_score = sum(scores[k] * self.weights[k] for k in self.weights)
        
        # Scale 0-100 score to 5-10 allocation
        min_alloc, max_alloc = 5.0, 10.0
        final_metric = min_alloc + (total_score / 100.0) * (max_alloc - min_alloc)
        
        return {
            "final_allocation": round(final_metric, 2),
            "raw_score": round(total_score, 2),
            "breakdown": scores
        }

# --- 2. The Streamlit UI ---

st.set_page_config(page_title="Stock Allocator", page_icon="📈", layout="wide")

# --- Sidebar: Configuration ---
st.sidebar.header("⚙️ Investment Philosophy (Weights)")
st.sidebar.caption("Adjust these weights to change how the system prioritizes factors. Must sum to 1.0.")

# Default weights (from your logic)
weights = {
    'pe': st.sidebar.number_input("PE Weight (Value)", value=0.10, step=0.01),
    'peg': st.sidebar.number_input("PEG Weight (GARP)", value=0.10, step=0.01),
    'de': st.sidebar.number_input("D/E Weight (Risk)", value=0.10, step=0.01),
    'profit_growth': st.sidebar.number_input("Profit Growth Weight", value=0.10, step=0.01),
    'consistency': st.sidebar.number_input("Consistency Weight", value=0.10, step=0.01),
    'holdings': st.sidebar.number_input("Holdings Absolute Weight", value=0.05, step=0.01),
    'delta': st.sidebar.number_input("Holdings Change Weight", value=0.10, step=0.01),
    'capex': st.sidebar.number_input("Capex Plans Weight", value=0.10, step=0.01),
    'rsi': st.sidebar.number_input("RSI Weight (Timing)", value=0.10, step=0.01),
    'technicals': st.sidebar.number_input("Technicals Weight", value=0.15, step=0.01),
}

current_total = sum(weights.values())
if not math.isclose(current_total, 1.0, rel_tol=1e-3):
    st.sidebar.warning(f"⚠️ Weights sum to {current_total:.2f}. Please adjust to 1.00")

# --- Main Page ---
st.title("📈 Stock Allocation Ranker")
st.markdown("""
This tool calculates a **safe allocation percentage (5% - 10%)** for a fundamentally strong stock based on 
valuation, growth, institutional interest, and technical positioning.
""")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1. Valuation & Growth")
    stock_name = st.text_input("Stock Name", "Example Stock Ltd")
    stock_pe = st.number_input("Stock PE", value=15.0)
    industry_pe = st.number_input("Industry PE", value=25.0)
    peg_ratio = st.number_input("PEG Ratio", value=1.0)
    profit_growth = st.number_input("3Y Profit CAGR (%)", value=15.0)

with col2:
    st.subheader("2. Quality & Holdings")
    de_ratio = st.number_input("Debt to Equity", value=0.5)
    consistency = st.slider("Profit/Margin Consistency (1-5)", 1, 5, 4)
    capex = st.slider("Capex Plans (1-5)", 1, 5, 3)
    
    st.caption("Holdings (%)")
    c1, c2, c3 = st.columns(3)
    p_hold = c1.number_input("Promoter %", value=50.0)
    f_hold = c2.number_input("FII %", value=10.0)
    d_hold = c3.number_input("DII %", value=10.0)

with col3:
    st.subheader("3. Momentum & Changes")
    rsi = st.number_input("RSI (14)", value=50.0)
    tech_signal = st.selectbox("Technical Status", ["nothing", "near support", "near resistance"])
    
    st.caption("Change in Holdings (Last Qtr %)")
    d1, d2, d3 = st.columns(3)
    p_delta = d1.number_input("Promoter Δ", value=0.0)
    f_delta = d2.number_input("FII Δ", value=0.0)
    d_delta = d3.number_input("DII Δ", value=0.0)

# --- Calculation Button ---
st.divider()
if st.button("Calculate Allocation", type="primary", use_container_width=True):
    # Initialize Ranker
    try:
        ranker = StockRanker(weights)
        
        # Prepare Data
        data = {
            "stock_pe": stock_pe, "industry_pe": industry_pe,
            "peg_ratio": peg_ratio, "rsi": rsi,
            "de_ratio": de_ratio, "profit_growth_3y_cagr": profit_growth,
            "consistency_rating": consistency,
            "promoter_holding": p_hold, "fii_holding": f_hold, "dii_holding": d_hold,
            "promoter_delta": p_delta, "fii_delta": f_delta, "dii_delta": d_delta,
            "capex_rating": capex, "technical_signal": tech_signal
        }
        
        # Calculate
        result = ranker.calculate_metric(data)
        
        # --- Display Results ---
        st.success(f"Analysis Complete for {stock_name}")
        
        # Top Metrics
        m1, m2 = st.columns([1, 2])
        
        with m1:
            st.metric(label="Recommended Allocation", value=f"{result['final_allocation']}%")
            st.caption("Min: 5% | Max: 10%")
        
        with m2:
            st.subheader("What does this mean?")
            if result['final_allocation'] >= 9.0:
                st.write(f"🌟 **Aggressive Buy.** {stock_name} scores very high across all metrics. It is cheap, growing, and technically well-positioned.")
            elif result['final_allocation'] >= 7.5:
                st.write(f"✅ **Solid Buy.** {stock_name} is a strong candidate, but may be slightly weak in 1-2 areas (e.g., slightly overvalued or neutral technicals).")
            else:
                st.write(f"⚠️ **Cautious/Minimum Buy.** {stock_name} passes your fundamental screen, but current parameters (valuation/technicals) suggest keeping position size small ({result['final_allocation']}%) for now.")

        # Detailed Breakdown
        with st.expander("See Detailed Score Breakdown"):
            st.write("Scores are normalized to 0-100 (100 is best).")
            st.dataframe(result['breakdown'])

    except Exception as e:
        st.error(f"Error calculating metric: {e}")