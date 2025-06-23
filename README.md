# Kong Food Restaurant - WhatsApp AI 订餐机器人

基于Claude AI的多语言WhatsApp订餐机器人，支持语音识别和智能订单处理。

## 🌟 功能特性

- 🤖 **Claude AI驱动** - 使用最新的Claude模型进行自然语言理解
- 🗣️ **语音支持** - Deepgram语音转文字，支持多语言
- 🍽️ **智能菜单** - 模糊搜索，别名匹配，智能推荐
- 🛒 **订单管理** - 自动处理订单，Loyverse POS集成
- 🌍 **多语言** - 支持中文、西班牙语、英语

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd whatsapp-order-bot

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的API密钥
```

### 2. API配置

#### Claude AI
- 注册 [Anthropic](https://console.anthropic.com/)
- 获取API密钥并设置 `CLAUDE_API_KEY`

#### Twilio WhatsApp
- 配置 [Twilio WhatsApp Business](https://www.twilio.com/whatsapp)
- 设置webhook URL: `https://your-domain.com/sms`

#### Deepgram (语音转文字)
- 注册 [Deepgram](https://deepgram.com/)
- 获取API密钥

#### Loyverse POS
- 设置 [Loyverse](https://loyverse.com/) 账户
- 配置OAuth应用获取凭据

### 3. 本地运行

```bash
# 开发模式
python main.py

# 生产模式
gunicorn main:app --workers 2 --bind 0.0.0.0:10000
```

### 4. 部署到Render

```bash
# 推送到GitHub后，在Render中：
# 1. 连接GitHub仓库
# 2. 选择render.yaml配置
# 3. 设置环境变量
# 4. 部署
```

## 📁 项目结构

```
├── main.py                 # 应用入口
├── requirements.txt        # Python依赖
├── render.yaml            # Render部署配置
├── .env.example           # 环境变量示例
├── README.md              # 项目文档
├── src/
│   ├── __init__.py        # 包初始化
│   ├── app.py             # Flask应用
│   ├── claude_client.py   # Claude AI客户端
│   ├── agent.py           # 对话处理逻辑
│   ├── deepgram_utils.py  # 语音转文字
│   ├── loyverse_api.py    # Loyverse API
│   ├── loyverse_auth.py   # Loyverse认证
│   ├── order_processor.py # 订单处理
│   ├── tools.py           # 工具函数
│   ├── data/
│   │   └── menu_kb.json   # 菜单知识库
│   └── prompts/
│       └── system_prompt.txt # 系统提示词
└── tests/
    └── test_parser.py     # 单元测试
```

## 🔧 API端点

- `POST /sms` - WhatsApp消息处理
- `GET /health` - 健康检查
- `POST /clear-session/<phone>` - 清除用户会话

## 🧪 测试

```bash
# 运行测试
python -m pytest tests/ -v

# 测试特定功能
python tests/test_parser.py
```

## 📊 监控

查看应用状态：
```bash
curl https://your-domain.com/health
```

## 🔧 配置说明

### Claude 模型配置
- `claude-3-5-sonnet-20241022` - 推荐，平衡性能和成本
- `claude-3-opus-20240229` - 最高质量，成本较高
- `claude-3-haiku-20240307` - 最快速，成本最低

### 语音识别设置
- 支持多种音频格式 (ogg, mp3, wav)
- 自动语言检测
- 支持西班牙语、英语、中文

## 🛠️ 故障排除

### 常见问题

1. **Claude API错误**
   ```bash
   # 检查API密钥
   echo $CLAUDE_API_KEY
   # 检查额度和权限
   ```

2. **Twilio连接问题**
   ```bash
   # 验证webhook URL可访问
   curl -X POST https://your-domain.com/sms
   ```

3. **音频转录失败**
   - 检查Deepgram API密钥
   - 确认音频格式支持
   - 查看日志获取详细错误

### 日志查看

```bash
# 实时日志
tail -f /var/log/app.log

# 错误日志过滤
grep ERROR /var/log/app.log
```

## 🔐 安全注意事项

- 定期轮换API密钥
- 使用HTTPS进行所有通信
- 验证webhook来源
- 限制API调用频率

## 📈 性能优化

- 会话数据定期清理
- API调用缓存
- 错误重试机制
- 负载均衡配置

## 🤝 贡献

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

## 📄 许可证

MIT License - 详见LICENSE文件

## 📞 支持

如有问题请创建Issue或联系开发团队。
