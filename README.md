# OpenAI Canvas · 多图工作流便携版

通过 OpenAI API 完成「参考图 → 提示词优化 → 图片生成」，使用可拖拽连线的深色画布。**无需安装 ComfyUI、Python 或下载模型。**

![界面预览](docs/preview.png)

## 下载即用

到 [Releases 下载页面](https://github.com/bullshitAI52/openai-canvas-portable/releases/latest) 选择对应系统。请下载下表中的便携 ZIP，而不是 GitHub 自动生成的 Source code。

| 系统 | 下载 | 压缩大小 | 启动文件 |
| --- | --- | --- | --- |
| Windows 10/11，Intel/AMD 64 位 | [Windows x64](https://github.com/bullshitAI52/openai-canvas-portable/releases/download/v1.0.0/OpenAI-Canvas-Windows-x64.zip) | 18.4 MB | `Start-Windows.bat` |
| Mac，M 系列苹果芯片 | [Mac Apple Silicon](https://github.com/bullshitAI52/openai-canvas-portable/releases/download/v1.0.0/OpenAI-Canvas-macOS-AppleSilicon.zip) | 30.9 MB | `Start-macOS.command` |
| Mac，Intel 处理器 | [Mac Intel](https://github.com/bullshitAI52/openai-canvas-portable/releases/download/v1.0.0/OpenAI-Canvas-macOS-Intel.zip) | 31.3 MB | `Start-macOS.command` |

1. 完整解压 ZIP，双击启动文件，保持启动窗口打开。
2. 在网页右上角「API 设置」中填入自己的 OpenAI API Key。
3. 上传参考图，修改提示词，点击「一键运行 2 个节点」。
4. 在 OUTPUT 中查看、下载图片；退出时点击「退出服务」。

默认本机地址：`http://127.0.0.1:8189/openai-canvas`。端口被占用时，程序会选择后续端口并打开正确地址。

## 功能

- 图片节点、LLM 节点、生图节点和输出节点；支持拖动、缩放、连线。
- 多张人物、服装与场景参考图；LLM 分析结果可继续编辑。
- 独立运行 LLM、生图或一键串联；可编辑模型、尺寸、质量和数量。
- 本机自动保存、工作流 JSON 导入导出、图片下载。
- 同一后台服务拒绝并发 API 任务，避免多个窗口重复运行。

## 数据与费用

便携包不含 API Key、私人图片或使用记录。每个人使用自己的密钥与 OpenAI 账户；API 按用量计费，不使用 ChatGPT 网页订阅额度。只有执行时，提示词和连接的参考图才发送到官方 OpenAI API。

用户数据与程序文件分开保存：

- Windows：`%LOCALAPPDATA%\OpenAI Canvas`
- Mac：`~/Library/Application Support/OpenAI Canvas`

`config.local.json` 含密钥，请勿分享。导出的工作流不含密钥，但包含上传的参考图；生成结果文件需要单独传输。分享软件应发送原始 Release ZIP。

## 验证范围

14 项后端测试和 9 项画布逻辑回归场景通过。Mac Apple Silicon 实测；Mac Intel 包通过 Rosetta 和解压后独立启动检查。**Windows 已完成文件结构、架构及完整性校验，尚未实机运行测试。**

没有使用真实 API Key 完成付费生图，模型权限、网络和生成效果仍需首次运行验证。便携包未做 Windows 发布者签名或 Apple 开发者公证。

详细说明：[使用说明](使用说明.md) · [检查结果](检查结果.md)

## 从源码运行

源码运行需要 Python 3.13；便携 ZIP 已自带运行环境。

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用：.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python server.py
```

不自动打开浏览器：`python server.py --no-browser`；指定端口：`python server.py --port 8189`。

可通过 `OPENAI_API_KEY` 提供密钥（优先于本机配置），通过 `OPENAI_CANVAS_DATA_DIR` 指定数据目录。

运行测试（不调用付费 API）：

```sh
python tests/test_server.py
node tests/test_ui.cjs
```

运行环境使用 Python、Pillow、certifi。便携包附带 `RUNTIME-SOURCES.json` 与第三方许可证；Release 附带 SHA-256 校验文件。本项目不是 OpenAI 官方产品。
