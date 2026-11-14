# EasyKig 开发交接

当前开发和验证使用 Blender 5.1。插件和网关分别位于 `easykig/` 与 `server/`，安装、配置和部署步骤见 [README](README.md)，请求格式见 [API 文档](docs/API.md)。

2026-11-14 客户端与远端部署调整。Windows 本机通过 Blender 自带 Python 开发插件，OpenSSH 连接远端网关。推理环境位于远端 ShapeUp。扩展偏好新增 SSH 主机/别名、用户、端口、密钥路径与转发目标，PS1 普通启动按已保存设置自动连接，`-Check` 与 `-NoTunnel` 跳过。正常退出 Blender 或禁用插件会回收所创建的 SSH 进程。

网关新增 `EASYKIG_AUTH_MODE=ssh`，接受实际回环连接，Blender 的 Server Token 可留空。`scripts/run_gateway.py` 在此模式要求绑定回环地址，关闭 Uvicorn 代理地址头解析。远端安装脚本的 `--ssh-auth` 可应用设置并重启网关。公网 HTTPS 与 Docker 桥接部署继续使用默认 Token 模式。

Windows 当前旧 Abnormal 1.1 启动时依赖已移除的 BGL，在 Blender 5.1 中需要停用或升级。EasyKig 在该错误后可正常注册。

v0.1.2 新增 ShapeUp 异步 3D 编辑：源网格 + 目标图提交、任务状态、暂停等待与恢复、结果导入。
网关恢复 ShapeUp 的归一化坐标，插件在临时副本上烘焙 Shape Keys 并换算 glTF 米单位。
原有 generic 文字 + GLB 上游接口继续保留。本机网关使用 8001，ShapeUp 使用 8000。

[扩展安装包](https://github.com/YuiLu/EasyKig/releases) 由 GitHub Actions 发布。推送和 PR 会运行测试，推送与扩展版本一致的 `v*` 标签时发布 ZIP。

v0.1.1 将服务配置、图像模型和预览目录设置放到扩展偏好。侧栏默认展示参考图、Prompt、生成操作和结果缩略图，建模工具默认折叠。

## 已验收

- [x] 41 项 Python 测试通过。SSH 参数、端口冲突、进程退出回收、无 Token 请求、回环访问控制与伪造代理头覆盖通过。
- [x] Blender 5.1.2 实际保存 SSH 偏好后重启，按启动脚本逻辑自动建立 OpenSSH 连接，验证连接失败状态显示与禁用时回收。使用本地未监听端口验证失败路径。
- [x] Blender 5.1.2 模拟 ShapeUp 的提交、暂停、恢复和结果导入通过，源 Shape Keys 与世界坐标尺寸保持。
- [x] 30 项 Python 测试通过，包含 ShapeUp multipart 桥接、输入校验、错误状态、坐标恢复、任务持久化、客户端恢复和旧 generic 协议。
- [x] Blender 5.1.2 构建并验证 v0.1.2 扩展 ZIP，以 `bl_ext.easykig_smoke.easykig` 命名空间启用、执行和禁用。
- [x] Blender 5.1.2 完整导出 → 模拟上游异步任务 → 暂停/恢复 → 下载/导入检查通过；源 Shape Keys 和毫米场景的世界坐标尺寸保持。恢复未重复提交任务。
- [x] 本机 EasyKig 网关通过实际 ShapeUp 跑完自带 fox 样例（geometry 30 steps、watertight 128、完整 texture），返回约 4.7 MB 带贴图 GLB。
- [x] 重启 EasyKig 网关后，使用同一实际任务 ID 重新下载成功。任务完成后 GPU 显存回到运行前水平。
- [x] 网关已加入现有 Supervisor 托管，与 ShapeUp 共用容器启动流程，空闲不加载 GPU 模型。

- [x] 用 Blender 4.5.4 构建扩展 ZIP，安装、启用并禁用扩展。禁用后场景属性与操作符已注销。
- [x] 演示模板提供 8 个可编辑 Shape Keys。外部网格的相对 Shape Keys 可读取，基底改名后也能正确识别。多对象集合可参与白模渲染。
- [x] MMD Tools 4.5.13 导入自制 PMX 文件，识别 Face 网格、两个材质和顶点 Morph。在毫米场景测得正确的物理尺寸。
- [x] 材质拆分仅作用于烘焙后的新副本，源网格材质和 Shape Keys 保持可用。
- [x] 渲染完整的 1024×1024 白模 PNG，确认原场景设置和数据块恢复。二进制 STL 尺寸已核对为毫米。
- [x] 自定义 HTTPS 网关通过 Blender 健康检查。网关通过本机 HTTPS 把请求转给测试上游，返回修改后的 GLB 并作为新网格导入。原始网格保持完整。
- [x] 错误令牌、读超时与服务断开返回可读错误。Python 测试通过，Compose 配置解析通过。
- [x] 可在网关加载逐字一致的参考 Prompt 预设。原文和署名由预设目录保管，公开源码使用 EasyKig 自带的默认 Prompt。

## 待验收

- [ ] Windows 本机到实际远端的自动 SSH 隧道与免 Token 验收，需要当前 SSH 地址、用户名和端口。仓库旧部署记录的真实推理验收发生在服务器环境。
- [ ] 在 Blender 中用两个授权的实际 Kig 模板验证 Shape Keys 和多对象组合。当前验证用的是自制网格。
- [ ] 使用授权的实际 PMX 核对材质名、脸部识别和 Morph 差异。当前 PMX 验收使用自制文件。
- [ ] 用可用图像额度生成 `finished_*.png`，人工确认与白模的角度、轮廓和五官一致。当前真实图片编辑请求收到供应商 HTTP 429。
- [ ] 在另一台实际 Blender 客户端通过 SSH 隧道或 HTTPS，使用授权 Kig 模板完成人工目视验收。本机已完成实际 ShapeUp 推理与模拟上游的 Blender 端自动验收。
- [ ] 在实际部署机运行 Docker Compose。
- [ ] 眼孔保护、内壳和后壳、壁厚与制造验证。面板标注为非制造级，文字调参为规则式。
