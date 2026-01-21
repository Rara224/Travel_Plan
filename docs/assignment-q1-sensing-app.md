# ELEG5600-ULTRA Sensing App — Q1

## 1) App name and URL links
- App name: **智能旅行助手（Sensing Trip Planner）**

本作业我建议提交 **公网可访问链接**（最不依赖课堂同网段环境），链接由本机端口通过隧道临时映射获得：

- Frontend URL (public tunnel): `https://<随机子域>.loca.lt/`
- Backend API docs (public tunnel): `https://<随机子域>.loca.lt/docs`

你在提交作业时，把上面两个 URL 替换成你实际启动隧道后输出的链接即可。

### 如何生成公网链接（推荐：localtunnel）

1) 启动后端（8000）
- 在 `helloagents-trip-planner/backend`：运行后端启动脚本（例如 `python run.py`）

2) 启动前端（5173）
- 在 `helloagents-trip-planner/frontend`：`npm run dev`

3) 打开两个隧道（前端 + 后端）
- 前端隧道：`npx localtunnel --port 5173`
- 后端隧道：`npx localtunnel --port 8000`

localtunnel 会打印类似：
- `your url is: https://xxxx.loca.lt`

那么你的可提交链接就是：
- Frontend: `https://xxxx.loca.lt/`
- Backend docs: `https://yyyy.loca.lt/docs`（后端会是另一个子域）

> 备注：如果 localtunnel 不稳定，可以用 Cloudflare Tunnel：
> - `cloudflared tunnel --url http://localhost:5173`
> - `cloudflared tunnel --url http://localhost:8000`

## 2) Utilized sensory information
本 App 使用（或可选使用）的传感器/感知信息如下：
- **Location / GPS**：通过浏览器 `Geolocation API` 获取设备当前经纬度、精度（accuracy）、速度（speed，可选）。
- **Orientation / Compass / IMU**：通过浏览器 `DeviceOrientationEvent` 获取设备朝向（heading，若设备/浏览器支持）或姿态角（alpha/beta/gamma）。
- **Motion / Accelerometer**：通过浏览器 `DeviceMotionEvent` 获取加速度信息，并用简单阈值判断用户是否在移动（is_moving）。

## 3) How sensors were utilized in the app
传感器数据会随旅行规划请求一起发送到后端（字段：`sensor_context`），并在行程生成时发挥作用：
- **基于当前位置的“从附近出发”规划**：若提供 GPS，经纬度会被用于提示模型“第 1 天游玩优先选择当前位置附近（例如 3km 内）的景点/餐饮/酒店作为出发点”，减少不必要的通勤距离。
- **基于运动状态的节奏调整**：若检测到用户在移动（例如步行/通勤中），行程会更偏向“紧凑路线/更近距离景点”；若静止或慢速，则可安排更宽松的节奏。
- **方向信息用于解释与偏好（辅助）**：若设备支持朝向角，会把当前方位（东/南/西/北）加入上下文，作为“从当前朝向方向优先选择附近 POI”的软约束（用于体现 orientation 传感器被实际消费）。

## Privacy & permission note (optional)
- 传感器采集为**可选**：用户不授权也可正常生成旅行计划。
- 浏览器会弹出权限请求（定位/方向/运动）；本实现只在用户点击按钮后采集一次并发送。
