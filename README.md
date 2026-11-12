# EasyKig

EasyKig 是 Kigurumi 头壳设计插件，当前使用 Blender 5.1 开发，配套 FastAPI 网关。可编辑模板 Shape Keys、预处理 PMX、渲染白模，并连接图像编辑服务和自建 GLB 编辑服务。头壳几何和 STL 输出为**非制造级**。

## Blender 安装与操作

1. 下载 [EasyKig 扩展 ZIP](https://github.com/YuiLu/EasyKig/releases)，在 Blender 的 **Preferences → Get Extensions → Install from Disk** 安装。也可以从仓库根目录运行 `blender --command extension build --source-dir easykig`。
2. 在 3D View 按 **N** 打开 **EasyKig**。将 PNG、JPG、JPEG 或 WebP 批量拖入 **References**，也可以用 **Add Images** 多选，最多四张。Blender 弹出导入菜单时选 **Add EasyKig Reference Images**。点缩略图在 Blender 内放大，按 **Esc** 关闭。预览从源图读取，长边最高为 1024 像素，方向按 EXIF 保持。直接在 **Prompt** 的各行输入，或用 **Paste** 粘贴整段多行文字。Prompt 和参考图路径随场景保存。按 **Head → Design → Product** 生成参考图。
3. **White Clay** 生成 1024×1024 正面白模。改变几何后重新渲染，再点击 **Finish**，将白模和参考图送给生图服务。使用 EasyKig Server 或 ChatGPT API Credits 路径时，多个参考图需要更新后的 EasyKig 网关。面板可切换结果阶段，点击结果缩略图可放大。
4. 展开 **Modeling Tools** 可创建 **Demo Template** 或使用选中的外部网格。**Preview Collection** 可把集合里的其他网格纳入白模。安装独立的 **MMD Tools 4.x** 后可使用 **PMX and Material Prep**，拆材质会烘焙到新副本。
5. 在 **Preferences → Add-ons → EasyKig** 配置服务器、请求超时和生图来源。开启 Blender 的 **Allow Online Access** 后，分别使用 **Test EasyKig Server** 和 **Test Image API & Refresh Models** 检查连接。点 **Save Preferences** 后，后续开发版启动会沿用已保存的设置。

**Supporting Images** 中三项均为可选。**Face Expression** 给 Head、Design 和 Product 提供表情参考。**Character Color Palette** 给 Head 提供发色、瞳色和角色配色。**Shell Style Example** 给 Design 和 Product 提供头壳结构或成品风格参考。

**Remote Text → Shape Keys** 使用规则式参数调整。STL 以毫米导出，Solidify 与拓扑检查用于设计阶段。眼孔、内壳、佩戴空间与制造公差仍需工程验证。

## 网关运行

需要 Python 3.10+。在仓库根目录执行：

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r server/requirements.txt
# Linux/macOS: cp server/.env.example server/.env
# Windows PowerShell: Copy-Item server/.env.example server/.env
```

在 `server/.env` 设置随机生成的 `EASYKIG_SERVER_TOKEN`。图像预览使用 `OPENAI_IMAGE_API_KEY`、`OPENAI_IMAGE_API_BASE` 和默认模型 `OPENAI_IMAGE_MODEL`。通过 `EASYKIG_IMAGE_MODELS` 添加 Blender 可选择的模型 ID，以逗号分隔。GLB 转发使用 `EASYKIG_EDIT3D_UPSTREAM_URL`（完整端点）和可选的 `EASYKIG_EDIT3D_UPSTREAM_TOKEN`。保存后用以下任一方式启动：

```bash
python -m uvicorn server.app:app --env-file server/.env --host 127.0.0.1 --port 8000
docker compose up --build -d
```

两种启动方式都默认通过 `http://127.0.0.1:8000` 访问。如果 EasyKig 在 SSH 容器内的 8000 端口运行，可以在本机开一个终端建立隧道：

```powershell
ssh -NT -o ExitOnForwardFailure=yes -p 35995 -L 127.0.0.1:8000:127.0.0.1:8000 user@magic-lab.tech
```

`35995` 是示例 SSH 端口。用实际用户名替换 `user`，保持终端开启，Blender 的服务器地址填 `http://127.0.0.1:8000`。有单独部署的 HTTPS 反向代理时，可以填它提供的 EasyKig HTTPS 地址。Blender 使用 `EASYKIG_SERVER_TOKEN`，上游令牌配置在网关。尚未接入 GLB 服务时，`/v1/edit3d` 返回 501。接口见 [API 文档](docs/API.md)。

### 切换生图来源与模型

在 EasyKig 扩展设置的 **Image Generation** 中选择来源。点 **Test Image API & Refresh Models** 获取该来源的模型列表。每个来源分别保存选中的模型。

- **OpenAI-compatible Gateway** 在 Blender 中填写 **Image API Base URL**（如 `https://gateway.example/v1`）和 **Image API Key**。可从 `/models` 列表选择，也可手填 **Model ID**。选择支持 `/images/edits` 并返回 PNG `b64_json` 的模型。此模式可以独立生图。若需要服务器上的逐字 Prompt 预设，勾选 **Use EasyKig Server Prompt Presets** 并更新 EasyKig 服务器。
- **EasyKig Server** 使用服务器上的 `OPENAI_IMAGE_API_BASE` 和 `OPENAI_IMAGE_API_KEY`。模型列表会合并配置的模型和供应商 `/models` 返回的可识别 GPT Image 模型。其他供应商的自定义图像模型可通过 `EASYKIG_IMAGE_MODELS` 声明。
- **ChatGPT API Credits** 使用 OpenAI 官方 API。符合条件的 ChatGPT Pro 或 Business 订阅可在账单页领取 API credits 并关联到自己拥有的 API 组织。把关联组织里的项目 API Key 设置为网关的 `OPENAI_SUBSCRIPTION_API_KEY`，再启动或重启网关。该额度可用于 Images API。Plus 的 ChatGPT 生图额度留在 ChatGPT 内使用。[OpenAI Docs](https://developers.openai.com/api/docs/guides/chatgpt-api-credits)

## 参考图 Prompt 预设

默认使用 EasyKig 自带 Prompt。要逐字使用已有授权的参考图 Prompt，把三阶段正文分别存为 UTF-8 的 `head.txt`、`design.txt` 和 `product.txt`，在网关设置 `EASYKIG_REFERENCE_PROMPTS_DIR` 指向它们。网关原样发送文件内容。使用 Docker 时，把该目录以只读方式挂载，并将变量设置为容器内路径。预设的署名、许可与适用范围随预设保存。

**Finish** 使用白模专用 Prompt，以渲染角度、轮廓和五官位置作为约束。参考图预设用于独立的三阶段工作流。

## 开发验收

在 Windows 上可以让 Blender 直接加载工作区里的 `easykig/`。首次启动时指定 Blender 可执行文件：

```powershell
.\scripts\dev-blender.ps1 -Blender 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
```

之后改完代码，关闭开发版 Blender，再运行 `.\scripts\dev-blender.ps1`。启动脚本复用平时的 Blender 5.1 偏好和已启用的扩展，包括 MMD Tools。用 `-BlendFile` 打开现有场景，用 `-Check` 无界面确认扩展已加载。想单独使用旧的开发配置时加 `-Isolated`。

网关也可以直接从源码运行，开发时给 README 中的 Uvicorn 命令加上 `--reload`，Python 代码变更后会自动重启。

```bash
python -m pip install pytest
python -m pytest -q
```

见 [交接记录](WORK_HANDOFF.md)。PMX 导入调用独立安装的 MMD Tools。EasyKig 源码许可见 [LICENSE](LICENSE)。
