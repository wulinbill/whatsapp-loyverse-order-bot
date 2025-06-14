from langchain.agents import initialize_agent, AgentType, Tool
from langchain.memory import ConversationBufferMemory
from langchain.chat_models import ChatOpenAI
import gpt_tools
from utils.logger import get_logger

logger = get_logger(__name__)

# A single shared OpenAI client instance – thread-safe according to the
# official Python SDK documentation.
llm = ChatOpenAI(model_name="gpt-4o", temperature=0, request_timeout=30)

tools = [
    Tool(name="ParseOrder", func=gpt_tools.tool_parse_order, description="解析客户点餐内容为 JSON"),
    Tool(name="SubmitOrder", func=gpt_tools.tool_submit_order, description="提交订单到 Loyverse POS")
]

def get_agent():
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    return initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        verbose=False,
        memory=memory,
    )
