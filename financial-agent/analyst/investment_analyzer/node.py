from analyst.state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage,HumanMessage
from analyst.investment_analyzer.tools.yfinance_tool import recent_news
from dotenv import load_dotenv
load_dotenv()
import os

current_dir = os.path.dirname(__file__)
prompt_path = os.path.join(current_dir, "prompt", "prompt.md")

with open(prompt_path, "r") as f:
    prompt = f.read()



llm = ChatGoogleGenerativeAI(
    model="gemini-flash-lite-latest",
    temperature=0
)

def _format_stock_report(stockReport: dict) -> str:
    """Format stock report for better readability in prompt"""
    formatted = []
    
    for ticker, metrics in stockReport.items():
        formatted.append(f"\n**{ticker}:**")
        formatted.append(f"  Current Price: {metrics.get('CurrentPrice', 'N/A')}")
        formatted.append(f"  P/E Ratio: {metrics.get('PERatio', 'N/A')}")
        formatted.append(f"  PEG Ratio: {metrics.get('PEGRatio', 'N/A')}")
        formatted.append(f"  Price to Book: {metrics.get('PriceToBookRatio', 'N/A')}")
        formatted.append(f"  Price to Sales (TTM): {metrics.get('PriceToSalesRatioTTM', 'N/A')}")
        formatted.append(f"  EPS: {metrics.get('EPS', 'N/A')}")
        formatted.append(f"  Profit Margin: {metrics.get('ProfitMargin', 'N/A')}")
        formatted.append(f"  Gross Profit Margin (TTM): {metrics.get('GrossProfitMarginTTM', 'N/A')}")
        formatted.append(f"  Return on Equity (TTM): {metrics.get('ReturnOnEquityTTM', 'N/A')}")
        formatted.append(f"  Revenue (TTM): {metrics.get('RevenueTTM', 'N/A')}")
        formatted.append(f"  Operating Cashflow: {metrics.get('OperatingCashflow', 'N/A')}")
        formatted.append(f"  Net Income: {metrics.get('NetIncome', 'N/A')}")
        formatted.append(f"  Gross Profit (TTM): {metrics.get('GrossProfitTTM', 'N/A')}")
    
    return '\n'.join(formatted)


investment_llm = llm.bind_tools([recent_news])

async def investment_node(state: AgentState) -> AgentState:
    """
    Final investment analysis node that:
    1. Waits for both sentiment and entity nodes to complete
    2. Uses yfinance tool ONCE to fetch news for all tickers
    3. Analyzes financial metrics + news + sentiment
    4. Generates final investment recommendations (INVEST/WAIT/AVOID)
    """
    
    # Ensure both upstream nodes have completed
    if not (state['sentimentflag'] and state["entityflag"]):
        # Not ready yet - wait for upstream nodes
        return {}
    
    # Extract data from state
    tickers = state["tickers"]
    sectors = state["sectors"]
    sentiment = state["sentiment"]
    stockReport = state["stockReport"]
    messages = state["messages"]
    
    # # Validate we have necessary data
    if not tickers or not stockReport:
        return {
            "advice": "ERROR: Insufficient data. Cannot give advice"
        }
    
    # # STAGE 1: Initialize conversation with data
    
    investment_message = [
            SystemMessage(content=prompt),
            HumanMessage(
                content=f"""Analyze the following information for investment advice:

                **Tickers:** {tickers}

                **Sectors:** {sectors}

                **Current Sentiment:** {sentiment}

                **Stock Report (Financial Metrics):**
                {_format_stock_report(stockReport)}
                """
            )
    ]

    new_message = messages + investment_message
                    
    # # STAGE 2 or 3: Invoke LLM
    response =  await investment_llm.ainvoke(new_message)
    messages.append(response)
    raw_response = response.content
    state["messages"] = messages 

    if not response.tool_calls:
        return {
            "advice": raw_response
        }
    
    
    return {
       "messages":messages 
    }