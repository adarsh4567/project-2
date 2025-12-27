from langchain_core.tools import tool
from typing import List
from dotenv import load_dotenv
import asyncio
import aiohttp

load_dotenv()

categories = ["INCOME_STATEMENT","OVERVIEW","GLOBAL_QUOTE","CASH_FLOW"]

async def fetch_category_async(session,category,stock):
    try:
        async with session.get(f"https://www.alphavantage.co/query?function={category}&symbol={stock}&apikey=ZM4GXRDR29MSZEDN",timeout=5) as response:
            response.raise_for_status()
            return category, await response.json()
    except aiohttp.ClientError as e:
        return category, f"Error: {e}"    

@tool
async def stock_tool(tickers:List[str]) -> dict:
    """
    Return a dict of stock metrics for the available tickers.
    """
    if not tickers:
        return {
            "stockReport":{}
        }
    
    final_dict={
    "AAPL": {
        "NetIncome": "97400000000",
        "GrossProfit": "170000000000",
        "PERatio": "28.5",
        "PEGRatio": "1.45",
        "EPS": "6.12",
        "ProfitMargin": "25.3",
        "ReturnOnEquityTTM": "145.2",
        "RevenueTTM": "385000000000",
        "GrossProfitTTM": "170000000000",
        "GrossProfitMarginTTM": 44.15,
        "PriceToBookRatio": "40.7",
        "PriceToSalesRatioTTM": "7.2",
        "OperatingCashflow": "115000000000",
        "CurrentPrice": "185.32"
    }
    }



    # for x in tickers:
    #     ticker_data = {}
    #     async with aiohttp.ClientSession() as session:
    #         tasks = [fetch_category_async(session,category,x) for category in categories]
    #         results = await asyncio.gather(*tasks)
    #         for category, result in results:
    #             match category:
    #                 case "INCOME_STATEMENT":
    #                     ticker_data["NetIncome"] = result["annualReports"][0]["netIncome"]
    #                     ticker_data["GrossProfit"] = result["annualReports"][0]["grossProfit"]
    #                 case "OVERVIEW":
    #                     ticker_data["PERatio"] = result["PERatio"]
    #                     ticker_data["PEGRatio"] = result["PEGRatio"]
    #                     ticker_data["EPS"] = result["EPS"]
    #                     ticker_data["ProfitMargin"] = result["ProfitMargin"]  
    #                     ticker_data["ReturnOnEquityTTM"] = result["ReturnOnEquityTTM"]
    #                     ticker_data["RevenueTTM"] = result["RevenueTTM"]
    #                     ticker_data["GrossProfitTTM"] = result["GrossProfitTTM"]
    #                     ticker_data["GrossProfitMarginTTM"] = (int(result["GrossProfitTTM"])/int(result["RevenueTTM"]))*100
    #                     ticker_data["PriceToBookRatio"] = result["PriceToBookRatio"]
    #                     ticker_data["PriceToSalesRatioTTM"] = result["PriceToSalesRatioTTM"]
    #                     ticker_data["ReturnOnEquityTTM"] = result["ReturnOnEquityTTM"]
    #                 case "CASH_FLOW":
    #                     ticker_data["OperatingCashflow"] = result["annualReports"][0]["operatingCashflow"]
    #                 case "GLOBAL_QUOTE":
    #                     ticker_data["CurrentPrice"] = result["Global Quote"]["05. price"]

    #         final_dict[x] = ticker_data                

    return {
        "stockReport": final_dict
    }                         
                
