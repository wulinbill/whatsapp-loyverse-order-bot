# WhatsApp → Loyverse AI 订餐机器人 v2.0

🍽️ **智能餐厅点餐助手** - 集成 Loyverse POS 系统的多语言 WhatsApp AI 订餐机器人

## ✨ 新版本特性

### 🔧 v2.0 重大改进
- ✅ **线程安全的会话管理** - 修复并发访问问题
- ✅ **统一配置管理** - 基于 Pydantic 的类型安全配置
- ✅ **增强的输入验证** - 防止 XSS 和注入攻击
- ✅ **优化的错误处理** - 更详细的错误信息和恢复机制
- ✅ **性能优化** - 智能缓存和异步处理优化
- ✅ **监控和统计** - 完整的运行状态监控
- ✅ **管理员接口** - 便于维护和调试的 API 端点

### 🌍 核心功能
- 🤖 **AI 驱动** - 使用 GPT-4o 进行智能订单解析
- 🗣️ **多语言支持** - 中文/英文/西班牙语无缝切换
- 📱 **WhatsApp 集成** - 通过 Twilio 实现 WhatsApp 消息处理
- 🏪 **POS 集成** - 直接对接 Loyverse POS 系统
- 💾 **会话管理** - 智能对话状态跟踪
- 🔒 **安全验证** - 输入验证和 webhook 安全机制

## 🚀 快速开始

### 环境要求
```bash
Python 3.8+
FastAPI
OpenAI API 访问权限
Loyverse POS 账户
Twilio WhatsApp Business API
```

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/your-repo/whatsapp-loyverse-bot.git
cd whatsapp-loyverse-bot
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥和配置
```

4. **启动应用**
```bash
# 开发环境
python main.py

# 生产环境
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## ⚙️ 配置说明

### 必需配置
```bash
# OpenAI API
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4o

# Loyverse POS
LOYVERSE_CLIENT_ID=your-client-id
LOYVERSE_CLIENT_SECRET=your-client-secret
LOYVERSE_REFRESH_TOKEN=your-refresh-token
LOYVERSE_STORE_ID=your-store-id
```

### 可选配置
```bash
# 缓存设置
MENU_CACHE_TTL=600          # 菜单缓存时间（秒）
SESSION_TTL=3600            # 会话过期时间（秒）

# 业务设置
DEFAULT_PREP_TIME_MINUTES=10     # 默认准备时间
LARGE_ORDER_THRESHOLD=3          # 大订单阈值
MAX_MESSAGE_LENGTH=1000          # 最大消息长度

# 系统设置
LOG_LEVEL=INFO              # 日志级别
DEBUG_MODE=false            # 调试模式
```

## 📋 API 端点

### 核心端点
- `POST /whatsapp-webhook` - WhatsApp 消息处理
- `POST /whatsapp-status` - 消息状态更新
- `GET /health` - 健康检查
- `GET /health/detailed` - 详细系统状态

### 管理端点
- `GET /menu` - 获取菜单
- `POST /menu/refresh` - 刷新菜单缓存
- `GET /stats` - 系统统计信息
- `POST /admin/cleanup` - 清理过期数据
- `GET/DELETE /admin/session/{user_id}` - 会话管理

## 🔄 对话流程

```
用户: "Hola, quiero un Pepper Pollo con tostones"
  ↓
🤖 AI 解析订单
  ↓
机器人: "Perfecto, Pepper Pollo con tostones x1. ¿Algo más?"
  ↓
用户: "No, eso es todo"
  ↓
机器人: "Para finalizar, ¿podría indicarme su nombre?"
  ↓
用户: "Juan Pérez"
  ↓
📋 生成 Loyverse 订单
  ↓
机器人: "Gracias, Juan. Su orden estará lista en 10 minutos."
```

## 🛠️ 技术架构

### 核心组件
```
📱 WhatsApp (Twilio) 
  ↓
🔄 FastAPI 应用
  ↓
🤖 GPT-4o 解析 → 🏪 Loyverse POS
  ↓
💾 会话存储 ← 📊 统计监控
```

### 关键模块
- **`whatsapp_handler.py`** - WhatsApp 消息处理和对话流程
- **`gpt_parser.py`** - AI 订单解析和菜单处理
- **`loyverse_api.py`** - Loyverse POS API 集成
- **`config.py`** - 统一配置管理
- **`utils/`** - 工具模块（验证、日志、会话）

## 📊 监控和调试

### 健康检查
```bash
curl http://localhost:8000/health/detailed
```

### 系统统计
```bash
curl http://localhost:8000/stats
```

### 查看用户会话
```bash
curl http://localhost:8000/admin/session/1234567890
```

### 清理系统缓存
```bash
curl -X POST http://localhost:8000/admin/cleanup
```

## 🔒 安全特性

- ✅ **输入验证** - 防止 XSS 和注入攻击
- ✅ **会话安全** - 线程安全的会话管理
- ✅ **API 限流** - 防止滥用和攻击
- ✅ **Webhook 验证** - Twilio 签名验证支持
- ✅ **敏感信息保护** - 日志中的敏感信息自动清理

## 🧪 测试

### 单元测试
```bash
pytest tests/ -v
```

### 集成测试
```bash
# 测试订单解析
python -m pytest tests/test_parser.py

# 测试 API 端点
python -m pytest tests/test_api.py
```

### 手动测试
```bash
# 调试菜单结构
python scripts/debug_menu.py

# 拉取菜单缓存
python scripts/pull_menu.py
```

## 🚨 故障排除

### 常见问题

**1. 菜单获取失败**
```bash
# 检查 Loyverse 配置
curl http://localhost:8000/health/detailed

# 手动刷新菜单
curl -X POST http://localhost:8000/menu/refresh
```

**2. 订单解析错误**
```bash
# 检查解析统计
curl http://localhost:8000/stats

# 查看详细日志
tail -f logs/app.log
```

**3. 会话状态异常**
```bash
# 清理过期会话
curl -X POST http://localhost:8000/admin/cleanup

# 重置特定用户会话
curl -X DELETE http://localhost:8000/admin/session/USER_ID
```

### 日志分析
```bash
# 实时查看日志
tail -f logs/app.log | grep ERROR

# 分析性能
tail -f logs/app.log | grep "Process-Time"
```

## 📈 性能优化

### 缓存策略
- **菜单缓存** - 内存 + 磁盘双重缓存
- **会话缓存** - 基于 TTL 的自动清理
- **解析缓存** - 常用菜单名称缓存

### 并发处理
- **异步 I/O** - 所有网络请求异步处理
- **线程安全** - 全局状态保护
- **连接池** - HTTP 客户端连接复用

## 🔄 升级指南

### 从 v1.x 升级到 v2.0

1. **备份数据**
```bash
cp -r . ../whatsapp-bot-backup
```

2. **更新依赖**
```bash
pip install -r requirements.txt --upgrade
```

3. **迁移配置**
```bash
# 使用新的配置格式
cp .env.example .env
# 迁移旧配置到新文件
```

4. **验证升级**
```bash
# 检查系统状态
curl http://localhost:8000/health/detailed
```

## 🤝 贡献指南

### 开发环境设置
```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 启用调试模式
export DEBUG_MODE=true
export LOG_LEVEL=DEBUG

# 运行测试
pytest
```

### 代码规范
- 使用 `black` 进行代码格式化
- 使用 `flake8` 进行代码检查
- 添加类型注解
- 编写单元测试

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🆘 支持

- 📧 **邮件支持**: your-email@example.com
- 💬 **问题反馈**: [GitHub Issues](https://github.com/your-repo/issues)
- 📖 **文档**: [在线文档](https://your-docs-site.com)

---

⭐ 如果这个项目对你有帮助，请给个 Star！
