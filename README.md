# 内向人会议助手 MVP

微信小程序 + 后端，实时转写会议内容，由大模型根据会议目标提醒「何时发言、说什么」，并通过信号灯与震动提醒用户。

---

## 一、你需要准备

- **腾讯云**：已开通实时语音识别，并有 **AppID、SecretId、SecretKey**。
  - **重要**：腾讯云自 2023-11-30 起不再支持在控制台查询 SecretKey，仅在创建密钥时显示一次，请创建后立即保存到安全位置（如密码管理器），否则只能重新创建密钥。
- **阿里云**：DashScope（通义千问）API Key，用于大模型建议。
- **微信开发者工具**：用于运行小程序；真机调试时后端需为 HTTPS 或通过内网穿透暴露。

---

## 二、后端（Python + FastAPI）

**以下命令均在项目根目录下的 `backend` 目录中执行。**

### 1. 环境与依赖

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

你已创建 `.env` 文件，请确认其中包含（值与示例一致即可，不要提交到 Git）：

- `TENCENT_ASR_APP_ID`：腾讯云语音识别 AppID  
- `TENCENT_SECRET_ID`：腾讯云 SecretId  
- `TENCENT_SECRET_KEY`：腾讯云 SecretKey（创建时保存的那份）  
- `ALIYUN_LLM_API_KEY`：阿里云 DashScope API Key  

可选：`TENCENT_ASR_ENGINE=16k_zh`、`ALIYUN_LLM_MODEL=qwen-plus` 等，见 `backend/.env.example`。

### 3. 启动

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- 接口文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/>

---

## 三、小程序

### 1. 导入项目

- 打开 **微信开发者工具**，选择「导入项目」。
- 目录选择本仓库下的 **`miniprogram`** 文件夹。
- 若暂无正式 AppID，可使用测试号；有 AppID 时在 `miniprogram/project.config.json` 中把 `appid` 改为你的 AppID。

### 2. 配置后端地址

编辑 `miniprogram/app.js`，修改 `globalData.baseUrl`：

- **本机 + 模拟器**：可用 `http://localhost:8000`（若请求失败，再改为本机局域网 IP，如 `http://192.168.x.x:8000`）。
- **真机调试**：必须使用电脑局域网 IP（如 `http://192.168.x.x:8000`）或已配置 HTTPS 的域名；也可用内网穿透（ngrok、frp 等）将本机 8000 端口暴露为 HTTPS 后填写该地址。

### 3. 使用流程

1. **会议设置页**：填写「会议主题」「目标类型」「目标描述」→ 点击「开始会议」。
2. **会议进行页**：自动开始录音，每约 8 秒上传一段；每 5 秒拉取一次建议。
3. **信号灯**：绿 = 建议现在发言（并触发短震动），黄 = 可准备发言，灰 = 继续聆听。
4. **结束会议**：点击「结束会议」可查看本场简要总结。

---

## 四、项目结构

| 目录/文件 | 说明 |
|-----------|------|
| `backend/` | FastAPI 后端：腾讯云 ASR（WebSocket）、阿里云大模型、会议状态（内存） |
| `backend/app/api/meeting.py` | 会议 API：start / chunk / status / end |
| `backend/app/services/asr_tencent.py` | 腾讯云实时语音识别封装 |
| `backend/app/services/llm_aliyun.py` | 阿里云大模型封装 |
| `miniprogram/` | 微信小程序：会议设置页、会议进行页（录音、上传、轮询、信号灯、震动） |
| `.env` | 本地密钥（已加入 .gitignore，切勿提交） |

---

## 五、可选：本地自测 ASR / 大模型

```bash
cd backend
source .venv/bin/activate

# 测试腾讯 ASR（需本地有一个 .aac 文件）
python -m app.services.asr_tencent /path/to/audio.aac

# 测试阿里云大模型
python -m app.services.llm_aliyun --summary "产品评审" --recent "接口下周定稿"
```

---

## 六、安全提醒

- **不要将 `.env` 或任何包含 SecretKey/API Key 的文件提交到 Git**；本项目已通过 `.gitignore` 忽略 `backend/.env`。
- 腾讯云 SecretKey 仅在创建时显示一次，请妥善保存；若遗失需在控制台新建密钥并更新 `.env`。
# AI_listening
# AI_listening
# AI_listening
# AI_listening
# AI_listening
