from langchain_core.tools import tool
from typing import List
import yfinance as yf
import asyncio

@tool
def recent_news(symbols: List[str]) -> dict:
    """
    return recent news for symbols
    """
    final_news = {}
    for x in symbols:
        company = yf.Ticker(x)
        news_items = company.get_news(count=3)
        summaries = [n["content"]["summary"] for n in news_items]
        final_news[x] = summaries

    return {"recentnews": final_news}




