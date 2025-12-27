from typing import Literal,TypedDict,List,Annotated
from langgraph.graph import add_messages


class AgentState(TypedDict):
    sentiment: str = ""
    news: str
    tickers: List[str] = []
    sectors: List[str] = []
    messages: Annotated[list, add_messages]
    sentimentflag: bool
    entityflag: bool
    stockReport: dict = {}
    advice: str = ""
    recentnews: dict = {}
