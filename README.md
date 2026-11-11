# EasyKig

EasyKig 是 Blender 4.5 LTS 的 Kigurumi 头壳设计插件，配套 FastAPI 网关。可编辑模板 Shape Keys、预处理 PMX、渲染白模，并连接图像编辑服务和自建 GLB 编辑服务。头壳几何和 STL 输出为**非制造级**。

## Blender 安装与操作

1. 下载 [EasyKig 扩展 ZIP](https://github.com/YuiLu/EasyKig/releases)，在 Blender 的 **Preferences → Get Extensions → Install from Disk** 安装。也可以从仓库根目录运行 `blender --command extension build --source-dir easykig`。
2. 在 3D View 按 **N** 打开 **EasyKig**。点击 **Demo Template** 查看 8 个 Shape Keys。编辑外部模板时，选中网格后点 **Use Selected**。多件模板可指定 **Preview Collection**，白模会包括集合里的网格，Shape Keys 仍按当前 Face 网格编辑。
3. 如需导入 PMX 或 PMD，在 Blender 的扩展管理器独立安装 **MMD Tools 4.x**。点击 **Import PMX (minimal)**，检查自动选出的 Face 和导入尺寸。默认每 PMX 单位按 0.08 米换算，可调整 **PMX Scale**。拆材质和烘焙操作会将当前 Morph 烘焙到新副本，原网格及其 Shape Keys 保留。
4. **Render White Clay** 生成正面 1024×1024 白模。改变几何后重新渲染，再点 **Generate Finished Preview**。插件把最近的白模和可选角色参考图送给网关，预览图写入 **Preview Directory**。
5. 参考图流程使用 **Character Head → Kig Design → Product**。辅助图可选。Character Head 使用表情与角色配色，Kig Design 使用表情与头壳案例，Product 使用商品照案例与表情。点击相应的结果按钮查看生成图。
6. 远端配置在 **Preferences → Add-ons → EasyKig**。开启 Blender 的 **Allow Online Access**，填写 **3D Editing Server URL**、**Server Token** 和 **Request Timeout (s)**，再执行 **Test Connection**。远端 GLB 结果作为新对象导入，源网格可在场景中继续使用。

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

在 `server/.env` 设置随机生成的 `EASYKIG_SERVER_TOKEN`。图像预览使用 `OPENAI_IMAGE_API_KEY`、`OPENAI_IMAGE_API_BASE` 和 `OPENAI_IMAGE_MODEL`。GLB 转发使用 `EASYKIG_EDIT3D_UPSTREAM_URL`（完整端点）和可选的 `EASYKIG_EDIT3D_UPSTREAM_TOKEN`。保存后用以下任一方式启动：

```bash
python -m uvicorn server.app:app --env-file server/.env --host 127.0.0.1 --port 8000
docker compose up --build -d
```

两种启动方式都默认通过 `http://127.0.0.1:8000` 访问。跨机器可用 HTTPS 反向代理或 SSH 本地转发，例如 `ssh -L 8000:127.0.0.1:8000 user@server`。Blender 使用网关令牌，上游令牌只配置在网关。尚未接入 GLB 服务时，`/v1/edit3d` 返回 501。接口见 [API 文档](docs/API.md)。

## 参考图 Prompt 预设

默认使用 EasyKig 自带 Prompt。要逐字使用已有授权的参考图 Prompt，把三阶段正文分别存为 UTF-8 的 `head.txt`、`design.txt` 和 `product.txt`，在网关设置 `EASYKIG_REFERENCE_PROMPTS_DIR` 指向它们。网关原样发送文件内容。使用 Docker 时，把该目录以只读方式挂载，并将变量设置为容器内路径。预设的署名、许可与适用范围随预设保存。

**Generate Finished Preview** 使用白模专用 Prompt，以渲染角度、轮廓和五官位置作为约束。参考图预设用于独立的三阶段工作流。

## 开发验收

```bash
python -m pip install pytest
python -m pytest -q
```

见 [交接记录](WORK_HANDOFF.md)。PMX 导入调用独立安装的 MMD Tools。EasyKig 源码许可见 [LICENSE](LICENSE)。
