# LanShare — 局域网屏幕共享（Windows）

在局域网内共享本机屏幕，并用另一台电脑观看和远程控制（类似向日葵的局域网用法，无需公网与账号）。

实现思路参考了以下开源项目（代码在 `_refs/`，仅供学习，未直接拷贝）：

| 项目 | 说明 |
|------|------|
| [NadirAliOfficial/nakdesk](https://github.com/NadirAliOfficial/nakdesk) | WebSocket 推 JPEG 帧 + Tk 客户端远程键鼠 |
| [qijungu/screenshare](https://github.com/qijungu/screenshare) | Flask 周期性截屏 + 浏览器观看（仅观看） |
| [jamesabel/remotedesktop](https://github.com/jamesabel/remotedesktop) | 纯局域网、UDP 自动发现（MIT，功能更完整） |
| [rustdesk/rustdesk](https://github.com/rustdesk/rustdesk) | 成熟远程桌面；局域网可直接用，体量较大 |

## 功能

- 本机 **开始共享**：UDP 广播，局域网内自动出现在列表
- **观看端**：双击列表或手动输入 `IP:端口` 连接
- 可选 **连接密码**、**仅观看**（关闭「允许远程键鼠」）
- 默认端口 `8765`，可在界面修改

## 使用者（推荐）— 零依赖

**不用装 Python、不用 pip。** 使用打包好的绿色版即可：

| 形态 | 拷贝内容 |
|------|----------|
| 文件夹版 | 整个 `LanShare-win32-x64\`，双击 `LanShare.exe` |
| 单文件版 | 仅 `LanShare.exe`（首次启动略慢） |

自己打包：在 Windows 上运行 `build.bat`（文件夹）或 `build-onefile.bat`（单 exe）。  
也可把仓库推到 GitHub 后，在 **Actions → Build Windows client → Run workflow** 下载构建产物，同样无需在使用者电脑上装依赖。

## 开发者 — 源码调试

仅改代码时需要 Python 3.10+：

```powershell
pip install -r requirements.txt
python main.py
```

## 防火墙

首次共享时请在 Windows 防火墙中允许 Python 的 **专用网络** 入站（或放行 TCP `8765`、UDP `45678`）。

## 打包为独立 Windows 客户端（推荐）

在 **Windows** 上进入本目录，双击或在 cmd 中运行：

```bat
build.bat
```

完成后将 **`dist\LanShare-win32-x64\` 整个文件夹** 拷贝到 U 盘或其它电脑即可（与 Electron 应用一样：文件夹内双击 `LanShare.exe`）。无需安装 Python。内含 `使用说明.txt`。

界面可勾选 **开机自启**、**启动后自动开始共享**（设置保存在 `%APPDATA%\LanShare\`）。

手动打包：

```bat
pip install -r requirements-build.txt
pyinstaller --noconfirm LanShare.spec
```

> 打包需在 Windows 上执行（PyInstaller 无法在本仓库的 Linux 环境直接生成 `.exe`）。

## 协议简述

- 发现：UDP `45678` 广播 JSON `{"name","ip","port"}`
- 画面：WebSocket `8765`，二进制帧 `F` + 宽高 + JPEG
- 控制：WebSocket JSON（`mm`/`mc`/`ms`/`kp`/`kr`）

## 许可

本项目示例代码可自由使用。参考仓库各自遵循其原许可证（如 GPL、MIT）。
