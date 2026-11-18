# EasyKig

Blender 5.1 的单部件网格编辑插件。选择一个模板网格和一张前脸或头饰参考图，提交给远端 ShapeUp，结果作为新网格导入。

角色参考、头壳设计、商品成图和部件拆分在独立的 [EasyKig Studio](https://github.com/YuiLu/ai-kigurumi-head-split) 开发。

## Blender 使用

1. 安装扩展，或运行 `./scripts/dev-blender.ps1` 加载工作区源码。
2. 在 N 面板打开 **EasyKig**，选择 **Source Mesh**，或使用 **Use Selected Mesh**。
3. 拖入一张 PNG、JPEG 或 WebP 单部件图，也可点击 **Drop Image or Browse**。点击图片可以放大预览。
4. 点击 **Edit Component**。插件上传当前模板的烘焙副本及参考图，后台查询 ShapeUp 任务并导入结果。高密度网格的上传副本会适当降面以满足 20 MiB 上限。
5. **Stop Waiting / Esc** 暂停客户端等待，**Resume Task** 恢复同一任务。任务记录保存在场景和输出目录的 `mesh_job.json` 中。

**Editing Notes** 用于保存编辑意图，支持多行编辑。当前 ShapeUp 使用图像条件，文字条件留待后续后端接入。模板文件中的其他部件可继续在 Blender 内编辑。

## 连接设置

**Preferences → Add-ons → EasyKig** 中选择 **Hosted Service** 或 **Self-hosted Service**。

- 托管服务填写服务 URL 和访问 Token，实际托管服务由部署者提供。
- 自部署可选 **Direct URL** 或 **SSH Tunnel**。SSH 填主机、端口、用户及私钥文件，转发端口默认本地 8001 到远端 127.0.0.1:8001。
- **Connect Server** 统一检查连接、凭据和 ShapeUp 状态。
- 勾选 **Auto-connect on Development Launch** 并 **Save Preferences** 后，PS1 启动会连接所选服务。

SSH 使用 OpenSSH 配置和密钥。未加密的私钥可直接读取，有口令的密钥可先加载到 ssh-agent。首次连接先在终端验证主机指纹和免交互登录。

## 远端网关

网关使用独立的 Python 3.10+ CPU 环境，ShapeUp 的 GPU 环境在远端部署。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r server/requirements.txt
cp server/.env.example server/.env
python scripts/run_gateway.py
```

在 `server/.env` 配置 ShapeUp 地址及凭据。

```dotenv
EASYKIG_EDIT3D_BACKEND=shapeup
EASYKIG_EDIT3D_UPSTREAM_URL=http://127.0.0.1:8000
EASYKIG_EDIT3D_UPSTREAM_TOKEN_FILE=/data/ShapeUp/runtime/api-token
EASYKIG_EDIT3D_JOB_DIR=runtime/edit3d-jobs
EASYKIG_AUTH_MODE=ssh
EASYKIG_HOST=127.0.0.1
EASYKIG_PORT=8001
```

SSH 模式接受回环连接，Blender 的 Server Token 可以留空。公网 HTTPS 或 Docker 桥接部署使用 `EASYKIG_AUTH_MODE=token` 并设置 `EASYKIG_SERVER_TOKEN`。旧 `/data/EasyKig` + Supervisor 部署可使用 `bash scripts/install-gateway.sh --ssh-auth`。

## 开发与验证

```powershell
.\scripts\dev-blender.ps1 -Blender 'D:\Blender51\blender.exe'
.\scripts\dev-blender.ps1 -Check
.\scripts\dev-blender.ps1 -NoConnect
```

启动器复用平时的 Blender 偏好，`-Isolated` 使用独立测试配置，`-NoTunnel` 兼容为 `-NoConnect` 的别名。改动后保存场景并重启开发版即可加载源码。

```bash
python -m pytest -q tests
python scripts/smoke-shapeup.py --blender /path/to/blender
```

接口见 [API](docs/API.md)，开发状态见 [交接记录](WORK_HANDOFF.md)。
