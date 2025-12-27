from dotenv import load_dotenv
import os

load_dotenv()  # take environment variables from .env.


GOOGLE_API_KEY=os.getenv("GOOGLE_API_KEY", None)
LANGSMITH_API_KEY=os.getenv("LANGSMITH_API_KEY", None)
REDIS_URI=os.getenv("REDIS_URI", None)
DATABASE_URI=os.getenv("DATABASE_URI", None)


