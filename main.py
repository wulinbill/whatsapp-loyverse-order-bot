#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kong Food Restaurant WhatsApp订餐机器人
使用Claude AI进行智能对话处理
"""

import os
import sys
from src.app import create_app

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# 创建Flask应用实例
app = create_app()

if __name__ == '__main__':
    # 开发环境配置
    port = int(os.getenv('PORT', 10000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    print(f"🍜 Kong Food Restaurant Bot starting on port {port}")
    print(f"🤖 Using Claude AI for intelligent conversations")
    print(f"🌐 Debug mode: {debug}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )
