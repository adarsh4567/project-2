from pydantic import BaseModel,Field
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from analyst.state import AgentState
import torch

tokenizer = AutoTokenizer.from_pretrained("yiyanghkust/finbert-tone")
model = AutoModelForSequenceClassification.from_pretrained("yiyanghkust/finbert-tone")


def sentiment_node(state: AgentState) -> AgentState:
    
    news = state["news"]

    inputs = tokenizer(news, return_tensors="pt", padding=True, truncation=True, max_length=512)
        
    with torch.no_grad():
            outputs = model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
    labels = ["Neutral", "Positive", "Negative"]
    predicted_class = torch.argmax(predictions, dim=1).item()
    
    return {
          "sentiment":labels[predicted_class],
          "sentimentflag":True
    }

    