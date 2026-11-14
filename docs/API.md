# EasyKig Gateway API v0.1.2

默认网关地址：`http://127.0.0.1:8001`，对所有 POST 接口发送 `Authorization: Bearer <EASYKIG_SERVER_TOKEN>`。

网关的默认认证模式为 `EASYKIG_AUTH_MODE=token`。使用 SSH 隧道时可在服务器设置
`EASYKIG_AUTH_MODE=ssh`，通过 `scripts/run_gateway.py` 绑定回环地址并禁用代理地址头解析。
此模式下业务接口按实际 TCP 来源接受回环请求，客户端可省略 Authorization。
非回环来源返回 403。远端 sshd 在服务器上建立回环连接，因此 Blender 可通过隧道访问。
ShapeUp 上游的私有令牌继续由服务器配置和读取。

## `GET /health`

无需鉴权。返回 `status`、`version`、`preview_enabled` 和 `mesh_editor_enabled`。后两个字段表示已配置相应凭据或上游地址。
`auth_mode` 返回 `token` 或 `ssh`，省略该字段的旧网关按 Token 模式连接。
3D 能力字段包括 `mesh_editor_backend`（`generic|shapeup`）、`mesh_editor_async` 和 `mesh_editor_requires_image`。这些是配置能力；ShapeUp 实际就绪状态通过鉴权的 `GET /v1/edit3d/health` 检查。
同时返回 `image_model`（默认模型）和 `image_models`（允许选择的模型 ID 列表）。

## `GET /v1/image/models`

使用网关 Bearer Token 鉴权。查询参数 `provider=gateway|chatgpt_credits`，返回所选来源的 `image_models` 及默认 `image_model`。ChatGPT API credits 路径使用关联 API 组织的项目密钥从 OpenAI 查询模型。

## `POST /v1/edit/parameters`

请求：

```json
{
  "prompt": "脸颊更圆一些，眼睛大一点",
  "shape_keys": {"Eye Size": 0.2, "Cheek Fullness": 0.3},
  "ranges": {"Eye Size": [0, 1], "Cheek Fullness": [0, 1]}
}
```

响应：

```json
{
  "shape_keys": {"Eye Size": 0.38, "Cheek Fullness": 0.48},
  "changes": {"Eye Size": 0.38, "Cheek Fullness": 0.48},
  "mode": "rules",
  "message": "Rule-based edit; review visually."
}
```

仅支持现有 Shape Keys，插件端进一步裁剪值域。规则基线不代表 AI 模型。

## `POST /v1/reference/transform`

请求 `{"stage":"head|design|product","source_png_base64":"...","prompt":"..."}`，响应 `{"image_png_base64":"...","stage":"head|design|product","mode":"image_edit"}`。每张图限 8 MiB PNG。可用 `additional_png_base64` 追加最多 6 张图，按数组顺序发送给供应商。配置 `EASYKIG_REFERENCE_PROMPTS_DIR` 时按阶段发送对应的 UTF-8 预设原文，忽略请求的 `prompt`。图像模型需要 `OPENAI_IMAGE_API_KEY`。

## `POST /v1/image/reference-prompt`

请求 `{"stage":"head|design|product","prompt":"..."}`，响应 `{"prompt":"..."}`。使用和 `/v1/reference/transform` 相同的预设加载逻辑。Blender 直连图像 API 时可以单独取得 Prompt。

## `POST /v1/preview/finish`

请求 `{"white_png_base64":"...","reference_png_base64":"... (optional)","prompt":"..."}`，响应 `{"image_png_base64":"...","mode":"image_edit","warning":"..."}`。源图限 8MB PNG。

可通过 `additional_png_base64` 提供最多 3 张补充参考图。网关将白模作为第一张图，其余参考图用于配色和风格。`GET /health` 的 `multi_reference_images` 表示网关支持此字段和参考图接口的新上限。

两个图像接口都接受可选的 `provider` 和 `model`。省略 `provider` 时使用网关默认来源。显式选 `chatgpt_credits` 时请求使用 `OPENAI_SUBSCRIPTION_API_KEY`。模型可从 `/v1/image/models` 获取。

## `POST /v1/edit3d`

请求：

```json
{
  "prompt": "Make the chin shorter, keep the existing eye openings",
  "mesh_glb_base64": "<base64 of binary GLB, max 20MB>"
}
```

响应：

```json
{
  "mesh_glb_base64": "<base64 of edited binary GLB>",
  "mode": "upstream"
}
```

此同步接口保留 `generic` 后端原有的文字 + GLB 协议。设置
`EASYKIG_EDIT3D_BACKEND=shapeup` 时返回 409，指引客户端使用下面的图像条件异步任务。
未配置上游时返回 501。

## ShapeUp 后端配置

```dotenv
EASYKIG_EDIT3D_BACKEND=shapeup
EASYKIG_EDIT3D_UPSTREAM_URL=http://127.0.0.1:8000
EASYKIG_EDIT3D_UPSTREAM_TOKEN_FILE=/data/ShapeUp/runtime/api-token
EASYKIG_EDIT3D_JOB_DIR=runtime/edit3d-jobs
```

上游 URL 和凭据由服务器配置，客户端不能指定。HTTP 仅允许 localhost/SSH 隧道；其他地址使用 HTTPS。
也可用 `EASYKIG_EDIT3D_UPSTREAM_TOKEN` 直接配置上游令牌，它优先于令牌文件。

## `GET /v1/edit3d/health`

需要网关 Bearer Token。检查 ShapeUp 的 `/readyz`，就绪时返回 200 和
`{"backend":"shapeup","ready":true,...}`。GPU/权重未就绪返回 503，上游凭据错误返回 502。

## `POST /v1/edit3d/jobs`

需要网关 Bearer Token。请求示例：

```json
{
  "mesh_glb_base64": "<source GLB, max 20 MiB>",
  "edit_png_base64": "<target PNG, max 8 MiB>",
  "seed": 10,
  "steps": 30,
  "watertight_resolution": 512
}
```

`seed` 默认 10，范围 0–4294967295；`steps` 默认 30，范围 1–100；
`watertight_resolution` 为 128、256 或 512。文字 `prompt` 可以保留作为客户端输入，
ShapeUp 由目标图像引导，不使用文字条件。此接口不会额外调用图像生成 API。

网关校验输入，将 GLB 和目标 PNG 作为 multipart 文件转发到 ShapeUp 的 `/jobs`，
返回 HTTP 202：`{"id":"<32位十六进制任务ID>","status":"queued","backend":"shapeup"}`。
上游队列满返回 429。网关保存源 GLB 的中心和尺度，用于恢复结果坐标。

## `GET /v1/edit3d/jobs/{id}`

需要网关 Bearer Token。返回 `id`、`status`、可用的时间戳、失败时的 `error` 与 `backend`。
状态为 `queued`、`running`、`succeeded`、`failed`。任务只在 POST 时提交；
查询、恢复等待和重复下载不会重新触发 GPU 生成。未知任务返回 404，非法 ID 返回 422。

## `GET /v1/edit3d/jobs/{id}/result`

需要网关 Bearer Token。未完成时返回 409；成功时返回二进制 `model/gltf-binary`，
最大 20 MiB。网关在 CPU 上还原 ShapeUp 的 bbox 中心/尺度，并保留贴图。
输入 GLB 应符合 glTF 的米单位约定；Blender 插件负责场景单位换算。
结果坐标系与上传源模型一致，具体编辑仍可改变形状和尺寸。

暂停客户端等待不会取消上游任务。任务状态保存在 ShapeUp；网关的中心/尺度恢复信息
保存在 `EASYKIG_EDIT3D_JOB_DIR`，需与后端任务数据一起保留，便于重启后恢复。

## 设计与安全边界

- 大请求：单输入 PNG 不超过 8 MB，输入 GLB 不超过 20 MB。
- 反向代理应限制请求体大小和超时，并配置 HTTPS 与鉴权。
- 网关仅在环境变量指定的 API/上游 URL 上发起请求；远端地址不由 Blender 上传参数控制，避免任意 SSRF。
- Token 模式的 `Authorization` 令牌保存在用户本机 Blender 偏好设置，通过 HTTPS 或 SSH 隧道使用。SSH 模式按回环连接来源鉴权，Uvicorn 应关闭代理地址头解析。
- ShapeUp 编辑使用异步任务队列；旧 generic 编辑接口保持同步 HTTP。网关、插件均不常驻 GPU 模型。
