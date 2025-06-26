#!/usr/bin/env python3
"""
构建向量搜索索引的脚本

用法:
    python scripts/build_index.py

环境变量:
    OPENAI_API_KEY: OpenAI API密钥
    POSTGRES_HOST: PostgreSQL主机
    POSTGRES_DB: 数据库名称
    POSTGRES_USER: 数据库用户
    POSTGRES_PASSWORD: 数据库密码
"""

import asyncio
import sys
import os
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import get_settings
from app.logger import get_logger
from app.utils.vector_search import vector_search_client
from app.utils.alias_matcher import alias_matcher

logger = get_logger(__name__)

async def main():
    """主函数"""
    settings = get_settings()
    
    print("🚀 开始构建向量搜索索引...")
    print(f"📊 项目根目录: {project_root}")
    
    # 检查配置
    if not settings.openai_api_key:
        print("❌ 错误: 未配置 OPENAI_API_KEY")
        print("请设置环境变量: export OPENAI_API_KEY=your_api_key")
        return 1
    
    if not settings.postgres_password:
        print("⚠️  警告: 未配置PostgreSQL，将跳过向量索引构建")
        print("如需启用向量搜索，请配置以下环境变量:")
        print("  POSTGRES_HOST=your_host")
        print("  POSTGRES_DB=your_database")
        print("  POSTGRES_USER=your_user")
        print("  POSTGRES_PASSWORD=your_password")
        return 0
    
    print(f"🔗 OpenAI模型: {settings.openai_embedding_model}")
    print(f"🗄️  数据库: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")
    
    try:
        # 1. 检查菜单数据
        print("\n📋 检查菜单数据...")
        menu_file = project_root / "app" / "knowledge_base" / "menu_kb.json"
        
        if not menu_file.exists():
            print(f"❌ 错误: 菜单文件不存在: {menu_file}")
            return 1
        
        with open(menu_file, 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # 统计菜单项数量
        total_items = 0
        for category_name, category_data in menu_data.get("menu_categories", {}).items():
            if isinstance(category_data, dict) and "items" in category_data:
                items_count = len(category_data["items"])
                total_items += items_count
                print(f"  📁 {category_name}: {items_count} 个菜品")
        
        print(f"  📊 总计: {total_items} 个菜品")
        
        if total_items == 0:
            print("❌ 错误: 菜单中没有找到任何菜品")
            return 1
        
        # 2. 刷新别名匹配器数据
        print("\n🔄 刷新别名匹配器...")
        alias_matcher.refresh_menu_data()
        print(f"  ✅ 加载了 {len(alias_matcher.menu_items)} 个菜品到别名匹配器")
        
        # 3. 构建向量索引
        print("\n🧠 构建向量搜索索引...")
        print("  这可能需要几分钟时间，请耐心等待...")
        
        start_time = asyncio.get_event_loop().time()
        
        await vector_search_client.build_embeddings_index()
        
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        print(f"  ✅ 向量索引构建完成! 耗时: {duration:.1f}秒")
        
        # 4. 测试搜索功能
        print("\n🧪 测试搜索功能...")
        
        test_queries = [
            "pollo teriyaki",
            "chicken",
            "carne de res",
            "pepper steak",
            "arroz frito"
        ]
        
        for query in test_queries:
            print(f"  🔍 测试查询: '{query}'")
            
            # 测试别名匹配
            alias_matches = alias_matcher.find_matches(query, "test", limit=3)
            print(f"    别名匹配: {len(alias_matches)} 个结果")
            
            # 测试向量搜索
            vector_matches = await vector_search_client.search_similar_items(query, "test", limit=3)
            print(f"    向量搜索: {len(vector_matches)} 个结果")
            
            if alias_matches:
                best_match = alias_matches[0]
                print(f"    最佳匹配: {best_match.get('item_name')} (分数: {best_match.get('score', 0):.1f})")
        
        print("\n🎉 索引构建完成!")
        print("\n📝 后续步骤:")
        print("  1. 启动应用: python -m app.main")
        print("  2. 测试WhatsApp webhook")
        print("  3. 发送测试消息验证功能")
        
        return 0
        
    except Exception as e:
        logger.error(f"构建索引时发生错误: {e}", exc_info=True)
        print(f"\n❌ 错误: {e}")
        print("\n🛠️  故障排除:")
        print("  1. 检查网络连接")
        print("  2. 验证OpenAI API密钥")
        print("  3. 确认PostgreSQL连接参数")
        print("  4. 检查数据库权限")
        return 1

def check_dependencies():
    """检查依赖项"""
    print("🔍 检查依赖项...")
    
    try:
        import openai
        print(f"  ✅ OpenAI: {openai.__version__}")
    except ImportError:
        print("  ❌ OpenAI库未安装")
        return False
    
    try:
        import psycopg2
        print(f"  ✅ psycopg2: {psycopg2.__version__}")
    except ImportError:
        print("  ❌ psycopg2库未安装")
        return False
    
    try:
        import numpy
        print(f"  ✅ NumPy: {numpy.__version__}")
    except ImportError:
        print("  ❌ NumPy库未安装")
        return False
    
    return True

if __name__ == "__main__":
    print("🤖 WhatsApp订餐机器人 - 向量索引构建工具")
    print("=" * 50)
    
    # 检查依赖项
    if not check_dependencies():
        print("\n❌ 缺少必要的依赖项，请运行:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    
    # 运行主函数
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 未处理的错误: {e}")
        sys.exit(1)
