# EasyKig

EasyKig 是 Kigurumi 头壳设计插件，当前使用 Blender 5.1 开发，配套 FastAPI 网关。可编辑模板 Shape Keys、预处理 PMX、渲染白模，并连接图像编辑服务和 ShapeUp 图像条件 3D 编辑服务。头壳几何和 STL 输出为**非制造级**。

## Blender 安装与操作

1. 下载 [EasyKig 扩展 ZIP](https://github.com/YuiLu/EasyKig/releases)，在 Blender 的 **Preferences → Get Extensions → Install from Disk** 安装。也可以从仓库根目录运行 `blender --command extension build --source-dir easykig`。
2. 在 3D View 按 **N** 打开 **EasyKig**。将 PNG、JPG、JPEG 或 WebP 批量拖入 **References**，也可以用 **Add Images** 多选，最多四张。Blender 弹出导入菜单时选 **Add EasyKig Reference Images**。点缩略图在 Blender 内放大，按 **Esc** 关闭。预览从源图读取，长边最高为 1024 像素，方向按 EXIF 保持。直接在 **Prompt** 的各行输入，或用 **Paste** 粘贴整段多行文字。Prompt 和参考图路径随场景保存。按 **Head → Design → Product** 生成参考图。
3. **White Clay** 生成 1024×1024 正面白模。改变几何后重新渲染，再点击 **Finish**，将白模和参考图送给生图服务。使用 EasyKig Server 或 ChatGPT API Credits 路径时，多个参考图需要更新后的 EasyKig 网关。面板可切换结果阶段，点击结果缩略图可放大。
4. 在 **3D Editing** 选择源网格和目标图。可使用 **Finished Preview**、已生成的 Head/Design/Product、原始参考图或 **Image File**。点 **Generate Edited 3D** 提交任务，Blender 保持可操作。状态栏显示排队、推理和下载阶段；关闭监控后可点 **Resume Task** 取回同一任务，结果作为新对象导入。**Stop Waiting / Esc** 只暂停客户端等待，已经接受的服务端任务继续执行。
5. 展开 **Modeling Tools** 可创建 **Demo Template** 或使用选中的外部网格。**Preview Collection** 可把集合里的其他网格纳入白模。安装独立的 **MMD Tools 4.x** 后可使用 **PMX and Material Prep**，拆材质会烘焙到新副本。
6. 在 **Preferences → Add-ons → EasyKig** 配置服务器、请求超时和生图来源。开启 Blender 的 **Allow Online Access** 后，分别使用 **Test EasyKig Server** 和 **Test Image API & Refresh Models** 检查连接。点 **Save Preferences** 后，后续开发版启动会沿用已保存的设置。

**Supporting Images** 中三项均为可选。**Face Expression** 给 Head、Design 和 Product 提供表情参考。**Character Color Palette** 给 Head 提供发色、瞳色和角色配色。**Shell Style Example** 给 Design 和 Product 提供头壳结构或成品风格参考。

**Remote Text → Shape Keys** 使用规则式参数调整。STL 以毫米导出，Solidify 与拓扑检查用于设计阶段。眼孔、内壳、佩戴空间与制造公差仍需工程验证。

## 本机与远端环境

Windows 本机运行 Blender 5.1、EasyKig 插件和 OpenSSH 客户端。`dev-blender.ps1` 直接加载工作区源码，使用 Blender 自带 Python。本机使用远端 3D 服务时，环境依赖由远端网关和 ShapeUp 提供。

Linux 远端运行 EasyKig FastAPI 网关，ShapeUp 的 GPU、PyTorch、CUDA、权重及推理依赖安装在远端的 ShapeUp 环境中。`server/requirements.txt` 是网关的 CPU 依赖，网关有独立虚拟环境。

## 远端网关运行

需要 Python 3.10+。在远端仓库根目录执行以下命令。

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r server/requirements.txt
# Linux/macOS: cp server/.env.example server/.env
# Windows PowerShell: Copy-Item server/.env.example server/.env
```

在 `server/.env` 设置随机生成的 `EASYKIG_SERVER_TOKEN`。图像预览使用 `OPENAI_IMAGE_API_KEY`、`OPENAI_IMAGE_API_BASE` 和默认模型 `OPENAI_IMAGE_MODEL`。通过 `EASYKIG_IMAGE_MODELS` 添加 Blender 可选择的模型 ID，以逗号分隔。3D 后端通过 `EASYKIG_EDIT3D_BACKEND=generic|shapeup` 选择。`generic` 使用 `EASYKIG_EDIT3D_UPSTREAM_URL` 的完整 JSON 端点；`shapeup` 使用 ShapeUp 服务根地址。上游令牌可用 `EASYKIG_EDIT3D_UPSTREAM_TOKEN` 或服务端的 `EASYKIG_EDIT3D_UPSTREAM_TOKEN_FILE` 配置。保存后用以下任一方式启动：

```bash
python scripts/run_gateway.py
docker compose up --build -d
```

两种启动方式都默认通过 `http://127.0.0.1:8001` 访问。如果 EasyKig 在 SSH 容器内的 8001 端口运行，可以在本机开一个终端建立隧道：

```powershell
ssh -NT -o ExitOnForwardFailure=yes -p 35995 -L 127.0.0.1:8001:127.0.0.1:8001 user@magic-lab.tech
```

`35995` 是示例 SSH 端口。用实际用户名替换 `user`，保持终端开启，Blender 的服务器地址填 `http://127.0.0.1:8001`。有单独部署的 HTTPS 反向代理时，可以填它提供的 EasyKig HTTPS 地址。Blender 使用 `EASYKIG_SERVER_TOKEN`，上游令牌配置在网关。尚未接入 GLB 服务时，`/v1/edit3d` 返回 501。接口见 [API 文档](docs/API.md)。

### 自动 SSH 隧道

在 **Preferences → Add-ons → EasyKig → SSH Tunnel** 设置连接，点击 **Save Preferences**。启用 **Auto-connect SSH on Development Launch** 后，每次正常运行 `dev-blender.ps1` 都会读取该 Blender 配置里的连接设置。

- **SSH Host / Config Alias** 填 SSH 主机或 `~/.ssh/config` 的 Host 别名。
- **SSH Port** 填登录端口，例如 35995。填 0 使用 SSH 配置里的端口。
- **SSH User** 和 **SSH Identity File** 可以留空，沿用 SSH 配置及 ssh-agent。
- **Local Port** 默认 8001，**Remote Host** 默认 `127.0.0.1`，**Remote Gateway Port** 默认 8001。

插件通过 OpenSSH 密钥或 ssh-agent 登录。首次连接先在终端使用同一主机完成主机指纹确认和登录验证。**Connect** 可在当前 Blender 内立即连接，**Disconnect** 关闭该 Blender 创建的隧道。连接时服务器地址自动设置为 `http://127.0.0.1:<Local Port>`，随后可点击 **Test EasyKig Server**。正常退出 Blender 或禁用 EasyKig 会关闭它创建的 SSH 进程。

`-Check` 只检查加载，`-NoTunnel` 可在本次普通启动时跳过自动连接。端口被占用时会显示错误，选用其他 Local Port 或关闭先前的隧道后重试。

### SSH 免 Token 连接

在远端的 `server/.env` 设置以下值，然后重启 EasyKig 网关。

```dotenv
EASYKIG_AUTH_MODE=ssh
EASYKIG_HOST=127.0.0.1
EASYKIG_PORT=8001
```

通过 `python scripts/run_gateway.py` 启动时，服务绑定回环地址并关闭代理地址头解析。SSH 转发连接由远端 sshd 连接本机回环地址，网关按实际连接来源接受请求。此模式下 Blender 的 **Server Token** 留空，网关的各业务接口使用同一 SSH 访问方式。公网 HTTPS 部署使用默认 `EASYKIG_AUTH_MODE=token`。

手动运行 Uvicorn 时使用 `--host 127.0.0.1 --no-proxy-headers`。Docker Compose 的桥接网络在网关处呈现 Docker 网桥地址，使用 Token 模式。

### 远端 ShapeUp 对接

下面以 `/data/EasyKig` 和 `/data/ShapeUp` 的服务器目录为例。EasyKig 网关在远端 `http://127.0.0.1:8001`，由 Supervisor 托管，ShapeUp 保持在远端 8000。
关闭终端、断开 SSH 后服务继续运行，容器重启时沿用已安装的 Supervisor 启动流程。

```bash
supervisorctl status easykig shapeup
supervisorctl restart easykig
tail -f /data/EasyKig/runtime/gateway.log
```

Blender 的服务器地址填隧道的本地地址。网关使用 Token 模式时，**Server Token** 使用
远端 `/data/EasyKig/runtime/api-token` 中的内容。也可以手动建立到 SSH 容器的隧道。

```bash
ssh -NT -o ExitOnForwardFailure=yes -L 127.0.0.1:8001:127.0.0.1:8001 your-ssh-alias
```

ShapeUp 的私有令牌由远端网关读取。使用现有目标图做 3D 编辑时，直接配置 3D 服务连接即可。

在同样的 `/data/ShapeUp` 部署旁重新安装网关，可以执行：

```bash
bash /data/EasyKig/scripts/install-gateway.sh
# 启用 SSH 免 Token 模式并重启网关
bash /data/EasyKig/scripts/install-gateway.sh --ssh-auth
```

ShapeUp 根据**源网格和目标图像**进行编辑，不支持只用文字从零生成三维。
插件会烘焙源网格当前 Shape Keys/修改器到上传副本，并将场景单位转换为 glTF 的米。
网关还原 ShapeUp 输出的归一化坐标后，Blender 再导入新网格；原网格及其 Shape Keys 保留。
新结果有独立拓扑，不继承原有 Shape Keys，编辑也不会保证保留眼孔或制造结构。

任务 ID 保存在场景设置和预览目录的 `mesh_job.json` 中。断网、暂停等待或重新打开已保存
的场景后，可通过 **Resume Task** 查询并下载同一任务，无须重复生成。网关端的恢复信息
保存在 `EASYKIG_EDIT3D_JOB_DIR`，Compose 使用持久卷保存该目录。
GPU 模型只在 ShapeUp 的任务子进程中加载，任务结束后释放显存；网关和插件网络线程不加载 GPU 模型。

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

日志出现 `Abnormal ... No module named 'bgl'` 时，在 **Preferences → Add-ons** 搜索 **Abnormal**，关闭启用状态并保存偏好。Blender 5.0 已移除 BGL API，Abnormal 1.1 需要更新其绘制实现才能在 5.1 使用。日志中的 `EasyKig source` 表示 EasyKig 已从工作区加载。[Blender 5.0 Python API](https://developer.blender.org/docs/release_notes/5.0/python_api/)

远端网关也可以直接从源码运行，开发时使用 `python -m uvicorn server.app:app --env-file server/.env --host 127.0.0.1 --port 8001 --no-proxy-headers --reload`，Python 代码变更后会自动重启。

```bash
python -m pip install pytest
python -m pytest -q
# 可选：Blender 5.1 的真实导出/异步网关/恢复/导入检查（使用模拟推理上游，无 GPU 负载）
python scripts/smoke-shapeup.py --blender /path/to/blender
```

见 [交接记录](WORK_HANDOFF.md)。PMX 导入调用独立安装的 MMD Tools。EasyKig 源码许可见 [LICENSE](LICENSE)。
