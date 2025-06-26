# 🤖 WhatsApp订餐机器人

基于Claude AI的多语言WhatsApp订餐机器人，支持语音识别和智能订单处理。专为Kong Food Restaurant设计，可部署在Render服务器运行。

## 🌟 功能特性

- 🤖 **Claude AI驱动** - 使用最新的Claude 4模型进行自然语言理解
- 🗣️ **语音支持** - Deepgram Nova-3语音转文字，支持多语言
- 🍽️ **智能菜单** - 模糊搜索，别名匹配，智能推荐
- 🛒 **订单管理** - 自动处理订单，Loyverse POS集成
- 🌍 **多语言支持** - 主要支持西班牙语，兼容中文和英文
- 📱 **双平台支持** - Twilio (测试) 和 360Dialog (生产)
- 🔍 **智能匹配** - 结合模糊搜索和向量搜索确保100%准确匹配
- 📊 **完整日志** - 结构化JSON日志，便于问题追踪

## 🏗️ 系统架构

```
WhatsApp消息 → 语音转文字 → 菜单匹配 → Claude分析 → POS下单 → 确认回复
     ↓              ↓           ↓          ↓        ↓        ↓
   Webhook    → Deepgram  → 模糊搜索   → Claude4 → Loyverse → WhatsApp
              → (Nova-3)  → 向量搜索   → (Opus)  → (OAuth) → (API)
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd whatsapp_order_bot

# 安装依赖
pip install -r requirements.txt

# 复制配置文件
cp .env.example .env
```

### 2. 配置环境变量

编辑 `.env` 文件：

```bash
# Claude AI配置
CLAUDE_API_KEY=sk-ant-xxx
CLAUDE_MODEL=claude-4-opus-20250514

# Deepgram语音转文字
DEEPGRAM_API_KEY=dgxxx
DEEPGRAM_MODEL=nova-3

# Loyverse POS系统
LOYVERSE_CLIENT_ID=xxx
LOYVERSE_CLIENT_SECRET=xxx
LOYVERSE_REFRESH_TOKEN=xxx
LOYVERSE_STORE_ID=your-store-id
LOYVERSE_POS_DEVICE_ID=your-pos-device-id

# WhatsApp配置 (选择一个)
CHANNEL_PROVIDER=twilio  # 或 dialog360

# Twilio (测试环境)
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# 360Dialog (生产环境)
DIALOG360_TOKEN=xxx
DIALOG360_PHONE_NUMBER=xxx

# 可选：向量搜索 (提升匹配准确性)
OPENAI_API_KEY=sk-xxx
POSTGRES_HOST=localhost
POSTGRES_DB=whatsapp_bot
POSTGRES_USER=postgres
POSTGRES_PASSWORD=xxx
```

### 3. 构建搜索索引

```bash
# 构建向量搜索索引 (可选但推荐)
python scripts/build_index.py
```

### 4. 启动应用

```bash
# 开发环境
python -m app.main

# 或使用Docker
docker-compose up
```

### 5. 配置Webhook

将webhook URL设置为：`https://your-domain.com/webhook/whatsapp`

## 📱 使用流程

### 典型对话流程

1. **问候** - "Hola, restaurante Kong Food. ¿Qué desea ordenar hoy?"

2. **点餐** - 用户: "Quiero 2 Pollo Teriyaki y 1 Pepper Steak"

3. **确认** - 系统确认菜品和价格

4. **询问姓名** - "Para finalizar, ¿podría indicarme su nombre, por favor?"

5. **完成订单** - 生成Loyverse订单，发送确认消息

### 支持的功能

- ✅ 文本订餐
- ✅ 语音订餐 (自动转文字)
- ✅ 菜品修改 (extra, poco, no, cambio)
- ✅ 搭配更换 (arroz+papa → arroz+tostones)
- ✅ 鸡肉部位指定 (cadera, muro, pechuga)
- ✅ 自动税费计算
- ✅ 厨房订单同步

## 🍽️ 菜单规则

### Kong Food特殊规则

1. **Combinaciones套餐**
   - 默认搭配: arroz + papa
   - 换搭配: "cambio tostones" → 添加额外收费项目

2. **Pollo Frito炸鸡**
   - 默认: 任意cadera和muro组合
   - 指定部位: "5 cadera, 3 muro, 2 pechuga" → 自动添加adicionales

3. **修饰符处理**
   - `extra ajo` → 查找"extra ajo"项目
   - `poco sal` → 查找"poco sal"项目
   - `no MSG` → 查找"no MSG"项目
   - `ajo aparte` → 查找"ajo aparte"项目

## 🔧 开发指南

### 项目结构

```
app/
├── main.py                 # FastAPI应用入口
├── config.py              # 配置管理
├── logger.py              # 日志系统
├── knowledge_base/        # 菜单知识库
│   └── menu_kb.json
├── llm/                   # Claude AI客户端
│   └── claude_client.py
├── speech/                # 语音处理
│   └── deepgram_client.py
├── utils/                 # 工具模块
│   ├── alias_matcher.py   # 模糊搜索
│   └── vector_search.py   # 向量搜索
├── pos/                   # POS系统集成
│   ├── loyverse_auth.py   # OAuth认证
│   ├── loyverse_client.py # API客户端
│   └── order_processor.py # 订单处理
└── whatsapp/              # WhatsApp集成
    ├── router.py          # 消息路由
    ├── twilio_adapter.py  # Twilio适配器
    └── dialog360_adapter.py # 360Dialog适配器
```

### 添加新菜品

1. 编辑 `app/knowledge_base/menu_kb.json`
2. 运行 `python scripts/build_index.py` 重建索引
3. 重启应用

### 自定义订餐规则

在 `app/pos/order_processor.py` 中修改以下方法：
- `_apply_combinaciones_rules()` - Combinaciones套餐规则
- `_apply_pollo_frito_rules()` - 炸鸡部位规则
- `_process_modifiers()` - 修饰符处理规则

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行集成测试
pytest tests/test_integration.py -v

# 测试特定功能
pytest tests/test_integration.py::TestWhatsAppIntegration::test_complete_order_flow -v
```

## 🚀 部署指南

### Render部署

1. **连接GitHub仓库**
   - 在Render控制台创建新的Web Service
   - 连接到你的GitHub仓库

2. **配置构建设置**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `./deploy/start.sh`

3. **设置环境变量**
   - 在Render控制台添加所有必要的环境变量
   - 确保设置 `ENVIRONMENT=production`

4. **健康检查**
   - Health Check Path: `/health`

### Docker部署

```bash
# 构建镜像
docker build -t whatsapp-bot .

# 运行容器
docker run -p 8000:8000 --env-file .env whatsapp-bot

# 或使用docker-compose
docker-compose up -d
```

### 环境配置

#### 开发环境
- 使用Twilio Sandbox
- 启用详细日志
- 禁用向量搜索（可选）

#### 生产环境
- 使用360Dialog正式号码
- JSON结构化日志
- 启用所有功能

## 📊 监控和日志

### 日志结构

每个操作都会记录结构化日志：

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "logger": "whatsapp_bot.business",
  "stage": "llm",
  "user_id": "+1234567890",
  "duration_ms": 1500,
  "data": {
    "model": "claude-4-opus-20250514",
    "prompt_tokens": 150
  }
}
```

### 监控端点

- `GET /health` - 健康检查
- `POST /admin/cleanup-sessions` - 清理过期会话
- `POST /admin/rebuild-index` - 重建向量索引
- `GET /admin/stats` - 获取统计信息

### 日志阶段

- `inbound` - 入站消息处理
- `speech` - 语音转文字
- `llm` - Claude AI处理
- `match` - 菜单匹配
- `pos` - POS系统操作
- `outbound` - 出站消息发送
- `auth` - 认证和token刷新
- `error` - 错误处理

## 🔒 安全考虑

### API密钥管理
- 所有密钥存储在环境变量中
- 生产环境使用密钥管理服务
- 定期轮换API密钥

### Webhook安全
- 验证webhook签名（Twilio/360Dialog）
- 使用HTTPS
- 限制来源IP（如果可能）

### 数据保护
- 客户信息加密存储
- 遵守GDPR/CCPA规定
- 定期清理过期会话

## 🛠️ 故障排除

### 常见问题

#### 1. Claude API错误
```bash
# 检查API密钥
curl -H "Authorization: Bearer $CLAUDE_API_KEY" https://api.anthropic.com/v1/messages

# 检查配额和限制
```

#### 2. Loyverse连接失败
```bash
# 测试认证
python -c "
from app.pos.loyverse_auth import loyverse_auth
import asyncio
print(asyncio.run(loyverse_auth.test_authentication()))
"

# 检查token信息
python -c "
from app.pos.loyverse_auth import loyverse_auth
print(loyverse_auth.get_token_info())
"
```

#### 3. 菜单匹配问题
```bash
# 重建搜索索引
python scripts/build_index.py

# 测试匹配
python -c "
from app.utils.alias_matcher import alias_matcher
matches = alias_matcher.find_matches('pollo teriyaki', 'test')
print([m['item_name'] for m in matches[:3]])
"
```

#### 4. 语音转录失败
- 检查Deepgram API密钥
- 验证音频格式支持
- 检查网络连接

### 调试模式

```bash
# 启用详细日志
export LOG_LEVEL=DEBUG

# 测试单个组件
python -m app.llm.claude_client
python -m app.speech.deepgram_client
python -m app.pos.loyverse_client
```

## 📈 性能优化

### 响应时间优化
- 使用后台任务处理webhook
- 缓存频繁查询的菜单项
- 优化数据库查询

### 成本控制
- 限制Claude API调用频率
- 使用模糊搜索减少向量搜索
- 合理设置token刷新时间

### 扩展建议
- 使用Redis管理会话状态
- 实现消息队列处理
- 添加负载均衡

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

### 代码规范
- 使用type hints
- 遵循PEP 8
- 添加docstrings
- 编写测试用例

## 📄 许可证

本项目采用MIT许可证。详见 [LICENSE](LICENSE) 文件。

## 🆘 支持

- 📧 技术支持: [your-email@example.com]
- 📖 文档: [项目Wiki]
- 🐛 问题反馈: [GitHub Issues]

## 🔄 更新日志

### v1.0.0 (2024-01-01)
- ✨ 初始版本发布
- 🤖 Claude 4集成
- 🗣️ Deepgram语音支持
- 🛒 Loyverse POS集成
- 📱 Twilio/360Dialog支持

---

**Kong Food Restaurant** - 让订餐更智能 🍽️
