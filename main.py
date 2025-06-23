#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kong Food Restaurant WhatsApp订餐机器人
使用Claude AI进行智能对话处理
"""

import os
import sys
import logging

# 确保正确的Python路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')

# 添加src目录到Python路径
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# 设置环境变量以确保模块能找到彼此
os.environ['PYTHONPATH'] = src_dir + ':' + os.environ.get('PYTHONPATH', '')

try:
    from app import create_app
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    print(f"Contents of current dir: {os.listdir('.')}")
    if os.path.exists('src'):
        print(f"Contents of src dir: {os.listdir('src')}")
    raise

# 创建Flask应用实例
app = create_app()

if __name__ == '__main__':
    # 配置日志记录
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 从环境变量获取端口，默认为 8080
    port = int(os.environ.get("PORT", 8080))
    
    # 使用 waitress 作为生产服务器
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
    
    # for development:
    # app.run(host="0.0.0.0", port=port, debug=True)
