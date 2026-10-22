# Pixel Minecraft Launcher
这是一个由bilibili UP主driver166使用Python开发的一个新生代图形化启动器。

## 功能

- 下载中心：版本下载（正式版/测试版/愚人节/远古 + 搜索）、模组下载（Modrinth 搜索安装）、整合包/资源包/光影预留
- 游戏版本删除与启动（支持离线账户）
- Forge / Fabric 模组加载器安装与加载器版本选择
- Java 自动扫描：全盘查找 java.exe 并缓存版本，启动时校验缓存，可手动刷新
- 模组、资源包、光影、存档管理
- NBT 查看/编辑器（树形展开、改值、增删键、物品图标悬停、物品选择器，保存自动备份）
- 版本隔离（隔离mod / 完全隔离）
- 服务器启动与管理
- 下载进度查看（下载时「查看下载进度」按钮从左侧滑出，点击进入独立的下载进度页面）
- 一键关闭所有正在运行的 Minecraft 游戏（检测到游戏运行时才显示按钮）
- 基于 maliang 的界面，支持透明度和背景颜色自定义

## 运行

```bash
pip install -r requirements.txt
python main.py
```

需要 Python 3.11+，并安装 Java（启动游戏、安装 Forge/Fabric 时使用）。

## 说明

- 首次运行会在同目录生成 `PML/PML.config`，保存用户名、Java、服务器、Token 等设置，**请勿提交到仓库**。
- 访问 Mojang 失败时会自动尝试 BMCLAPI 镜像。
- `source code/` 下保留历史版本源码，仓库只维护根目录的 `main.py`。
