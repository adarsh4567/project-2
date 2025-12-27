from analyst.state import AgentState
from analyst.sentiment_analyzer.node import sentiment_node
from analyst.entity_recognizer.node import entity_node
from langgraph.graph import StateGraph, START, END
from typing import Literal,Generator
from langgraph.prebuilt import ToolNode
from analyst.entity_recognizer.tools.search import search_tool
from analyst.entity_recognizer.tools.finsearch import stock_tool
from analyst.investment_analyzer.tools.yfinance_tool import recent_news
from analyst.investment_analyzer.node import investment_node
# from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessageChunk


def should_continue(state:AgentState) -> Literal["tools","investment_advice"]:
   """
    Routing function to determine next step:
    - If last message has tool calls -> go to tools node
    - Otherwise -> end the graph
   """
   messages = state.get("messages", [])

   if not messages:
        return "investment_advice"
   
   last_message = messages[-1]

   if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
   return "investment_advice" 

def should_continue_last(state:AgentState) -> Literal["newstools","end"]:
   """
    Routing function to determine next step:
    - If last message has tool calls -> go to news_tools node
    - Otherwise -> end the graph
   """
   messages = state.get("messages", [])

   if not messages:
        return "end"
   
   last_message = messages[-1]

   if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            if tool_call.get("name") == "recent_news":
                return "newstools"
        
   return "end" 




class FinancialAgent:

    def __init__(self):
        self.runnable = self.build_graph()


    def build_graph(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("sentiment_node",sentiment_node)
        workflow.add_node("entity_node",entity_node)
        workflow.add_node("tools",ToolNode([search_tool,stock_tool]))
        workflow.add_node("newstools",ToolNode([recent_news]))
        workflow.add_node("investment_node",investment_node)

        # parallel node execution
        workflow.add_edge(START,"sentiment_node")
        workflow.add_edge(START,"entity_node")


        workflow.add_conditional_edges(
        "entity_node",
        should_continue,
            {
                "tools": "tools",
                "investment_advice": "investment_node"
            }
        )
        workflow.add_edge("sentiment_node","investment_node")
        workflow.add_conditional_edges(
            "investment_node",
            should_continue_last,
            {
                "newstools":"newstools",
                "end":END
            }

        )
        workflow.add_edge("tools", "entity_node")
        workflow.add_edge("newstools","investment_node")
        return workflow.compile()
    



agent = FinancialAgent()

graph = agent.build_graph()


