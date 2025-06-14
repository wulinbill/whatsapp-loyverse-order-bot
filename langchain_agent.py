"""LangChain Agent 配置模块"""
import os
from typing import Dict, Any, Optional
from langchain.agents import initialize_agent, AgentType, Tool
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.schema import BaseMemory
import gpt_tools
from utils.logger import get_logger

logger = get_logger(__name__)

# 确保 OpenAI API Key 存在
openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    raise RuntimeError("Environment variable OPENAI_API_KEY is required but missing.")

# 全局 LLM 实例 - 根据官方文档，OpenAI 客户端是线程安全的
llm = ChatOpenAI(
    model_name="gpt-4o",
    temperature=0.1,  # 降低随机性，提高一致性
    request_timeout=60,  # 增加超时时间
    max_retries=2,  # 设置重试次数
    openai_api_key=openai_key
)

# 定义可用工具
tools = [
    Tool(
        name="ParseOrder",
        func=gpt_tools.tool_parse_order,
        description=gpt_tools.TOOL_DESCRIPTIONS["ParseOrder"]
    ),
    Tool(
        name="SubmitOrder",
        func=gpt_tools.tool_submit_order,
        description=gpt_tools.TOOL_DESCRIPTIONS["SubmitOrder"]
    ),
    Tool(
        name="GetMenu",
        func=gpt_tools.tool_get_menu,
        description=gpt_tools.TOOL_DESCRIPTIONS["GetMenu"]
    )
]

# 用于存储每个用户会话的内存
_user_memories: Dict[str, BaseMemory] = {}

def get_agent(user_id: str = "default"):
    """获取或创建指定用户的 LangChain Agent
    
    每个用户维护独立的对话记忆，实现会话隔离
    
    Args:
        user_id: 用户标识符，用于区分不同用户的会话
        
    Returns:
        配置好的 LangChain Agent 实例
    """
    try:
        # 获取或创建用户专属的内存
        if user_id not in _user_memories:
            logger.debug("为用户 %s 创建新的对话记忆", user_id)
            _user_memories[user_id] = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                max_token_limit=4000  # 限制记忆长度，避免上下文过长
            )
        
        memory = _user_memories[user_id]
        
        # 创建 Agent
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=False,  # 生产环境关闭详细日志
            memory=memory,
            max_iterations=5,  # 限制最大迭代次数，防止无限循环
            early_stopping_method="generate",  # 改进的停止策略
            handle_parsing_errors=True,  # 自动处理解析错误
        )
        
        logger.debug("成功获取用户 %s 的 Agent", user_id)
        return agent
        
    except Exception as e:
        logger.error("创建 Agent 失败: %s", e, exc_info=True)
        raise RuntimeError(f"无法创建 LangChain Agent: {e}")


def clear_user_memory(user_id: str) -> bool:
    """清除指定用户的对话记忆
    
    Args:
        user_id: 用户标识符
        
    Returns:
        是否成功清除记忆
    """
    try:
        if user_id in _user_memories:
            _user_memories[user_id].clear()
            logger.info("已清除用户 %s 的对话记忆", user_id)
            return True
        else:
            logger.warning("用户 %s 没有对话记忆需要清除", user_id)
            return False
    except Exception as e:
        logger.error("清除用户 %s 的对话记忆失败: %s", user_id, e)
        return False


def get_user_memory_stats(user_id: str) -> Optional[Dict[str, Any]]:
    """获取用户对话记忆统计信息
    
    Args:
        user_id: 用户标识符
        
    Returns:
        记忆统计信息字典，如果用户不存在则返回 None
    """
    try:
        if user_id not in _user_memories:
            return None
        
        memory = _user_memories[user_id]
        chat_history = memory.chat_memory.messages if hasattr(memory, 'chat_memory') else []
        
        return {
            "user_id": user_id,
            "message_count": len(chat_history),
            "has_memory": len(chat_history) > 0
        }
    except Exception as e:
        logger.error("获取用户 %s 记忆统计失败: %s", user_id, e)
        return None


def cleanup_old_memories(max_users: int = 100):
    """清理过多的用户记忆，防止内存泄漏
    
    Args:
        max_users: 最大保留的用户数量
    """
    try:
        if len(_user_memories) > max_users:
            # 简单的 FIFO 清理策略
            users_to_remove = list(_user_memories.keys())[:-max_users]
            for user_id in users_to_remove:
                del _user_memories[user_id]
                logger.debug("清理用户 %s 的记忆", user_id)
            
            logger.info("清理了 %d 个用户的记忆，当前保留 %d 个用户", 
                       len(users_to_remove), len(_user_memories))
    except Exception as e:
        logger.error("清理用户记忆失败: %s", e)


# 系统提示，帮助 Agent 理解其角色
SYSTEM_PROMPT = """
你是一个智能餐厅点餐助手，专门帮助客户通过 WhatsApp 下订单。

你的主要功能：
1. 理解客户的自然语言点餐需求
2. 解析订单并转换为标准格式
3. 将订单提交到 POS 系统
4. 为客户提供友好的服务体验

工作流程：
1. 当客户发送订单时，使用 ParseOrder 工具解析订单内容
2. 确认订单信息无误后，使用 SubmitOrder 工具提交订单
3. 如需查看菜单，使用 GetMenu 工具获取可用菜品

注意事项：
- 始终以友好、专业的态度与客户交流
- 在提交订单前确认客户的选择
- 如果解析出现问题，礼貌地要求客户重新描述订单
- 支持中文、英文和西班牙语交流
"""
