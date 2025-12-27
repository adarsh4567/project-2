from analyst.state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage,HumanMessage
import os
import json
from analyst.entity_recognizer.tools.search import search_tool
from analyst.entity_recognizer.tools.finsearch import stock_tool
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


enitity_llm = llm.bind_tools([search_tool,stock_tool])

async def entity_node(state: AgentState) -> AgentState:
    news = state["news"]
    messages = state.get("messages", [])

    # first message in the list
    if not messages:
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Analyze this financial news:\n\n{news}")
        ]

    response = await enitity_llm.ainvoke(messages)
    messages.append(response)
    raw_response = response.content
    state["messages"] = messages

    # Ready with final Response
    if not response.tool_calls:
        json_start = raw_response.find('{')
        json_end = raw_response.rfind('}') + 1
            
        if json_start != -1 and json_end > json_start:
            json_str = raw_response[json_start:json_end]
            result = json.loads(json_str)
            return {
                "tickers":result.get("tickers", []),
                "sectors":result.get("sectors", []),
                "entityflag":True,
                "stockReport": result.get("stockReport", {})
                
            }
 
    return {
        "messages":messages
    }