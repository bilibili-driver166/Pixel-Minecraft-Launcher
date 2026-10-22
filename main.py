import tkinter as tk
import tkinter.ttk as ttk
import minecraft_launcher_lib as mll
import os
import time
import ast
import gzip
import hashlib
import inspect
import io
import json
import locale
import queue
import re
import struct
import urllib.request
import uuid
import maliang.animation as animation
import tkinter.messagebox as messagebox
import tkinter.colorchooser
import tkinter.filedialog
import colorama
import webbrowser
import shutil
import subprocess
import sys
import maliang
import threading
import pymsgbox
import maliang.theme as theme


CONFIG_PATH = "./PML/PML.config"
JAVA_SEARCH_DIRS = ("C:/Program Files/Java", "C:/Program Files (x86)/Java")
BMCLAPI_FORGE_URL = "https://bmclapi2.bangbang93.com/forge/minecraft/{version}"
BMCLAPI_FABRIC_LOADER_URL = "https://bmclapi2.bangbang93.com/fabric-meta/v2/versions/loader"
BMCLAPI_FABRIC_GAME_URL = "https://bmclapi2.bangbang93.com/fabric-meta/v2/versions/game"
BMCLAPI_VERSION_MANIFEST = (
    "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"
)
# 版本隔离模式
ISOLATION_NONE = 0
ISOLATION_MOD = 1
ISOLATION_FULL = 2
ISOLATION_VALUES = ["不开启版本隔离", "隔离mod", "完全隔离"]
_NOT_GIVEN = object()

# 官方下载地址 -> BMCLAPI 镜像地址, 官方源失败时自动回退
MIRROR_HOSTS = (
    ("https://launchermeta.mojang.com", "https://bmclapi2.bangbang93.com"),
    ("https://piston-meta.mojang.com", "https://bmclapi2.bangbang93.com"),
    ("https://piston-data.mojang.com", "https://bmclapi2.bangbang93.com"),
    ("https://launcher.mojang.com", "https://bmclapi2.bangbang93.com"),
    ("https://libraries.minecraft.net", "https://bmclapi2.bangbang93.com/maven"),
    (
        "https://resources.download.minecraft.net",
        "https://bmclapi2.bangbang93.com/assets",
    ),
    ("https://files.minecraftforge.net/maven", "https://bmclapi2.bangbang93.com/maven"),
    ("https://maven.minecraftforge.net", "https://bmclapi2.bangbang93.com/maven"),
    ("https://maven.fabricmc.net", "https://bmclapi2.bangbang93.com/maven"),
    ("https://meta.fabricmc.net", "https://bmclapi2.bangbang93.com/fabric-meta"),
    ("https://maven.neoforged.net/releases", "https://bmclapi2.bangbang93.com/maven"),
)


def mirror_url(url):
    """把官方下载地址转换成 BMCLAPI 镜像地址"""
    url = str(url)
    for source, target in MIRROR_HOSTS:
        if url.startswith(source):
            return target + url[len(source) :]
    return url


_MIRROR_STATE = {"prefer": False}


def enable_bmclapi_fallback():
    """让 minecraft-launcher-lib 在官方源失败时自动改用 BMCLAPI 镜像"""
    try:
        import minecraft_launcher_lib  # noqa: F401
        import minecraft_launcher_lib._helper  # noqa: F401
    except Exception as exp:
        print(f"[WARN] 无法启用镜像回退: {exp}")
        return

    modules = [
        module
        for name, module in list(sys.modules.items())
        if name == "minecraft_launcher_lib" or name.startswith("minecraft_launcher_lib.")
    ]
    try:
        import requests

        network_errors = (requests.exceptions.RequestException, OSError)
    except Exception:
        network_errors = (OSError,)

    def wrap(original):
        if getattr(original, "_pml_mirror_wrapped", False):
            return original

        def wrapper(url, *args, **kwargs):
            url = str(url)
            mirrored = mirror_url(url)
            if mirrored == url:
                return original(url, *args, **kwargs)

            # 一旦确认官方源不可用, 之后的请求直接走镜像, 避免每个文件都卡一次
            if _MIRROR_STATE["prefer"]:
                try:
                    return original(mirrored, *args, **kwargs)
                except network_errors:
                    return original(url, *args, **kwargs)

            try:
                return original(url, *args, **kwargs)
            except network_errors as exp:
                print(f"[WARN] 官方源请求失败, 改用镜像: {type(exp).__name__}")
                result = original(mirrored, *args, **kwargs)
                if result is not False and result is not None:
                    _MIRROR_STATE["prefer"] = True
                    print("[INFO] 后续下载将优先使用 BMCLAPI 镜像")
                return result

        wrapper._pml_mirror_wrapped = True
        wrapper._pml_original = original
        return wrapper

    for module in modules:
        for attribute in ("download_file", "get_requests_response_cache"):
            function = getattr(module, attribute, None)
            if callable(function) and not getattr(
                function, "_pml_mirror_wrapped", False
            ):
                setattr(module, attribute, wrap(function))


def read_text_file(path):
    """读取文本文件: 优先使用 UTF-8, 同时兼容旧版本写入的 GBK 文件"""
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def strip_config_value(value):
    """去掉配置值两端的引号"""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def parse_config_list(raw):
    """解析配置中的列表, 兼容旧版本写入的格式"""
    raw = (raw or "").strip()
    if raw in ("", "[]"):
        return []
    try:
        value = ast.literal_eval(raw)
        if isinstance(value, (list, tuple)):
            return [str(i) for i in value]
    except (ValueError, SyntaxError):
        pass
    result = []
    for item in raw.split(", "):
        item = strip_config_value(item)
        result.append(item)
    return result


def offline_uuid(username: str) -> str:
    """根据用户名生成离线账户的 UUID(与正版离线模式的算法一致)"""
    data = hashlib.md5(("OfflinePlayer:" + username).encode("utf-8")).digest()
    data = bytearray(data)
    data[6] = (data[6] & 0x0F) | 0x30
    data[8] = (data[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(data)))


def supports_java_argument(func) -> bool:
    """判断 minecraft-launcher-lib 的函数是否支持 java 参数(兼容旧版本库)"""
    try:
        return "java" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def parse_java_major(version: str) -> int:
    """从 '1.8.0_341' / '17.0.2' / '21' 这类版本号中取出主版本号"""
    match = re.search(r"\d+", str(version))
    if match is None:
        raise ValueError(version)
    first = int(match.group())
    if first == 1:
        parts = str(version).split(".")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
    return first


def forge_version_key(version: str):
    """把 Forge 版本号转换成可以比较数字大小的元组"""
    return tuple(int(i) for i in re.findall(r"\d+", version))


def required_java_version(minecraft_version: str) -> int:
    """返回该 Minecraft 版本所需的 Java 主版本号, 无法识别时返回 0(不做限制)"""
    try:
        parts = [int(i) for i in str(minecraft_version).split(".")[:3]]
    except ValueError:
        return 0
    if len(parts) < 2 or parts[0] != 1:
        return 0
    minor = parts[1]
    patch = parts[2] if len(parts) > 2 else 0
    if minor >= 21 or (minor == 20 and patch >= 5):
        return 21
    if minor >= 18:
        return 17
    if minor == 17:
        return 16
    return 8


# ---------------------------------------------------------------------------
# NBT 只读解析(用于 NBT 查看器)
# ---------------------------------------------------------------------------
NBT_END = 0
NBT_BYTE = 1
NBT_SHORT = 2
NBT_INT = 3
NBT_LONG = 4
NBT_FLOAT = 5
NBT_DOUBLE = 6
NBT_BYTE_ARRAY = 7
NBT_STRING = 8
NBT_LIST = 9
NBT_COMPOUND = 10
NBT_INT_ARRAY = 11
NBT_LONG_ARRAY = 12

NBT_TAG_NAMES = {
    NBT_END: "End",
    NBT_BYTE: "Byte",
    NBT_SHORT: "Short",
    NBT_INT: "Int",
    NBT_LONG: "Long",
    NBT_FLOAT: "Float",
    NBT_DOUBLE: "Double",
    NBT_BYTE_ARRAY: "Byte[]",
    NBT_STRING: "String",
    NBT_LIST: "List",
    NBT_COMPOUND: "Compound",
    NBT_INT_ARRAY: "Int[]",
    NBT_LONG_ARRAY: "Long[]",
}
NBT_MAX_DEPTH = 256
NBT_MAX_ELEMENTS = 10_000_000


class NbtTag:
    """一个 NBT 标签(只读)"""

    __slots__ = ("tag_type", "name", "value", "element_type")

    def __init__(self, tag_type, value=None, name="", element_type=None):
        self.tag_type = tag_type
        self.value = value
        self.name = name
        self.element_type = element_type


class _NbtReader:
    """读取大端 NBT 数据"""

    def __init__(self, data):
        self.data = data
        self.size = len(data)
        self.pos = 0

    def read(self, length):
        end = self.pos + length
        if end > self.size:
            raise ValueError("NBT 数据不完整")
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def read_u8(self):
        return self.read(1)[0]

    def read_i8(self):
        return struct.unpack(">b", self.read(1))[0]

    def read_i16(self):
        return struct.unpack(">h", self.read(2))[0]

    def read_i32(self):
        return struct.unpack(">i", self.read(4))[0]

    def read_i64(self):
        return struct.unpack(">q", self.read(8))[0]

    def read_f32(self):
        return struct.unpack(">f", self.read(4))[0]

    def read_f64(self):
        return struct.unpack(">d", self.read(8))[0]

    def read_string(self):
        length = struct.unpack(">H", self.read(2))[0]
        return self.read(length).decode("utf-8", errors="replace")

    def read_payload(self, tag_type, depth=0):
        if depth > NBT_MAX_DEPTH:
            raise ValueError("NBT 嵌套层数过多")
        if tag_type == NBT_BYTE:
            return NbtTag(tag_type, self.read_i8())
        if tag_type == NBT_SHORT:
            return NbtTag(tag_type, self.read_i16())
        if tag_type == NBT_INT:
            return NbtTag(tag_type, self.read_i32())
        if tag_type == NBT_LONG:
            return NbtTag(tag_type, self.read_i64())
        if tag_type == NBT_FLOAT:
            return NbtTag(tag_type, self.read_f32())
        if tag_type == NBT_DOUBLE:
            return NbtTag(tag_type, self.read_f64())
        if tag_type == NBT_BYTE_ARRAY:
            length = self.read_i32()
            if length < 0 or length > NBT_MAX_ELEMENTS:
                raise ValueError("Byte 数组长度异常")
            return NbtTag(tag_type, self.read(length))
        if tag_type == NBT_STRING:
            return NbtTag(tag_type, self.read_string())
        if tag_type == NBT_LIST:
            element_type = self.read_u8()
            length = self.read_i32()
            if length < 0 or length > NBT_MAX_ELEMENTS:
                raise ValueError("List 长度异常")
            items = [
                self.read_payload(element_type, depth + 1) for _ in range(length)
            ]
            return NbtTag(tag_type, items, element_type=element_type)
        if tag_type == NBT_COMPOUND:
            children = {}
            while True:
                child_type = self.read_u8()
                if child_type == NBT_END:
                    break
                child_name = self.read_string()
                child = self.read_payload(child_type, depth + 1)
                child.name = child_name
                children[child_name] = child
            return NbtTag(tag_type, children)
        if tag_type == NBT_INT_ARRAY:
            length = self.read_i32()
            if length < 0 or length > NBT_MAX_ELEMENTS:
                raise ValueError("Int 数组长度异常")
            raw = self.read(length * 4)
            values = list(struct.unpack(">%di" % length, raw)) if length else []
            return NbtTag(tag_type, values)
        if tag_type == NBT_LONG_ARRAY:
            length = self.read_i32()
            if length < 0 or length > NBT_MAX_ELEMENTS:
                raise ValueError("Long 数组长度异常")
            raw = self.read(length * 8)
            values = list(struct.unpack(">%dq" % length, raw)) if length else []
            return NbtTag(tag_type, values)
        raise ValueError(f"不支持的 NBT 类型: {tag_type}")


def read_nbt_file(path):
    """读取 .dat / .nbt 文件, 自动识别 gzip 压缩"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except OSError as exp:
            raise ValueError(f"gzip 解压失败: {exp}")
    reader = _NbtReader(data)
    tag_type = reader.read_u8()
    if tag_type == NBT_END:
        raise ValueError("文件里没有 NBT 数据")
    name = reader.read_string()
    root = reader.read_payload(tag_type)
    root.name = name
    return root


def nbt_type_name(tag_type):
    return NBT_TAG_NAMES.get(tag_type, f"TAG_{tag_type}")


def nbt_type_label(tag):
    if tag.tag_type == NBT_LIST and tag.element_type is not None:
        return f"List<{nbt_type_name(tag.element_type)}>"
    return nbt_type_name(tag.tag_type)


def nbt_preview(text, limit=120):
    text = " ".join(str(text).split())
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def nbt_summary(tag):
    """返回树形列表里"值"一列显示的摘要"""
    tag_type = tag.tag_type
    value = tag.value
    if tag_type in (NBT_BYTE, NBT_SHORT, NBT_INT, NBT_LONG):
        return str(value)
    if tag_type in (NBT_FLOAT, NBT_DOUBLE):
        return f"{value:g}" if isinstance(value, float) else str(value)
    if tag_type == NBT_STRING:
        return '"' + nbt_preview(value) + '"'
    if tag_type in (NBT_BYTE_ARRAY, NBT_INT_ARRAY, NBT_LONG_ARRAY):
        return f"长度 {len(value)}"
    if tag_type == NBT_LIST:
        return f"{len(value)} 项"
    if tag_type == NBT_COMPOUND:
        return f"{len(value)} 个键"
    return ""


class Progressbar:
    def __init__(self, master, place_x, place_y, max_value, orient="vertical"):
        self.place_x = place_x
        self.place_y = place_y
        self.max = max_value
        self.master = master
        self.orient = orient
        self._var = tk.IntVar()

    def place(self):
        self.main_place = ttk.Progressbar(
            self.master,
            maximum=self.max,
            orient=self.orient,
            variable=self._var,
            length=500,
        )
        self.main_place.place(x=self.place_x, y=self.place_y)

    def get_progress(self):
        return self._var.get()

    def set_progress(self, value):
        def main():
            for i in range(self._var.get(), value + 1, 1):
                self._var.set(i)
                self.main_place.update()
                time.sleep(0.1)

        threading.Thread(target=main).start()

    def destroy(self):
        self.main_place.destroy()


class MinecraftLauncher:
    def checkfiles(self):
        if os.path.isdir("./PML"):
            ddd = open("./PML/ddd.ico", "wb")
            ddd.write(
                b'\x00\x00\x01\x00\x01\x00\x80\x80\x00\x00\x00\x00\x00\x00\xed\x04\x00\x00\x16\x00\x00\x00\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x80\x00\x00\x00\x80\x08\x06\x00\x00\x00\xc3>a\xcb\x00\x00\x00\x01sRGB\x00\xae\xce\x1c\xe9\x00\x00\x04\xa7IDATx^\xed\x9d\xdbu\x141\x10D\xdbA8\t\x1f\x82\x80\x1cx\x84\x03\x84\xc3#\x07 \t\x82\xc0A\x80\xc7\xc7\x87\x0f{\x17WQ#\x8dV\xba\xfb\xdd-\xa9\xab\xaez4\xb3\xb3\xf6U\xf1YZ\x81\xab\xa5\xab\xa7\xf8\x02\x80\xc5!\x00\x00\x00X\\\x81\xc5\xcb\xa7\x03\x00\xc0\xe2\n,^>\x1d\x00\x00\x16W`\xf1\xf2\xe9\x00\x00\xb0\xb8\x02\x8b\x97O\x07\x00\x80\xc5\x15X\xbc|:\x00\x00,\xae\xc0\xe2\xe5\xd3\x01\x00 V\xe0w<\x02\x03$\nD\x9b8J~X5\x00$\xf6\xe5\xb9\x91\x87Q2\x00\xe4\xee\xed0B\xe4a\x94\x0c\x00;\xd8\x97\x0f\x11y\x18%\x03@\xee\xde\x0e#D\x1eF\xc9\x00\xb0\x83}\xf9\x10\x91\x87Q2\x00\xe4\xee\xed0B\xe4a\x94\x0c\x00;\xd8\x97\x0f\x11y\x18%\x03@\xee\xde\x0e#D\x1eF\xc9\x00\xb0\x83}\xf9\x10\x91\x87Q\xb2\t\xc0mU\xfd\xcc\xeb]b\x84\x9b\xaa\xba\x16+\x8d<\x8c\x92M\x00\xbe\xdc\x01\xf0V,j\xf5\xb0M\xab\xd7\xa2\x08\x91\x87Q2\x00\x88\x16\xf9a\x00\xe0k6U\x06\x00Le\xa7_\x0c\x00\xf8\x9aM\x95\x01\x00S\xd9\xe9\x17\x03\x00\xbefSe\x00\xc0Tv\xfa\xc5\x00\x80\xaf\xd9T\x19\x000\x95\x9d~1S\x02\xf0\xb9\xaa\xde\x89Z\xbc\xaf\xaaWbl\x8b\xb0m\xfe\x1f-\x06\x16\xc7\xfcd<5\x8d\x1e\xe6E\xc9\r\x9f\x04:;@\xd4\xd4\n\xdb\x1eYok8\xea\xe3\xd4\x1fy\x18%\x03@3>\x00\xc0\xf82\xa4\x85\x0bt\x00CU\xf5w\x01\xce\xb7\x81\xce\x0e0\x96*\x87\x02\x80,U\x15\x00\x18b\x89\xa1\xce\x06\x88.\xe3Q2g\x00\xd1N?\x0c\x008\x03\xac\xfdB\x88\xb3\x03\xfc\xfd\xf5|\x06g\x80\xe75\xfa\x1b\xc1\x19\xc0\x10K\x0cu6@t\x19\x8f\x929\x03\x88v\xfaa\x00`\x9c\x01T\x88\xb7\xb6\xbe=bU>\\\x02\x14\x95\x06\xe9\x00\x00`\x98\xf58T\x15\xef_S\x1c}\x06Pk\xa0\x03\x9cpQ\x15\x0f\x00\x82]\xf6\x1f\xa9\x9c\x018\x03\xf0\x1c`\xef_\xc6p\t\xe0\x12\xc0]\x00\x87@\xed\x82\xccm\xa0\xa6\xd3}\x14w\x01\x86Xb(\x87@\x0e\x81\xf3\x1d\x02\x9d\x97B\x9d\x97"\xd5\x97G_\xdeu\xab\xedeO\xe5\xf3\xa6\xaa\xbe*\x81U\xb5\x8d\xab|~\x19\x7f\x1f\xc1\xa9?\xba\x95\x8f\x92\x07y\x12\xa8\x88\xef\xc68g\x80K\xb9\x04\x9e\xd4\x00\x00N\xa3\x01\x00\xc6\x969z\x07\x18K\x95C\x01@\x96\xea\xf8\xbb\x00c\xa9r(\x00\xc8R\x01\xc0\xd1\x1d0\xba\x8cG\xc9\x1c\x02/\xea9\x08\x87@\xa3\xabq\t0\xc4:\xba\x05\x1aK\x95C\x01@\x96\x8a3\xc0\xd1\x1b \xba\x8cG\xc9\x9c\x018\x03l\n\xa8;\xe0\xe8G\xc1FS\xbb\x7f\x0e\xffBL\xf8 \xc6\xf1(\xd8\xf8\xa3\x07\xdd\xbe\r;c\xde2\xf3\xcfp\t\xd8\xa3\x86\xc7\x1c\x00\x80\xd8\xd6\x9cK@\xab\x9f\x87\x03\x80a\xd6\xe3\xd0=\xc4S\xcf\x00\x00\xa0\x1b\xd5\xad\x03\x01\xc0iS\xba\x19p\xf4\x19\x04\x00\x00@\xefKg"\xb9\x04\xc4\x12>\x19\xa0[\x07\xa2\x03\xd0\x01b|\xe9\x00\xb1\x84t\x80e\xef\xc39\x04\xee\xbf{\xce\x8d\xd8\xea\xa7a\x17\xdd\x01G=\x03\xb4\xc0\x02\x00N\xa8\n\x00\xa7Q\xe3}\x00c\x0b\xb6h\x81\xc6\xf4r(\x1d\x80\x0e\xd0\xe4\xd7\xc1-6\xc0\xf2\xcf\x01\xe4mm\x04\xd2\x01\xe8\x00t\x80K\xf96\xd0\xd8\xd8r(\x1d\x80\x0e@\x07\xa0\x03h\r\x83\xdb@M\xa7\xfb(\xf5\x14\xec\xbc\x14jL/\x87n\xbf\xe3W_\xe0t\xfei\xd4wq\x05\xdf\xaa\xea\xa3\x18\xbb\xfc\xdf\x07\x10u\x9a6\x8c\xdb\xc0i\xad\xd5\n\x03\x00M\xa7i\xa3\x00`Zk\xb5\xc2\x00@\xd3i\xda(\x00\x98\xd6Z\xad0\x00\xd0t\x9a6\n\x00\xa6\xb5V+\x0c\x004\x9d\xa6\x8d\x02\x80i\xad\xd5\n\x9b\x12\x80[\xe3O\xa5j2\xcd\x1buSU\xd7by\xd1k}Q\xf2\xc3\x02\xd5\xef\x02\xc4z\x083\x15\x88<\x8c\x92\x01\xc0\xb4\xaaMx\xe4a\x94\x0c\x00m\x1c5G\x8d<\x8c\x92\x01\xc0\xb4\xaaMx\xe4a\x94\x0c\x00m\x1c5G\x8d<\x8c\x92\x01\xc0\xb4\xaaMx\xe4a\x94\x0c\x00m\x1c5G\x8d<\x8c\x92\x01\xc0\xb4\xaaMx\xe4a\x94\x0c\x00m\x1c5G\x8d<\x8c\x92\x01\xc0\xb4\xaaMx\xe4a\x94\xdc\xa6\x1eF\xed\xa9\x00\x00\xf4T{\xc0\xb9\x00`@Sz.\t\x00z\xaa=\xe0\\\x000\xa0)=\x97\x04\x00=\xd5\x1ep.\x00\x18\xd0\x94\x9eK\x02\x80\x9ej\x0f8\x17\x00\x0chJ\xcf%\x01@O\xb5\x07\x9c\x0b\x00\x064\xa5\xe7\x92\x00\xa0\xa7\xda\x03\xce\x05\x00\x03\x9a\xd2sI\x00\xd0S\xed\x01\xe7\x02\x80\x01M\xe9\xb9$\x00\xe8\xa9\xf6\x80s\xfd\x01\x1d\x94\x9d\x90\xcch\xf3&\x00\x00\x00\x00IEND\xaeB`\x82'
            )
            ddd.close()
            if not os.path.exists(CONFIG_PATH) or (
                read_text_file(CONFIG_PATH).strip() == ""
            ):
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    f.write(
                        "UsernameList = []\n"
                        "alpha = 0.85\n"
                        "ServerList = []\n"
                        'Background = ""\n'
                        "ServerPath = []\n"
                        'LastDict = ""\n'
                        'LastLaunch = ""\n'
                        'LastUsername = ""\n'
                        'Token = ""\n'
                        "VerSplit = 0\n"
                        "curJava = 0\n"
                        "exJava = []\n"
                    )
        else:
            os.mkdir("PML")
            self.checkfiles()

    def read_configs(self):
        config_text = read_text_file(CONFIG_PATH)
        for line in config_text.split("\n"):
            if " = " not in line:
                continue
            key, value = line.split(" = ", 1)
            key = key.strip().lower()
            value = value.strip()
            try:
                if key == "lastdict":
                    self.minecraft_dir = strip_config_value(value)
                elif key == "lastlaunch":
                    selected_version = strip_config_value(value)
                    if selected_version:
                        self.selected_version = selected_version
                elif key == "lastusername":
                    username = strip_config_value(value)
                    if username:
                        self.Username = username
                elif key == "usernamelist":
                    self.UsernameList = parse_config_list(value)
                elif key == "serverlist":
                    self.ServerList = parse_config_list(value)
                elif key in ("background", "backgroud"):
                    background = strip_config_value(value)
                    if background:
                        self.bg = background
                elif key == "token":
                    self.Token = strip_config_value(value)
                elif key == "serverpath":
                    self.ServerPath = parse_config_list(value)
                elif key == "versplit":
                    self.Versplitvar = int(float(strip_config_value(value)))
                elif key == "curjava":
                    self.CurJavaVar = int(float(strip_config_value(value)))
                elif key == "exjava":
                    self.exjavaplace = parse_config_list(value)
                elif key == "alpha":
                    self.alpha = float(strip_config_value(value))
            except (TypeError, ValueError):
                # 忽略损坏的配置项, 继续读取其它内容
                continue
        if not self.minecraft_dir:
            # 没有设置过游戏目录时使用默认的 .minecraft 目录
            try:
                self.minecraft_dir = mll.utils.get_minecraft_directory().replace(
                    "\\", "/"
                )
            except Exception as exp:
                print(f"[WARN] 无法获取默认游戏目录: {exp}")
                self.minecraft_dir = os.path.abspath(".minecraft").replace("\\", "/")

    def init_var(self):
        self.UsernameList = []
        self.CurJavaVar = 0
        self.ServerList = []
        self.exjavaplace = []
        self.ServerPath = []
        self.minecraft_dir = ""
        self.selected_version = "暂无数据"
        self.Username = "暂无数据"
        self.current_username = ""
        self.bg = None
        self.alpha = 0.85
        self.Versplitvar = 0
        self.Token = None
        self.support_mod = False
        self.modlistlist = []
        self._java_entries = None
        self.read_configs()
        self.save_selected = ""
        self.current_max = 0
        try:
            self.downloaded_minecraft_versions = os.listdir(
                os.path.join(self.minecraft_dir, "versions")
            )
        except OSError:
            self.downloaded_minecraft_versions = []
        self.download_version_to = ""
        self.support_fabric = ""
        self.support_forge = ""
        self.game_processes = []
        self.current_progress = 0
        self.downloading = False
        self.close_button_visible = False
        self.progress_button_visible = False
        self.progress_page_open = False
        self.download_page_open = False
        self.current_page = "main"
        self.nbt_window = None
        self._nbt_tags = {}
        self._nbt_placeholders = set()
        self._nbt_last_dir = ""

    def __init__(self):
        self._ui_queue = queue.Queue()
        enable_bmclapi_fallback()
        self.checkfiles()
        self.init_var()
        self.main_win = maliang.Tk(title="Pixel Minecraft Launcher")
        try:
            self.default_bg = self.main_win.cget("bg")
        except tk.TclError:
            self.default_bg = "SystemButtonFace"
        self.main_win.geometry(size=(1150, 650))
        self.main_win.center()
        try:
            self.alpha = min(1.0, max(0.0, float(self.alpha)))
        except (TypeError, ValueError):
            self.alpha = 0.85
        self.main_win.alpha(self.alpha)
        self.main_win.resizable(False, False)
        theme.customize_window(self.main_win, header_color="skyblue")
        try:
            self.main_win.iconbitmap("PML/ddd.ico")
        except tk.TclError as exp:
            print(f"[WARN] 无法设置窗口图标: {exp}")

        # 启动游戏标语&按钮
        self.Start_Game_Label = tk.Label(
            self.main_win,
            text=f"是时候启动游戏了！\n正在使用的账户:{self.Username}\n准备启动游戏:{self.selected_version}",
            bg=self.bg,
        )
        self.Start_Game_Label.place(x=900, y=500)
        self.Start_Game_Button = tk.Button(
            self.main_win,
            text="启动游戏",
            width=30,
            height=2,
            relief="ridge",
            command=self.start_th,
        )
        self.Start_Game_Button.place(x=880, y=560)
        self.Modify_Button = tk.Button(
            self.main_win,
            text="版本选择&版本设置",
            width=30,
            height=1,
            relief="ridge",
            command=self.change_version_and_modify_version,
        )
        self.Modify_Button.place(x=880, y=610)
        # 关闭所有正在运行的 Minecraft 游戏(类似 PCL)
        # 默认隐藏, 检测到有游戏运行时才显示
        self.CloseGames_Button = tk.Button(
            self.main_win,
            text="关闭所有游戏",
            relief="groove",
            command=self.close_all_games,
        )
        self.close_button_visible = False
        # 下载进度按钮: 和关闭游戏一样在窗口外面, 有下载时才从左侧滑入
        self.ProgressButton = tk.Button(
            self.main_win,
            text="查看下载进度",
            relief="groove",
            command=self.show_download_progress,
        )
        self.ProgressButton.place(x=-200, y=530)
        self.progress_button_visible = False

        self.create_all()
        self.create_main()
        # 欢迎标题
        self.main_win.config(bg=self.bg)
        self.Label = tk.Label(
            self.main_win,
            text=f"欢迎回来，{os.getlogin()}",
            font=("等线", 15),
            bg=self.bg,
        )
        self.Label.place(x=15, y=610)

        self.start_game_watcher()
        self.main_win.after(100, self._process_ui_queue)
        self.main_win.mainloop()

    def ui_call(self, func, *args, **kwargs):
        """把界面操作交给主线程执行(子线程中不能直接操作控件)"""
        self._ui_queue.put((func, args, kwargs))

    def _process_ui_queue(self):
        while True:
            try:
                func, args, kwargs = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args, **kwargs)
            except Exception as exp:
                print(f"[ERROR] 界面更新失败: {exp}")
        try:
            self.main_win.after(100, self._process_ui_queue)
        except tk.TclError:
            pass

    def delete_main(self):
        animation.MoveTkWidget(
            self.Download_Button,
            (0, 950),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Settings_Button,
            (0, -1050),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.ServerLauncher_Button,
            (0, 950),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Others_Button,
            (0, -1050),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        self.Modify_Button.config(state=tk.DISABLED)

    def any_java_processes(self):
        """快速判断系统里是否有 java/javaw 进程"""
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for image in ("javaw.exe", "java.exe"):
            try:
                output = subprocess.check_output(
                    ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    creationflags=creation_flags,
                ).decode("utf-8", errors="ignore")
            except Exception:
                # 无法判断时保守地认为可能有, 交给 wmic 继续确认
                return True
            if image.lower() in output.lower():
                return True
        return False

    def get_running_game_processes(self):
        """找出正在运行的 Minecraft 客户端进程 PID"""
        pids = set()
        for process in list(getattr(self, "game_processes", [])):
            try:
                if process.poll() is None:
                    pids.add(process.pid)
            except Exception:
                continue
        # 没有 java 进程时直接返回, 避免每次轮询都去调用 wmic
        if not pids and not self.any_java_processes():
            return []
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        output = ""
        try:
            output = subprocess.check_output(
                [
                    "wmic",
                    "process",
                    "where",
                    "name='java.exe' or name='javaw.exe'",
                    "get",
                    "ProcessId,CommandLine",
                    "/FORMAT:CSV",
                ],
                stderr=subprocess.DEVNULL,
                timeout=10,
                creationflags=creation_flags,
            ).decode("utf-8", errors="ignore")
        except Exception as exp:
            print(f"[WARN] wmic 列举进程失败: {exp}")
            try:
                output = subprocess.check_output(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-CimInstance Win32_Process -Filter "
                        "\"Name='java.exe' or Name='javaw.exe'\" | "
                        "Where-Object { $_.CommandLine -match 'minecraft' } | "
                        "ForEach-Object { $_.ProcessId }",
                    ],
                    text=True,
                    timeout=20,
                    creationflags=creation_flags,
                )
            except Exception as powershell_exp:
                print(f"[WARN] 无法枚举游戏进程: {powershell_exp}")
                return sorted(pids)

        if output and "ProcessId" in output and "," in output:
            import csv
            import io as _io

            for row in csv.reader(_io.StringIO(output)):
                if len(row) < 3 or not row[-1].strip().isdigit():
                    continue
                command_line = ",".join(row[1:-1])
                if (
                    "net.minecraft.client.main.Main" in command_line
                    or "--accessToken" in command_line
                ):
                    pids.add(int(row[-1].strip()))
        else:
            for line in output.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
        return sorted(pids)

    def set_close_button_visible(self, visible):
        """根据是否有游戏运行来显示/隐藏"关闭所有游戏"按钮"""
        if visible and not getattr(self, "close_button_visible", False):
            self.CloseGames_Button.place(x=15, y=572)
            self.close_button_visible = True
        elif not visible and getattr(self, "close_button_visible", False):
            self.CloseGames_Button.place_forget()
            self.close_button_visible = False

    def start_game_watcher(self):
        """后台定时检测是否有游戏在运行, 用来控制按钮显示"""

        def watch():
            last_state = False
            while True:
                try:
                    state = bool(self.get_running_game_processes())
                except Exception as exp:
                    print(f"[WARN] 游戏进程检测失败: {exp}")
                    state = last_state
                if state != last_state:
                    last_state = state
                    self.ui_call(self.set_close_button_visible, state)
                time.sleep(5)

        threading.Thread(target=watch, daemon=True).start()

    def close_all_games(self):
        """关闭所有 Minecraft 游戏进程(类似 PCL)"""
        try:
            pids = self.get_running_game_processes()
        except Exception as exp:
            print(f"[ERROR] 查找游戏进程失败: {exp}")
            tkinter.messagebox.showerror("错误", f"查找游戏进程失败:{exp}")
            return
        if not pids:
            tkinter.messagebox.showinfo("提示", "没有找到正在运行的 Minecraft 游戏。")
            return
        if not tkinter.messagebox.askyesno(
            "关闭所有游戏",
            f"找到 {len(pids)} 个正在运行的 Minecraft 游戏，确定全部关闭吗？\n"
            "未保存的游戏进度可能会丢失。",
        ):
            return
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        closed = 0
        for pid in pids:
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    creationflags=creation_flags,
                )
                if result.returncode == 0:
                    closed += 1
            except Exception as exp:
                print(f"[WARN] 无法结束进程 {pid}: {exp}")
        try:
            self.set_close_button_visible(bool(self.get_running_game_processes()))
        except Exception:
            self.set_close_button_visible(False)
        tkinter.messagebox.showinfo(
            "完成", f"已关闭 {closed} 个游戏进程（共找到 {len(pids)} 个）。"
        )

    def start_th(self):
        isolation_mode = self.get_isolation_mode()
        java_path = self.get_launch_java()
        threading.Thread(
            target=self.start_game,
            args=(isolation_mode, java_path),
            daemon=True,
        ).start()

    def create_main(self):
        self.set_current_page("main")
        self.Modify_Button.config(state=tk.NORMAL)
        # 开始写控件类
        animation.MoveTkWidget(
            self.Download_Button,
            (0, -950),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Settings_Button,
            (0, 1050),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.ServerLauncher_Button,
            (0, -950),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Others_Button,
            (0, 1050),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()

    def set_alpha(self, value):
        self.main_win.alpha(self.scale.get() / 100)
        self.alpha = self.scale.get() / 100
        self.apply_window_alpha()
        self.save_all()

    def apply_window_alpha(self):
        """把透明度同步到 NBT 查看器等子窗口"""
        window = getattr(self, "nbt_window", None)
        if window is None:
            return
        try:
            if window.winfo_exists():
                window.attributes("-alpha", self.alpha)
        except (tk.TclError, AttributeError):
            pass

    def fetch_version_list_from_mirror(self):
        """从 BMCLAPI 镜像获取 Minecraft 版本列表"""
        with urllib.request.urlopen(BMCLAPI_VERSION_MANIFEST, timeout=20) as response:
            data = json.load(response)
        versions = []
        for item in data.get("versions", []):
            try:
                versions.append(
                    {"id": item["id"], "type": item.get("type", "release")}
                )
            except (KeyError, TypeError):
                continue
        return versions

    def get_local_version_list(self):
        """获取本地已安装的版本(网络不可用时的兜底)"""
        try:
            names = os.listdir(os.path.join(self.minecraft_dir, "versions"))
        except OSError:
            return []
        return [
            {"id": name, "type": "installed"}
            for name in sorted(names, reverse=True)
            if name.strip()
        ]

    def get_version_list(self):
        """获取远程版本列表: 官方源 -> BMCLAPI 镜像 -> 本地已安装版本"""
        try:
            return mll.utils.get_version_list()
        except Exception as exp:
            print(f"[WARN] 官方版本列表获取失败: {type(exp).__name__}: {exp}")
        try:
            versions = self.fetch_version_list_from_mirror()
            if versions:
                print("[INFO] 已通过 BMCLAPI 镜像获取版本列表")
                return versions
        except Exception as exp:
            print(f"[WARN] 镜像版本列表获取失败: {type(exp).__name__}: {exp}")
        local_versions = self.get_local_version_list()
        if local_versions:
            print("[WARN] 网络不可用, 仅显示本地已安装版本")
            return local_versions
        self.ui_call(self.show_version_list_message, "网络不畅，请稍后重试。")
        return []

    def show_version_list_message(self, message):
        self.version_listbox.delete(0, tk.END)
        self.version_listbox.insert(0, message)

    def delete_download(self):
        self.download_page_open = False
        animation.MoveTkWidget(
            self.Menu_Butt_download,
            (-50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.version_listbox,
            (0, -500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.VersionDescription,
            (1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        self.create_main()

    def delete_modify(self):
        animation.MoveTkWidget(
            self.Menu_Butt_modify,
            (-50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Change_Dir, (-50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.VersionListListBox,
            (0, -500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.VerDescription,
            (1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        self.create_main()

    def delete_mod(self):
        mod_name = self.get_selected_mod()
        if mod_name is None:
            tkinter.messagebox.showerror("错误", "你没有选择任何mod!")
            return
        mods_dir = f"{self.minecraft_dir}/versions/{self.selected_version}/mods"
        try:
            os.remove(os.path.join(mods_dir, mod_name))
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法删除{mod_name}:{exp}")
            return
        tkinter.messagebox.showinfo("成功", f"已删除1个mod:{mod_name}")
        self.reload_mods()

    def reload_mods(self):
        self.d_mod.config(state=tk.NORMAL)
        self.e_mod.config(state=tk.NORMAL)
        self.Add.config(command=self.add_mod)
        self.Delete.config(command=self.delete_mod)
        self.ModListListBox.delete(0, tk.END)
        self.modlistlist = []
        if self.support_mod and self.selected_version != "":
            mods_dir = f"{self.minecraft_dir}/versions/{self.selected_version}/mods"
            try:
                mod_names = os.listdir(mods_dir)
            except OSError:
                mod_names = []
            if not mod_names:
                self.ModListListBox.insert(tk.END, "这个版本还没有安装任何mod")
                return
            for i in mod_names:
                self.modlistlist.append(i)
                if i.endswith(".disabled"):
                    self.ModListListBox.insert(tk.END, i[:-9] + "(已被禁用)")
                else:
                    self.ModListListBox.insert(tk.END, i)
        else:
            self.ModListListBox.insert(tk.END, "您的版本并不支持mod或者没有选中版本")

    def create_all(self):
        self.Download_Button = tk.Button(
            self.main_win,
            text="下载版本",
            width=20,
            height=25,
            command=self.from_menu_to_download_page,
            anchor="se",
            font=("等线"),
            relief="groove",
        )
        self.Download_Button.place(x=170, y=1000)
        self.Settings_Button = tk.Button(
            self.main_win,
            text="用户设置",
            width=20,
            height=25,
            command=self.from_menu_to_user_settigs_page,
            anchor="se",
            font=("等线"),
            relief="groove",
        )
        self.Settings_Button.place(x=370, y=-1000)
        self.ServerLauncher_Button = tk.Button(
            self.main_win,
            text="服务器启动",
            width=20,
            height=25,
            anchor="se",
            font=("等线"),
            relief="groove",
            command=self.from_menu_to_server_page,
        )
        self.ServerLauncher_Button.place(x=570, y=1000)
        self.Others_Button = tk.Button(
            self.main_win,
            text="杂项设置",
            width=20,
            height=25,
            anchor="se",
            font=("等线"),
            relief="groove",
            command=self.from_menu_to_PML_settings_page,
        )
        self.Others_Button.place(x=770, y=-1000)

        self.Menu_Butt_Settings = tk.Button(
            self.main_win, text="🏠", command=self.delete_PML_settings
        )
        self.Menu_Butt_Settings.place(x=-50, y=5)  # x=0, y=0
        self.PML_Setting_Frame = tk.Frame(self.main_win, width=1000, height=200)
        self.PML_Setting_Frame.place(x=30, y=-295)
        self.scale = tk.Scale(
            self.PML_Setting_Frame,
            from_=0,
            to=100,
            length=200,
            command=self.set_alpha,
            orient="horizontal",
            label="设置窗口透明度",
            bg=self.bg,
        )
        self.scale.set(self.alpha * 100)
        self.scale.place(x=0, y=0)  # x=30, y=0
        self.Reset = tk.Button(
            self.PML_Setting_Frame,
            text="重置透明度",
            command=lambda: self.scale.set(85),
        )
        self.Reset.place(x=220, y=35)
        self.ColorSetLabel = tk.Label(
            self.PML_Setting_Frame, text="设置背景颜色", bg=self.bg
        )
        self.ColorSetLabel.place(x=0, y=60)  # x=30, y=60
        self.ColorChooser = tk.Button(
            self.PML_Setting_Frame, text="点我设置背景颜色", command=self.set_color
        )
        self.ColorChooser.place(x=0, y=80)  # x=30, y=80
        self.ResetColor = tk.Button(
            self.PML_Setting_Frame, text="重置背景颜色", command=self.reset_color
        )
        self.ResetColor.place(x=220, y=80)
        self.Version_Splition_Label = tk.Label(
            self.PML_Setting_Frame, text="版本隔离设置:", font=("等线", 13)
        )
        self.Version_Splition_Label.place(x=0, y=120)
        self.Version_Splition_Combobox = ttk.Combobox(
            self.PML_Setting_Frame,
            values=ISOLATION_VALUES,
            state="readonly",
        )
        if not 0 <= self.Versplitvar < len(ISOLATION_VALUES):
            self.Versplitvar = 0
        self.Version_Splition_Combobox.current(self.Versplitvar)
        self.Version_Splition_Combobox.bind(
            "<<ComboboxSelected>>", self.Change_Ver_split
        )
        self.Version_Splition_Combobox.place(x=120, y=120)
        self.Java_Label = tk.Label(
            self.PML_Setting_Frame, text="Java设置:", font=("等线", 13)
        )
        self.Java_Label.place(x=0, y=150)
        java_values = ["自动选择"] + self.get_java()
        if not 0 <= self.CurJavaVar < len(java_values):
            self.CurJavaVar = 0
        self.Java_Combobox = ttk.Combobox(
            self.PML_Setting_Frame,
            values=java_values,
            state="readonly",
            width=60,
        )
        self.Java_Combobox.current(self.CurJavaVar)
        self.Java_Combobox.bind("<<ComboboxSelected>>", self.Change_Java)
        self.Java_Combobox.place(x=120, y=150)
        self.Java_add_butt = ttk.Button(
            self.PML_Setting_Frame, text="手动添加Java", command=self.add_java
        )
        self.Java_add_butt.place(x=575, y=146)
        self.NbtViewerLabel = tk.Label(
            self.PML_Setting_Frame, text="NBT 文件查看:", font=("等线", 13)
        )
        self.NbtViewerLabel.place(x=720, y=0)
        self.ViewNbtButton = tk.Button(
            self.PML_Setting_Frame,
            text="打开 NBT 查看器",
            command=self.show_nbt_viewer,
        )
        self.ViewNbtButton.place(x=720, y=28)

        self.Menu_Butt_User = tk.Button(
            self.main_win, text="🏠", command=self.delete_settings
        )
        self.Menu_Butt_User.place(x=-50, y=5)
        self.Add_User = tk.Button(self.main_win, text="➕", command=self.AddNewUser)
        self.Add_User.place(x=-50, y=35)
        self.Delete_User = tk.Button(self.main_win, text="➖", command=self.DeleteUser)
        self.Delete_User.place(x=-50, y=65)
        self.username_listbox = tk.Listbox(self.main_win, width=40, height=25)
        self.username_listbox.place(x=30, y=-495)
        self.username_listbox.insert(tk.END, "正在加载...")
        self.UserDescription = ttk.Frame(
            self.main_win, width=750, height=454, relief="ridge"
        )
        self.UserDescription.place(x=1350, y=5)
        self.UserDescriptionLabel = tk.Label(
            self.UserDescription, text="用户信息", font=("等线", 25)
        )
        self.UserDescriptionLabel.place(x=20, y=0)
        self.username_listbox.bind("<<ListboxSelect>>", self.get_username_to_set)
        self.username_listbox.bind("<Double-Button-1>", self.apply_username)

        self.Menu_Butt_Server = tk.Button(
            self.main_win, text="🏠", command=self.delete_server_settings
        )
        self.Menu_Butt_Server.place(x=-50, y=5)
        self.Add_Server = tk.Button(self.main_win, text="➕", command=self.AddNewServer)
        self.Add_Server.place(x=-50, y=35)
        self.Delete_Server = tk.Button(
            self.main_win, text="➖", command=self.DeleteServer
        )
        self.Delete_Server.place(x=-50, y=65)
        self.server_listbox = tk.Listbox(self.main_win, width=40, height=25)
        self.server_listbox.place(x=30, y=-495)
        self.server_listbox.insert(tk.END, "正在加载...")
        self.server_listbox.bind("<<ListboxSelect>>", self.change_server)
        self.server_listbox.delete(0)
        self.ServerDescription = ttk.Frame(
            self.main_win, width=750, height=454, relief="ridge"
        )
        self.ServerDescription.place(x=1350, y=5)
        self.ServerDescriptionLabel = tk.Label(
            self.ServerDescription, text="服务器面板", font=("等线", 25)
        )
        self.ServerPath_Label = tk.Label(self.ServerDescription, text="服务器核心位置:")
        self.ServerPath_Label.place(x=20, y=60)
        self.ServerDescriptionLabel.place(x=20, y=0)
        self.StartServerButton = tk.Button(
            self.ServerDescription, text="启动这台服务器", command=self.run_server
        )
        self.StartServerButton.place(x=20, y=80)
        # OpenP2P 联机功能暂时停用, 需要恢复时取消下面 8 行注释
        # self.Enable_Start_OpenP2P_var = tk.IntVar()
        # self.Enable_Start_OpenP2P_var.set(1)
        # self.Enable_Start_OpenP2P = tk.Checkbutton(
        #     self.ServerDescription,
        #     text="开启服务器时\n启动联机服务端",
        #     variable=self.Enable_Start_OpenP2P_var,
        # )
        # self.Enable_Start_OpenP2P.place(x=20, y=115)
        self.ServerLog = tk.Text(self.ServerDescription, width=70, height=19)
        self.ServerLog.place(x=130, y=80)
        self.ServerLog.bind("<Control-S>", self.save_prop)
        self.ServerLog.bind("<Control-s>", self.save_prop)
        self.Apply_Settings = tk.Button(
            self.ServerDescription,
            width=79,
            height=2,
            text="应用修改",
            command=self.save_prop,
        )
        self.Apply_Settings.place(x=130, y=400)

        self.Menu_Butt_download = tk.Button(
            self.main_win, text="🏠", command=self.delete_download
        )
        self.Menu_Butt_download.place(x=-50, y=5)
        self.version_listbox = tk.Listbox(self.main_win, width=40, height=25)
        self.version_listbox.place(x=30, y=-495)
        self.version_listbox.insert(tk.END, "正在加载...")
        self.VersionDescription = ttk.Frame(
            self.main_win, width=750, height=454, relief="ridge"
        )
        self.VersionDescription.place(x=1350, y=5)
        self.VersionDescriptionLabel = tk.Label(
            self.VersionDescription, text="版本概述", font=("等线", 25)
        )
        self.VersionDescriptionLabel.place(x=20, y=0)
        self.SupportForgeLabel = tk.Label(self.VersionDescription, text="Forge支持:")
        self.SupportForgeLabel.place(x=20, y=60)
        self.SupportFabricLabel = tk.Label(self.VersionDescription, text="Fabric支持:")
        self.SupportFabricLabel.place(x=20, y=80)
        self.ModLoaderLabel = tk.Label(self.VersionDescription, text="选择模组加载器:")
        self.ModLoaderLabel.place(x=20, y=100)
        self.ModLoader = tk.StringVar()
        self.ModLoader.set("原版")
        self.ModLoaderOption = ttk.Combobox(
            self.VersionDescription,
            textvariable=self.ModLoader,
            values=["原版"],
            state="readonly",
        )
        self.ModLoaderOption.place(x=150, y=100)
        self.ModLoaderOption.bind(
            "<<ComboboxSelected>>", self.get_mod_loader_version_theard
        )
        self.ModLoaderVersionLabel = tk.Label(
            self.VersionDescription, text="选择Mod加载器版本:"
        )
        self.ModLoaderVersionLabel.place(x=20, y=120)
        self.ModLoaderVersion = tk.StringVar()
        self.ModLoaderVersionOption = ttk.Combobox(
            self.VersionDescription,
            textvariable=self.ModLoaderVersion,
            values=[],
            state="normal",  # 允许手动输入版本号(网络获取失败时也能用)
            width=24,
        )
        self.ModLoaderVersionOption.place(x=150, y=120)
        self.DownloadButton = tk.Button(
            self.VersionDescription,
            text="下载Minecraft",
            width=30,
            height=1,
            command=self.download_minecraft_version_theard,
        )
        self.DownloadButton.place(x=20, y=150)

        self.Menu_Butt_modify = tk.Button(
            self.main_win, text="🏠", command=self.delete_modify
        )
        self.Menu_Butt_modify.place(x=-50, y=0)
        self.Change_Dir = tk.Button(
            self.main_win, text="🔄️", command=self.change_minecraft_dir
        )
        self.Change_Dir.place(x=-50, y=30)
        self.VersionListListBox = tk.Listbox(self.main_win, width=40, height=25)
        self.VersionListListBox.place(x=30, y=-500)
        self.VerDescription = ttk.Frame(
            self.main_win, width=750, height=454, relief="ridge"
        )
        self.VerDescription.place(x=1350, y=0)
        self.VerDescriptionLabel = tk.Label(
            self.VerDescription, text="版本信息", font=("等线", 25)
        )
        self.VerDescriptionLabel.place(x=20, y=0)
        self.DeleteVersionButton = tk.Button(
            self.VerDescription,
            text="删除当前版本",
            command=self.delete_version,
        )
        self.DeleteVersionButton.place(x=430, y=10)
        self.supply_mod_loading = tk.Label(self.VerDescription, text="支持mod加载:")
        self.supply_mod_loading.place(x=20, y=60)
        self.VersionListListBox.bind(
            "<<ListboxSelect>>", self.UpdateModListAndUpdateModLoaderSupport
        )
        self.modlist = tk.Label(self.VerDescription, text="Mod列表")
        self.modlist.place(x=10, y=80)
        self.Add = tk.Button(self.VerDescription, text="➕", command=self.add_mod)
        self.Add.place(x=10, y=100)
        self.Delete = tk.Button(self.VerDescription, text="➖", command=self.delete_mod)
        self.Delete.place(x=10, y=135)
        self.d_mod = tk.Button(self.VerDescription, text="🚫", command=self.disable_mod)
        self.d_mod.place(x=10, y=170)
        self.e_mod = tk.Button(self.VerDescription, text="☑️", command=self.enable_mod)
        self.e_mod.place(x=10, y=205)
        self.mod_list_butt = tk.Button(
            self.VerDescription, text="🧩", command=self.reload_mods
        )
        self.mod_list_butt.place(x=10, y=240)
        self.save_list_butt = tk.Button(
            self.VerDescription, text="💾", command=self.load_saves
        )
        self.save_list_butt.place(x=10, y=275)
        self.ModListListBox = tk.Listbox(self.VerDescription, width=50, height=19)
        self.ModListListBox.place(x=36, y=100)

        # ---- 下载进度页(和下载页一样是独立页面) ----
        self.Menu_Butt_progress = tk.Button(
            self.main_win, text="🏠", command=self.from_progress_to_download_page
        )
        self.Menu_Butt_progress.place(x=-50, y=5)
        self.ProgressDescription = ttk.Frame(
            self.main_win, width=750, height=454, relief="ridge"
        )
        self.ProgressDescription.place(x=1350, y=5)
        self.ProgressDescriptionLabel = tk.Label(
            self.ProgressDescription, text="下载进度", font=("等线", 25)
        )
        self.ProgressDescriptionLabel.place(x=20, y=0)
        self.progress_version_var = tk.StringVar(value="")
        self.progress_status_var = tk.StringVar(value="准备中...")
        self.progress_percent_var = tk.StringVar(value="")
        self.progress_value_var = tk.DoubleVar(value=0)
        self.ProgressVersionLabel = tk.Label(
            self.ProgressDescription, textvariable=self.progress_version_var
        )
        self.ProgressVersionLabel.place(x=20, y=60)
        self.ProgressStatusLabel = tk.Label(
            self.ProgressDescription,
            textvariable=self.progress_status_var,
            anchor="w",
            justify="left",
            wraplength=680,
        )
        self.ProgressStatusLabel.place(x=20, y=100)
        self.progress_bar = ttk.Progressbar(
            self.ProgressDescription,
            length=680,
            maximum=100,
            variable=self.progress_value_var,
        )
        self.progress_bar.place(x=20, y=145)
        self.ProgressPercentLabel = tk.Label(
            self.ProgressDescription, textvariable=self.progress_percent_var
        )
        self.ProgressPercentLabel.place(x=20, y=175)
        self.ProgressHintLabel = tk.Label(
            self.ProgressDescription,
            text="下载期间可以点左上角 🏠 返回下载页面，下载会在后台继续。",
        )
        self.ProgressHintLabel.place(x=20, y=215)

    def add_java(self):
        javawplace = tkinter.filedialog.askopenfilename(
            title="打开Java解释器位置", filetypes=[("Java解释器", "javaw.exe")]
        )
        if javawplace == "":
            return
        javawplace = os.path.abspath(javawplace).replace("\\", "/")
        if os.path.basename(javawplace).lower() != "javaw.exe":
            tkinter.messagebox.showerror("错误", "请选择 javaw.exe 文件!")
            return
        if javawplace in self.exjavaplace:
            tkinter.messagebox.showinfo("提示", "这个 Java 已经添加过了!")
            return
        self.exjavaplace.append(javawplace)
        self._java_entries = None
        try:
            self.Java_Combobox.config(values=["自动选择"] + self.get_java())
        except AttributeError:
            pass
        self.save_all()

    def Change_Ver_split(self, *args):
        try:
            self.Versplitvar = ISOLATION_VALUES.index(
                self.Version_Splition_Combobox.get()
            )
        except ValueError:
            self.Versplitvar = ISOLATION_NONE
        self.save_all()

    def get_isolation_mode(self):
        """读取当前的版本隔离模式"""
        try:
            return ISOLATION_VALUES.index(self.Version_Splition_Combobox.get())
        except ValueError:
            return ISOLATION_NONE

    def create_download(self):
        animation.MoveTkWidget(
            self.Menu_Butt_download,
            (50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.version_listbox,
            (0, 500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.VersionDescription,
            (-1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()

    def read_java_version(self, java_path):
        """读取 Java 的版本号, 读取失败时返回空字符串"""
        try:
            java_exe = java_path
            if os.path.basename(java_exe).lower() == "javaw.exe":
                java_exe = os.path.join(os.path.dirname(java_exe), "java.exe")
            result = subprocess.run(
                [java_exe, "-version"], text=True, capture_output=True, timeout=15
            )
            text = (result.stderr or result.stdout).strip().splitlines()[0]
            match = re.search(r'version "([^"]+)"', text)
            if match:
                return match.group(1)
            return text.split(" ")[-1].strip('"')
        except Exception as exp:
            print(f"[WARN] 无法读取 Java 版本 {java_path}: {exp}")
            return ""

    def discover_java(self):
        """扫描系统中的 Java, 返回 [(显示名称, javaw 路径, 版本号)]"""
        if self._java_entries is not None:
            return self._java_entries

        entries = []
        paths = set()

        def add(java_path, display_name, version):
            java_path = str(java_path).replace("\\", "/")
            key = os.path.normcase(os.path.abspath(java_path))
            if key in paths or not os.path.isfile(java_path):
                return
            paths.add(key)
            entries.append((display_name, java_path, version))

        for base in JAVA_SEARCH_DIRS:
            if not os.path.isdir(base):
                continue
            for name in sorted(os.listdir(base)):
                javaw_path = os.path.join(base, name, "bin", "javaw.exe")
                if os.path.isfile(javaw_path):
                    shown_path = javaw_path.replace("\\", "/")
                    add(
                        shown_path,
                        f"{''.join(name.split('-')).upper()} ({shown_path}) [全局]",
                        name.split("-")[-1],
                    )

        for java_path in self.exjavaplace:
            if not java_path or not java_path.strip():
                continue
            java_version = self.read_java_version(java_path)
            display_version = (
                java_version.split("_")[0] if java_version else "未知版本"
            )
            add(
                java_path,
                f"{display_version} ({java_path.replace(chr(92), '/')}) [自定义]",
                java_version,
            )

        self._java_entries = entries
        return entries

    def get_java_place(self):
        return [path for _display, path, _version in self.discover_java()]

    def get_java(self):
        return [display for display, _path, _version in self.discover_java()]

    def get_java_version(self):
        return [version for _display, _path, version in self.discover_java()]

    def get_java_version_by_place(self, java_path):
        """根据 Java 路径查找版本号"""
        normalized = os.path.normcase(
            os.path.abspath(str(java_path).replace("\\", "/"))
        )
        for _display, path, version in self.discover_java():
            if os.path.normcase(os.path.abspath(path)) == normalized:
                return version
        return self.read_java_version(java_path)

    def Change_Java(self, *args):
        try:
            self.CurJavaVar = (["自动选择"] + self.get_java()).index(
                self.Java_Combobox.get()
            )
        except ValueError:
            self.CurJavaVar = 0
        self.save_all()

    def copy_to_version_folder(self, source, folder):
        """把文件复制到当前版本对应的文件夹中"""
        target_dir = (
            f"{self.minecraft_dir}/versions/{self.selected_version}/{folder}"
        )
        try:
            os.makedirs(target_dir, exist_ok=True)
            target = os.path.join(target_dir, os.path.basename(source))
            shutil.copy(source, target)
            return target
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"复制文件失败:{exp}")
            return None

    def add_resource_packs(self):
        modplace = tk.filedialog.askopenfilename(title="打开资源包位置")
        if modplace != "":
            if self.copy_to_version_folder(modplace, "resourcepacks") is None:
                return
            tkinter.messagebox.showinfo(
                "成功",
                f"已成功安装{os.path.basename(modplace)}到{self.selected_version}",
            )
            self.load_resource_packs()

    def delete_resource_packs(self):
        selection = self.ModListListBox.curselection()
        if selection == ():
            tkinter.messagebox.showerror("错误", "你没有选择任何资源包!")
            return
        pack_name = self.ModListListBox.get(selection[0])
        try:
            os.remove(
                f"{self.minecraft_dir}/versions/{self.selected_version}/resourcepacks/{pack_name}"
            )
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法删除{pack_name}:{exp}")
            return
        tkinter.messagebox.showinfo("成功", f"已删除1个资源包:{pack_name}")
        self.load_resource_packs()

    def add_shader_packs(self):
        modplace = tk.filedialog.askopenfilename(title="打开资源包位置")
        if modplace != "":
            if self.copy_to_version_folder(modplace, "shaderpacks") is None:
                return
            tkinter.messagebox.showinfo(
                "成功",
                f"已成功安装{os.path.basename(modplace)}到{self.selected_version}",
            )
            self.load_shader_packs()

    def delete_shader_packs(self):
        selection = self.ModListListBox.curselection()
        if selection == ():
            tkinter.messagebox.showerror("错误", "你没有选择任何光影包!")
            return
        pack_name = self.ModListListBox.get(selection[0])
        try:
            os.remove(
                f"{self.minecraft_dir}/versions/{self.selected_version}/shaderpacks/{pack_name}"
            )
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法删除{pack_name}:{exp}")
            return
        tkinter.messagebox.showinfo("成功", f"已删除1个光影包:{pack_name}")
        self.load_shader_packs()

    def add_data_packs(self):
        modplace = tk.filedialog.askopenfilename(title="打开数据包位置")
        if modplace != "" and self.save_selected not in [
            "..返回上一级",
            "重命名此版本",
            "修改版本光影包...",
            "修改版本资源包...",
        ]:
            target_dir = (
                f"{self.minecraft_dir}/versions/{self.selected_version}"
                f"/saves/{self.save_selected}/datapacks"
            )
            try:
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy(
                    modplace, os.path.join(target_dir, os.path.basename(modplace))
                )
            except OSError as exp:
                tkinter.messagebox.showerror("错误", f"复制文件失败:{exp}")
                return
            tkinter.messagebox.showinfo(
                "成功",
                f"已成功安装{os.path.basename(modplace)}到{self.selected_version}",
            )
            self.modify_saves()

    def delete_data_packs(self):
        selection = self.ModListListBox.curselection()
        if selection == () or self.save_selected in [
            "..返回上一级",
            "重命名此版本",
            "修改版本光影包...",
            "修改版本资源包...",
        ]:
            return
        pack_name = self.ModListListBox.get(selection[0])
        try:
            os.remove(
                f"{self.minecraft_dir}/versions/{self.selected_version}/saves/{self.save_selected}/datapacks/{pack_name}"
            )
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法删除{pack_name}:{exp}")
            return
        tkinter.messagebox.showinfo("成功", f"已删除1个数据包:{pack_name}")
        self.modify_saves()

    def get_save_to_modify(self, *args):
        if self.ModListListBox.curselection() != ():
            self.save_selected = self.ModListListBox.get(
                self.ModListListBox.curselection()[0]
            )

    def get_nex_one(self, *args):
        if self.save_selected != "":
            if self.save_selected in ["修改版本光影包...", "修改版本资源包..."]:
                if self.save_selected == "修改版本光影包...":
                    self.load_shader_packs()
                elif self.save_selected == "修改版本资源包...":
                    self.load_resource_packs()
            else:
                self.modify_saves()

    def modify_saves(self):
        if self.save_selected not in [
            "..返回上一级",
            "重命名此版本",
            "修改版本光影包...",
            "修改版本资源包...",
        ]:
            try:
                datapackslist = os.listdir(
                    f"{self.minecraft_dir}/versions/{self.selected_version}/saves/{self.save_selected}/datapacks"
                )
                self.ModListListBox.delete(0, tk.END)
                for i in datapackslist:
                    self.ModListListBox.insert(0, i)
                self.ModListListBox.insert(0, "重命名此版本")
                self.ModListListBox.insert(0, "..返回上一级")
                self.ModListListBox.unbind("<Double-Button-1>")
                self.ModListListBox.bind("<Double-Button-1>", self.reload_save)
                self.Add.config(command=self.add_data_packs)
                self.Delete.config(command=self.delete_data_packs)
            except FileNotFoundError:
                self.ModListListBox.delete(0, tk.END)
                self.ModListListBox.insert(0, "版本选择错误或者没有数据包文件夹")
                self.ModListListBox.insert(0, "重命名此版本")
                self.ModListListBox.insert(0, "..返回上一级")
                self.ModListListBox.unbind("<Double-Button-1>")
                self.ModListListBox.bind("<Double-Button-1>", self.reload_save)

    def load_resource_packs(self):
        try:
            resourcepackslist = os.listdir(
                f"{self.minecraft_dir}/versions/{self.selected_version}/resourcepacks"
            )
            self.ModListListBox.delete(0, tk.END)
            for i in resourcepackslist:
                self.ModListListBox.insert(0, i)
            self.ModListListBox.insert(0, "..返回上一级")
            self.ModListListBox.unbind("<Double-Button-1>")
            self.ModListListBox.bind("<Double-Button-1>", self.reload_save)
            self.Delete.config(command=self.delete_resource_packs)
            self.Add.config(command=self.add_resource_packs)
        except FileNotFoundError:
            self.ModListListBox.delete(0, tk.END)
            self.ModListListBox.insert(0, "版本选择错误或者没有资源包文件夹")
            self.ModListListBox.insert(0, "..返回上一级")
            self.ModListListBox.unbind("<Double-Button-1>")
            self.ModListListBox.bind("<Double-Button-1>", self.reload_save)

    def load_shader_packs(self):
        try:
            shaderpacklist = os.listdir(
                f"{self.minecraft_dir}/versions/{self.selected_version}/shaderpacks"
            )
            self.ModListListBox.delete(0, tk.END)
            for i in shaderpacklist:
                self.ModListListBox.insert(0, i)
            self.ModListListBox.insert(0, "..返回上一级")
            self.ModListListBox.unbind("<Double-Button-1>")
            self.ModListListBox.bind("<Double-Button-1>", self.reload_save)
            self.Delete.config(command=self.delete_shader_packs)
            self.Add.config(command=self.add_shader_packs)
        except FileNotFoundError:
            self.ModListListBox.delete(0, tk.END)
            self.ModListListBox.insert(0, "版本选择错误或者没有光影文件夹")
            self.ModListListBox.insert(0, "..返回上一级")
            self.ModListListBox.unbind("<Double-Button-1>")
            self.ModListListBox.bind("<Double-Button-1>", self.reload_save)

    def rename_save(self):
        if self.save_selected not in [
            "..返回上一级",
            "修改版本光影包...",
            "修改版本资源包...",
        ]:
            name = pymsgbox.prompt("输入重命名后的存档名称:")
            if name is not None:
                try:
                    os.rename(
                        f"{self.minecraft_dir}/versions/{self.selected_version}/saves/{self.save_selected}",
                        f"{self.minecraft_dir}/versions/{self.selected_version}/saves/{name}",
                    )
                    tkinter.messagebox.showinfo(
                        "完成!", f"已将{self.save_selected}重命名为{name}!"
                    )
                except Exception as exp:
                    tkinter.messagebox.showerror("错误", f"无法完成重命名:{exp}")

    def reload_save(self, *args):
        if self.save_selected == "..返回上一级":
            self.load_saves()
        elif self.save_selected == "重命名此版本":
            self.rename_save()

    def load_saves(self):
        self.ModListListBox.delete(0, tk.END)
        self.ModListListBox.insert(0, "正在加载存档...")
        try:
            self.d_mod.config(state=tk.DISABLED)
            self.e_mod.config(state=tk.DISABLED)
            save_list = os.listdir(
                f"{self.minecraft_dir}/versions/{self.selected_version}/saves"
            )
            self.ModListListBox.bind("<<ListboxSelect>>", self.get_save_to_modify)
            self.ModListListBox.bind("<Double-Button-1>", self.get_nex_one)
            self.ModListListBox.delete(0, tk.END)
            for i in save_list:
                self.ModListListBox.insert(0, i)
            self.ModListListBox.insert(0, "修改版本光影包...")
            self.ModListListBox.insert(0, "修改版本资源包...")
        except:
            self.ModListListBox.delete(0, tk.END)
            self.ModListListBox.insert(0, "错误的版本或者没有存档文件夹")

    def check_java(self, java_version: str, minecraft_version: str) -> bool:
        try:
            java_major = parse_java_major(java_version)
        except ValueError:
            return True
        need = required_java_version(minecraft_version)
        if need == 0:
            return True
        return java_major >= need

    def get_launch_java(self):
        """返回用户选中的 Java 路径, 选择"自动选择"时返回 None"""
        if self.Java_Combobox.get() == "自动选择":
            return None
        try:
            index = self.CurJavaVar - 1
            places = self.get_java_place()
            if 0 <= index < len(places):
                return places[index]
        except Exception as exp:
            print(f"[WARN] 无法获取选中的 Java: {exp}")
        return None

    def build_launch_options(self, executable_path=None, game_directory=None):
        """构造离线账户的启动参数"""
        username = str(self.Username or "").strip()
        if username in ("", "暂无数据"):
            username = "Player"
        options = {
            "username": username,
            "uuid": offline_uuid(username),
            "token": "",
            "userType": "legacy",
            "launcherName": "PML Launcher",
            "launcherVersion": "4.4",
            "gameDirectory": game_directory or self.minecraft_dir,
        }
        if executable_path:
            options["executablePath"] = executable_path
        return options

    def get_base_game_directory(self):
        """不隔离时游戏使用的目录"""
        return self.minecraft_dir

    def get_isolated_game_directory(self):
        """完全隔离时游戏使用的目录: versions/<版本>"""
        return os.path.join(
            self.minecraft_dir, "versions", str(self.selected_version)
        ).replace("\\", "/")

    def copy_mods_to_global(self):
        """版本隔离: 把当前版本的 mod 临时复制到全局 mods 目录"""
        version_mods = f"{self.minecraft_dir}/versions/{self.selected_version}/mods"
        global_mods = f"{self.minecraft_dir}/mods"
        copied = []
        try:
            os.makedirs(global_mods, exist_ok=True)
            for name in os.listdir(version_mods):
                if not name.endswith(".jar"):
                    continue
                target = os.path.join(global_mods, name)
                if os.path.exists(target):
                    print(f"[INFO] 已存在同名 mod, 跳过: {target}")
                    continue
                shutil.copy2(os.path.join(version_mods, name), target)
                copied.append(name)
        except OSError as exp:
            print(f"[ERROR] 复制 mod 失败: {exp}")
        return copied

    def restore_mods_from_global(self, copied):
        """版本隔离: 游戏结束后清理临时复制到全局 mods 目录的文件"""
        global_mods = f"{self.minecraft_dir}/mods"
        for name in copied:
            target = os.path.join(global_mods, name)
            try:
                if os.path.exists(target):
                    os.remove(target)
            except OSError as exp:
                print(f"[WARN] 无法删除临时 mod {target}: {exp}")

    def start_game(self, isolation_mode=_NOT_GIVEN, java_path=_NOT_GIVEN):
        """启动游戏(隔离模式和 Java 路径在界面线程中读取后传入)"""
        if isolation_mode is _NOT_GIVEN:
            isolation_mode = self.get_isolation_mode()
        if isolation_mode not in (
            ISOLATION_NONE,
            ISOLATION_MOD,
            ISOLATION_FULL,
        ):
            isolation_mode = ISOLATION_NONE
        if java_path is _NOT_GIVEN:
            java_path = self.get_launch_java()
        if str(self.selected_version or "").strip() in ("", "暂无数据"):
            self.ui_call(
                tkinter.messagebox.showerror, "错误", "你没有选择要启动的版本!"
            )
            return
        game_directory = self.get_base_game_directory()
        if isolation_mode == ISOLATION_FULL:
            # 完全隔离: 游戏直接以 versions/<版本> 作为游戏目录,
            # mods/存档/资源包/光影/配置/options.txt 都会保存在这个文件夹里
            game_directory = self.get_isolated_game_directory()
            if not os.path.isdir(game_directory):
                self.ui_call(
                    tkinter.messagebox.showerror,
                    "错误",
                    f"找不到版本 {self.selected_version} 的安装目录:\n{game_directory}\n"
                    "请到「版本选择&版本设置」里点 🔄 检查游戏目录是否正确。",
                )
                return
            print(f"[INFO] 已开启版本隔离, 游戏目录: {game_directory}")

        copied_mods = []
        try:
            if isolation_mode == ISOLATION_MOD:
                copied_mods = self.copy_mods_to_global()

            if java_path is not None:
                java_version = self.get_java_version_by_place(java_path)
                if not self.check_java(java_version, self.selected_version):
                    answer = messagebox.askyesnocancel(
                        "警告",
                        f"要启动的版本是{self.selected_version}, 但是要求的使用的Java是{java_version}。\n"
                        "你确定要使用这个Java吗？\n"
                        "这可能会带来不希望的报错。\n"
                        "(确定请按 Yes/是，不确定请按 No/否，取消请按 Cancel/取消)",
                    )
                    if answer is None:
                        return
                    if answer is False:
                        java_path = None

            options = self.build_launch_options(java_path, game_directory)
            minecraft_command = mll.command.get_minecraft_command(
                self.selected_version, self.minecraft_dir, options
            )
            print(f"[INFO] 启动命令: {subprocess.list2cmdline(minecraft_command)}")
            process = subprocess.Popen(minecraft_command, cwd=game_directory)
            self.game_processes.append(process)
            self.ui_call(self.set_close_button_visible, True)
            try:
                process.wait()
            finally:
                try:
                    self.game_processes.remove(process)
                except ValueError:
                    pass
                self.ui_call(
                    self.set_close_button_visible, bool(self.game_processes)
                )
            if process.returncode != 0:
                print(f"[WARN] 游戏进程已退出, 返回码: {process.returncode}")
        except mll.exceptions.VersionNotFound:
            self.ui_call(
                tkinter.messagebox.showerror,
                "错误",
                f"找不到版本 {self.selected_version}, 请先下载这个版本!",
            )
        except Exception as exp:
            print(f"[ERROR] 启动游戏失败: {exp}")
            self.ui_call(
                tkinter.messagebox.showerror, "错误", f"启动游戏失败:{exp}"
            )
        finally:
            if copied_mods:
                self.restore_mods_from_global(copied_mods)

    def create_modify(self):
        animation.MoveTkWidget(
            self.Menu_Butt_modify,
            (50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Change_Dir, (50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.VersionListListBox,
            (0, 500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.VerDescription,
            (-1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()

    def add_mod(self):
        modplace = tk.filedialog.askopenfilename(title="打开mod位置")
        if modplace == "" or not self.support_mod:
            return
        mods_dir = f"{self.minecraft_dir}/versions/{self.selected_version}/mods"
        try:
            os.makedirs(mods_dir, exist_ok=True)
            shutil.copy(modplace, os.path.join(mods_dir, os.path.basename(modplace)))
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法安装这个mod:{exp}")
            return
        tkinter.messagebox.showinfo(
            "成功",
            f"已成功安装{os.path.basename(modplace)}到{self.selected_version}",
        )
        self.reload_mods()

    def get_selected_mod(self):
        """返回当前选中的 mod 文件名, 没有选中时返回 None"""
        selection = self.ModListListBox.curselection()
        if selection == ():
            return None
        index = selection[0]
        if index >= len(self.modlistlist):
            return None
        return self.modlistlist[index]

    def is_disabled(self):
        mod_name = self.get_selected_mod()
        if mod_name is None:
            return False
        return mod_name.endswith(".disabled")

    def disable_mod(self):
        mod_name = self.get_selected_mod()
        if mod_name is None:
            tkinter.messagebox.showerror("错误", "你没有选择任何mod!")
            return
        if mod_name.endswith(".disabled"):
            return
        mods_dir = f"{self.minecraft_dir}/versions/{self.selected_version}/mods"
        try:
            os.rename(
                os.path.join(mods_dir, mod_name),
                os.path.join(mods_dir, mod_name + ".disabled"),
            )
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法禁用{mod_name}:{exp}")
            return
        self.reload_mods()

    def enable_mod(self):
        mod_name = self.get_selected_mod()
        if mod_name is None:
            tkinter.messagebox.showerror("错误", "你没有选择任何mod!")
            return
        if not mod_name.endswith(".disabled"):
            return
        mods_dir = f"{self.minecraft_dir}/versions/{self.selected_version}/mods"
        try:
            os.rename(
                os.path.join(mods_dir, mod_name),
                os.path.join(mods_dir, mod_name[:-9]),
            )
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法启用{mod_name}:{exp}")
            return
        self.reload_mods()

    def UpdateModListAndUpdateModLoaderSupport(self, *args):
        if self.VersionListListBox.curselection() != ():
            self.selected_version = self.VersionListListBox.get(
                self.VersionListListBox.curselection()[0]
            )
            if len(self.selected_version) >= len("1.20.3 Fabric 0.16.2"):
                self.Start_Game_Label.config(
                    text=f"是时候启动游戏了！\n正在使用的账户:{self.Username}\n准备启动游戏:{self.selected_version[:19]}\n{self.selected_version[19:]}"
                )
                self.Start_Game_Label.place(x=900, y=483)
            else:
                self.Start_Game_Label.config(
                    text=f"是时候启动游戏了！\n正在使用的账户:{self.Username}\n准备启动游戏:{self.selected_version}"
                )
                self.Start_Game_Label.place(x=900, y=500)
            self.save_all()
            try:
                version_path = (
                    f"{self.minecraft_dir}/versions/{self.selected_version}"
                )
                for i in os.listdir(version_path):
                    if i.endswith(".json"):
                        with open(
                            os.path.join(version_path, i),
                            encoding="utf-8",
                            errors="replace",
                        ) as version_file:
                            version_json = version_file.read().lower()
                        self.support_mod = any(
                            loader in version_json
                            for loader in ("forge", "fabric", "quilt", "neoforge")
                        )
                        self.supply_mod_loading.config(
                            text=(
                                "支持mod加载:支持"
                                if self.support_mod
                                else "支持mod加载:不支持"
                            )
                        )
                        break
                self.reload_mods()
            except OSError:
                pass

    def download_minecraft_version_theard(self):
        if self.downloading:
            tkinter.messagebox.showinfo("提示", "已经有下载任务正在进行中。")
            return
        if not self.download_version_to:
            tkinter.messagebox.showerror("错误!", "你没有选择任何版本!")
            return
        version = self.download_version_to
        mod_loader = self.ModLoader.get()
        loader_version = (self.ModLoaderVersion.get() or "").strip()
        java_path = self.get_launch_java()
        self.start_download_ui(version, mod_loader)
        threading.Thread(
            target=self.download_version,
            args=(version, mod_loader, loader_version, java_path),
            daemon=True,
        ).start()
        print("成功创建下载任务:", version)

    def delete_version(self):
        """删除当前选中的已安装版本"""
        selection = self.VersionListListBox.curselection()
        if selection == ():
            tkinter.messagebox.showerror("错误", "你没有选择要删除的版本!")
            return
        if self.downloading:
            tkinter.messagebox.showinfo("提示", "正在下载版本，请等下载完成后再删除。")
            return
        index = selection[0]
        version = self.VersionListListBox.get(index)
        if not version or version == "暂无数据":
            return
        version_dir = os.path.join(self.minecraft_dir, "versions", version)
        if not os.path.isdir(version_dir):
            tkinter.messagebox.showerror("错误", f"找不到版本文件夹:{version_dir}")
            return
        if not tkinter.messagebox.askyesno(
            "删除版本",
            f"确定要删除版本「{version}」吗？\n"
            f"文件夹: {version_dir}\n"
            "该版本文件夹里的 mod、存档、配置等都会被一起删除，且无法恢复。",
        ):
            return
        try:
            shutil.rmtree(version_dir)
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"删除失败:{exp}")
            return
        self.reload_versions()
        self.VersionListListBox.delete(0, tk.END)
        for i in self.downloaded_minecraft_versions:
            if i != "" and not i.isspace():
                self.VersionListListBox.insert(0, i)
        if self.selected_version == version:
            self.selected_version = "暂无数据"
            self.support_mod = False
            self.modlistlist = []
            self.ModListListBox.delete(0, tk.END)
            self.Start_Game_Label.config(
                text=f"是时候启动游戏了！\n正在使用的账户:{self.Username}\n准备启动游戏:{self.selected_version}"
            )
        self.save_all()
        tkinter.messagebox.showinfo("完成", f"已删除版本:{version}")

    def get_nbt_initial_dir(self):
        """打开 NBT 文件时的默认目录: 上次目录 -> 全局 saves -> 当前版本 saves"""
        last_dir = getattr(self, "_nbt_last_dir", "")
        if last_dir and os.path.isdir(last_dir):
            return last_dir
        if not self.minecraft_dir:
            return os.getcwd()
        for candidate in (
            os.path.join(self.minecraft_dir, "saves"),
            os.path.join(
                self.minecraft_dir, "versions", str(self.selected_version), "saves"
            ),
        ):
            if os.path.isdir(candidate):
                return candidate
        return self.minecraft_dir

    def show_nbt_viewer(self):
        """打开只读的 NBT 查看器"""
        if getattr(self, "nbt_window", None) is not None:
            try:
                if self.nbt_window.winfo_exists():
                    self.nbt_window.deiconify()
                    self.nbt_window.lift()
                    return
            except tk.TclError:
                pass
        self.nbt_window = tk.Toplevel(self.main_win)
        self.nbt_window.title("NBT 查看器")
        self.nbt_window.geometry("960x620")
        self.nbt_window.transient(self.main_win)
        try:
            self.nbt_window.attributes("-alpha", self.alpha)
        except tk.TclError:
            pass
        try:
            self.nbt_window.iconbitmap("PML/ddd.ico")
        except tk.TclError:
            pass

        top = tk.Frame(self.nbt_window)
        top.pack(fill="x", padx=10, pady=8)
        self.nbt_path_var = tk.StringVar(value="未打开文件")
        tk.Label(top, textvariable=self.nbt_path_var, anchor="w").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(top, text="全部折叠", command=self.collapse_nbt_tree).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(top, text="打开文件...", command=self.open_nbt_file).pack(
            side="right"
        )

        tree_frame = tk.Frame(self.nbt_window)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.nbt_tree = ttk.Treeview(
            tree_frame, columns=("type", "value"), show="tree headings"
        )
        self.nbt_tree.heading("#0", text="名称 / 索引")
        self.nbt_tree.heading("type", text="类型")
        self.nbt_tree.heading("value", text="值")
        self.nbt_tree.column("#0", width=300, anchor="w")
        self.nbt_tree.column("type", width=110, anchor="w")
        self.nbt_tree.column("value", width=500, anchor="w")
        yscroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.nbt_tree.yview
        )
        xscroll = ttk.Scrollbar(
            tree_frame, orient="horizontal", command=self.nbt_tree.xview
        )
        self.nbt_tree.configure(
            yscrollcommand=yscroll.set, xscrollcommand=xscroll.set
        )
        self.nbt_tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.nbt_tree.bind("<<TreeviewOpen>>", self.on_nbt_tree_open)

        tk.Label(
            self.nbt_window,
            text="只读查看，不会修改文件。支持 .dat / .nbt，不支持 region(.mca) 文件。",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 8))
        self.nbt_tree.delete(*self.nbt_tree.get_children(""))

    def open_nbt_file(self, path=None):
        """读取并显示一个 NBT 文件"""
        if not path:
            path = tkinter.filedialog.askopenfilename(
                title="选择 NBT 文件",
                initialdir=self.get_nbt_initial_dir(),
                filetypes=[
                    ("NBT 数据文件", "*.dat"),
                    ("NBT 文件", "*.nbt"),
                    ("所有文件", "*.*"),
                ],
            )
        if not path:
            return
        try:
            root = read_nbt_file(path)
        except Exception as exp:
            tkinter.messagebox.showerror(
                "无法读取 NBT", f"{os.path.basename(path)}\n{exp}"
            )
            return
        self._nbt_tags = {}
        self._nbt_placeholders = set()
        self._nbt_last_dir = os.path.dirname(os.path.abspath(path))
        self.nbt_tree.delete(*self.nbt_tree.get_children(""))
        self.nbt_path_var.set(path)
        title = root.name or os.path.basename(path)
        iid = self.nbt_tree.insert(
            "",
            "end",
            text=title,
            values=(nbt_type_label(root), nbt_summary(root)),
            open=True,
        )
        self._nbt_tags[iid] = root
        self.populate_nbt_children(iid, root)

    def populate_nbt_children(self, parent, tag):
        if tag.tag_type == NBT_COMPOUND:
            for name, child in tag.value.items():
                self.insert_nbt_row(parent, name, child)
        elif tag.tag_type == NBT_LIST:
            for index, child in enumerate(tag.value):
                self.insert_nbt_row(parent, f"[{index}]", child)

    def insert_nbt_row(self, parent, label, tag):
        iid = self.nbt_tree.insert(
            parent,
            "end",
            text=label,
            values=(nbt_type_label(tag), nbt_summary(tag)),
        )
        self._nbt_tags[iid] = tag
        if (tag.tag_type == NBT_COMPOUND and tag.value) or (
            tag.tag_type == NBT_LIST and tag.value
        ):
            dummy = self.nbt_tree.insert(
                iid, "end", text="正在加载...", values=("", "")
            )
            self._nbt_placeholders.add(dummy)

    def on_nbt_tree_open(self, event=None):
        iid = self.nbt_tree.focus()
        tag = self._nbt_tags.get(iid)
        if tag is None:
            return
        children = self.nbt_tree.get_children(iid)
        if len(children) == 1 and children[0] in self._nbt_placeholders:
            self._nbt_placeholders.discard(children[0])
            self.nbt_tree.delete(children[0])
            self.populate_nbt_children(iid, tag)

    def collapse_nbt_tree(self):
        for iid in self.nbt_tree.get_children(""):
            self.nbt_tree.item(iid, open=False)

    def change_version_and_modify_version(self):
        self.set_current_page("modify")
        self.reload_versions()
        self.delete_main()
        self.create_modify()
        self.VersionListListBox.delete(0, tk.END)
        for i in self.downloaded_minecraft_versions:
            if i != "" and not i.isspace():
                self.VersionListListBox.insert(0, i)

    def delete_PML_settings(self):
        animation.MoveTkWidget(
            self.Menu_Butt_Settings,
            (-50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.PML_Setting_Frame,
            (0, -300),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        self.create_main()

    def create_PML_settings(self):
        animation.MoveTkWidget(
            self.Menu_Butt_Settings,
            (50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.PML_Setting_Frame,
            (0, 300),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()

    def background_widgets(self):
        """需要跟随背景颜色一起变化的控件"""
        return (
            self.main_win,
            self.Label,
            self.Start_Game_Label,
            self.ColorSetLabel,
            self.PML_Setting_Frame,
            self.scale,
        )

    def apply_background(self, color):
        """设置背景颜色(None 表示恢复默认配色)"""
        target = self.default_bg if color is None else color
        for widget in self.background_widgets():
            try:
                widget.config(bg=target)
            except tk.TclError as exp:
                print(f"[WARN] 无法设置背景颜色: {exp}")
        self.bg = color
        self.save_all()

    def set_color(self):
        color = tkinter.colorchooser.askcolor(title="设置背景颜色")
        if color[1] is None:
            return
        self.apply_background(color[1])

    def reset_color(self):
        """恢复默认背景颜色"""
        self.apply_background(None)

    def from_menu_to_PML_settings_page(self):
        self.set_current_page("settings")
        self.delete_main()
        self.create_PML_settings()

    def AddNewUser(self):
        user_win = tk.Tk()
        user_win.title("添加用户")
        user_win.geometry("300x200")
        user_win.iconbitmap("./PML/ddd.ico")

        def check(event):
            if user_type.get() == "离线登录":
                label = tk.Label(user_win, text="用户名:")
                label.grid(column=1, row=2)
                self.Entry = tk.Entry(user_win)
                self.Entry.grid(column=2, row=2)

        def apply_func():
            username = self.Entry.get().strip()
            if username == "":
                messagebox.showerror("提示!", "笨蛋!你用户名都没填!")
            elif not username.isascii():
                messagebox.showerror("提示!", "用户名不可为中文!")
            else:
                self.username_listbox.insert(tk.END, username)
                self.UsernameList.append(username)
                user_win.destroy()
                self.save_all()

        def cancel_func():
            user_win.destroy()

        label = tk.Label(user_win, text="用户名:")
        label.grid(column=1, row=2)
        self.Entry = tk.Entry(user_win)
        self.Entry.grid(column=2, row=2)
        tk.Label(user_win, text="用户类型:").grid(column=1, row=1)
        user_type = ttk.Combobox(user_win, values=["离线登录"], state="readonly")
        user_type.current(0)
        user_type.grid(column=2, row=1)
        user_type.bind("<<ComboboxSelected>>", check)
        cancel = ttk.Button(user_win, text="取消", command=cancel_func)
        cancel.grid(column=1, row=3)
        apply = ttk.Button(user_win, text="确认", command=apply_func)
        apply.grid(column=2, row=3)

        user_win.mainloop()

    def DeleteUser(self):
        selection = self.username_listbox.curselection()
        if selection == ():
            tkinter.messagebox.showerror("错误!", "你没有选择用户!")
            return
        index = selection[0]
        username = self.username_listbox.get(index)
        if username in self.UsernameList:
            self.UsernameList.remove(username)
        self.username_listbox.delete(index)
        if self.Username == username:
            self.Username = "暂无数据"
            self.Start_Game_Label.config(
                text=f"是时候启动游戏了！\n正在使用的账户:{self.Username}\n准备启动游戏:{self.selected_version}"
            )
        self.save_all()

    def delete_settings(self):
        animation.MoveTkWidget(
            self.Menu_Butt_User,
            (-50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Add_User, (-50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.Delete_User, (-50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.username_listbox,
            (0, -500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.UserDescription,
            (1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        self.create_main()

    def get_username_to_set(self, *args):
        selection = self.username_listbox.curselection()
        if selection != ():
            self.current_username = self.username_listbox.get(selection[0])

    def apply_username(self, *args):
        username = str(self.current_username or "").strip()
        if username == "":
            return
        self.Username = username
        self.save_all()
        self.Start_Game_Label.config(
            text=f"是时候启动游戏了！\n正在使用的账户:{self.Username}\n准备启动游戏:{self.selected_version}"
        )
        messagebox.showinfo("成功!", f"用户名已被设置为{self.Username}")

    def create_user(self):
        animation.MoveTkWidget(
            self.Menu_Butt_User,
            (50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Add_User, (50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.Delete_User, (50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.username_listbox,
            (0, 500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.UserDescription,
            (-1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()

    def from_menu_to_user_settigs_page(self):
        self.set_current_page("user")
        self.delete_main()
        self.create_user()
        self.username_listbox.delete(0, "end")
        for i in self.UsernameList:
            if i != "" and not i.isspace():
                self.username_listbox.insert(tk.END, i)

    def check_support(self, *args):
        selection = self.version_listbox.curselection()
        if selection == ():
            return
        version = self.version_listbox.get(selection[0])
        if version == "正在加载..." or version.startswith("网络不畅"):
            return
        self.download_version_to = version

        def main():
            self.ui_call(self.SupportFabricLabel.config, text="Fabric支持:正在加载...")
            self.ui_call(self.SupportForgeLabel.config, text="Forge支持:正在加载...")
            try:
                fabric_supported = bool(
                    mll.fabric.is_minecraft_version_supported(version)
                )
            except Exception as exp:
                # 官方源失败时尝试用镜像判断, 避免直接显示“不支持”
                print(f"[WARN] 官方源检查 Fabric 失败: {type(exp).__name__}")
                fabric_supported = self.fabric_supported_by_mirror(version)
            try:
                forge_supported = mll.forge.find_forge_version(version) is not None
            except Exception as exp:
                print(f"[WARN] 官方源检查 Forge 失败: {type(exp).__name__}")
                mirror_forge_versions = self.fetch_forge_versions_from_mirror(version)
                forge_supported = (
                    None
                    if mirror_forge_versions is None
                    else bool(mirror_forge_versions)
                )
            if fabric_supported is None:
                fabric_state = "未知(网络异常)"
            else:
                fabric_state = "支持" if fabric_supported else "不支持"
            if forge_supported is None:
                forge_state = "未知(网络异常)"
            else:
                forge_state = "支持" if forge_supported else "不支持"
            self.support_fabric = "true" if fabric_supported else "false"
            self.support_forge = "true" if forge_supported else "false"
            self.ui_call(
                self.SupportFabricLabel.config, text=f"Fabric支持:{fabric_state}"
            )
            self.ui_call(
                self.SupportForgeLabel.config, text=f"Forge支持:{forge_state}"
            )
            mod_loaders = ["原版"]
            if fabric_supported is not False:
                mod_loaders.append("Fabric")
            if forge_supported is not False:
                mod_loaders.append("Forge")
            self.ui_call(self.apply_mod_loader_support, mod_loaders)

        threading.Thread(target=main, daemon=True).start()

    def apply_mod_loader_support(self, mod_loaders):
        self.support_mod_loaders = mod_loaders
        self.ModLoaderVersion.set("")
        self.ModLoaderVersionOption.config(values=[])
        self.ModLoaderOption.config(values=mod_loaders)
        self.ModLoaderOption.current(0)

    def change_minecraft_dir(self):
        to_change = tkinter.filedialog.askdirectory()
        if to_change == "":
            return
        to_change = "/".join(os.path.abspath(to_change).split("\\"))
        try:
            os.makedirs(os.path.join(to_change, "versions"), exist_ok=True)
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法使用这个文件夹:{exp}")
            return
        self.minecraft_dir = to_change
        self.reload_mod_tkinter()
        self.save_all()

    def reload_versions(self):
        try:
            self.downloaded_minecraft_versions = os.listdir(
                os.path.join(self.minecraft_dir, "versions")
            )
        except OSError:
            self.downloaded_minecraft_versions = []

    def reload_mod_tkinter(self):
        self.reload_versions()
        try:
            self.VersionListListBox.delete(0, tk.END)
            for i in self.downloaded_minecraft_versions:
                self.VersionListListBox.insert(0, i)
        except AttributeError:
            pass

    def pre_do(self):
        """清理列表项两端可能残留的引号(兼容旧配置文件)"""

        def clean(item):
            item = str(item)
            if len(item) >= 2 and item[0] == item[-1] and item[0] in "'\"":
                item = item[1:-1]
            return item

        self.ServerPath = [clean(i) for i in self.ServerPath]
        self.UsernameList = [clean(i) for i in self.UsernameList]
        self.exjavaplace = [clean(i) for i in self.exjavaplace]

    def save_all(self):
        background = "" if self.bg is None else str(self.bg)
        token = "" if self.Token is None else str(self.Token)
        self.pre_do()
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(
                    f"UsernameList = {self.UsernameList!r}\n"
                    + f"alpha = {self.alpha}\n"
                    + f"ServerList = {self.ServerList!r}\n"
                    + f'Background = "{background}"\n'
                    + f"ServerPath = {self.ServerPath!r}\n"
                    + f'LastDict = "{self.minecraft_dir}"\n'
                    + f'LastLaunch = "{self.selected_version}"\n'
                    + f'LastUsername = "{self.Username}"\n'
                    + f'Token = "{token}"\n'
                    + f"VerSplit = {self.Versplitvar}\n"
                    + f"curJava = {self.CurJavaVar}\n"
                    + f"exJava = {self.exjavaplace!r}\n"
                )
        except OSError as exp:
            print(f"[ERROR] 保存配置失败: {exp}")

    def DeleteServer(self):
        selection = self.server_listbox.curselection()
        if selection == ():
            tkinter.messagebox.showerror("错误!", "你没有选择服务器!")
            return
        index = selection[0]
        server_name = self.server_listbox.get(index)
        if server_name in self.ServerList:
            self.ServerList.remove(server_name)
        if 0 <= index < len(self.ServerPath):
            del self.ServerPath[index]
        self.server_listbox.delete(index)
        self.save_all()

    def AddNewServer(self):
        self.Server_win = tk.Tk()
        self.Server_win.iconbitmap("./PML/ddd.ico")
        self.Server_win.geometry("400x300")
        self.Server_win.title("添加服务器")
        self.Server_win.resizable(False, False)

        def find_server_place():
            self.place = tkinter.filedialog.askopenfilename(
                title="服务器核心文件位置选择", filetypes=[("jar文件", "*.jar")]
            )
            self.Server_Place.destroy()
            try:
                self.Label_Server_Place.config(text=self.place)
            except AttributeError:
                if len(self.place) <= 13:
                    self.Label_Server_Place = tk.Label(self.Server_win, text=self.place)
                else:
                    self.Label_Server_Place = tk.Label(
                        self.Server_win, text=self.place[0:13] + "\n" + self.place[13:]
                    )
                self.Label_Server_Place.grid(row=2, column=2, columnspan=100)

            self.Server_Place = tk.Button(
                self.Server_win, text="更改", command=find_server_place
            )
            self.Server_Place.grid(row=3, column=1)
            self.jump_eula_loading.grid(column=1, row=4)
            self.create_server_button.grid(column=1, row=5, columnspan=100, padx=5)

        def create_server():
            try:
                jump_eula = str(var.get()).lower() in ("on", "true", "1")
                server_name = self.Server_Name.get().strip()
                if self.place == "":
                    tkinter.messagebox.showerror("错误!", "你还没有选择服务器地址!")
                    return
                if server_name == "":
                    tkinter.messagebox.showerror("错误!", "你还没有填写服务器名称!")
                    return
                server_dir = os.path.abspath(
                    os.path.join(os.path.dirname(self.place), server_name)
                )
                server_jar = os.path.join(server_dir, os.path.basename(self.place))
                os.makedirs(server_dir, exist_ok=True)
                shutil.copyfile(os.path.abspath(self.place), server_jar)
                self.ServerList.append(server_name)
                self.ServerPath.append(server_jar.replace("\\", "/"))
                self.server_listbox.insert(tk.END, server_name)
                self.save_all()

                def run_server_once():
                    tmp_working = os.getcwd()
                    os.chdir(server_dir)
                    try:
                        if jump_eula:
                            # 必须在启动之前写入, 而且需要覆盖服务器自己生成的 eula=false
                            with open("./eula.txt", "w", encoding="utf-8", newline="\n") as f:
                                f.write("eula=true\n")
                        subprocess.call(
                            ["java", "-jar", f"./{os.path.basename(server_jar)}"]
                        )
                    finally:
                        os.chdir(tmp_working)

                t1 = threading.Thread(target=run_server_once, daemon=True)
                t1.start()
            except AttributeError:
                tkinter.messagebox.showerror("错误!", "你还没有选择服务器地址!")
            except OSError as exp:
                tkinter.messagebox.showerror("错误!", f"创建服务器失败:{exp}")

        tk.Label(self.Server_win, text="服务器名称:").grid(column=1, row=1)
        self.Server_Name = tk.Entry(self.Server_win)
        self.Server_Name.grid(column=2, row=1)
        tk.Label(self.Server_win, text="服务器位置:").grid(column=1, row=2)
        self.Server_Place = tk.Button(
            self.Server_win, text="选择服务器位置", command=find_server_place
        )
        self.Server_Place.grid(column=2, row=2)
        var = tk.BooleanVar()
        var.set(True)
        self.jump_eula_loading = tk.Checkbutton(
            self.Server_win,
            text="跳过EULA加载",
            onvalue="on",
            offvalue="off",
            variable=var,
        )
        self.jump_eula_loading.grid(column=1, row=3)
        self.jump_eula_loading.select()
        self.create_server_button = tk.Button(
            self.Server_win,
            text="创建服务器",
            width=54,
            relief="groove",
            command=create_server,
        )
        self.create_server_button.grid(column=1, row=4, columnspan=100, padx=5)

        self.Server_win.mainloop()

    def set_status(self, status: str):
        self.status = status
        print(f"下载状态：{status}")
        self.ui_call(self.update_progress_ui)

    def set_progress(self, progress: int):
        try:
            self.current_progress = int(progress)
        except (TypeError, ValueError):
            self.current_progress = 0
        if self.current_max != 0:
            self.progress = f"{progress}/{self.current_max}"
            print(f"下载状态:{progress}/{self.current_max}")
        self.ui_call(self.update_progress_ui)

    def set_max(self, new_max: int):
        try:
            self.current_max = int(new_max)
        except (TypeError, ValueError):
            self.current_max = 0
        self.ui_call(self.update_progress_ui)

    def set_progress_button_visible(self, visible):
        """显示/隐藏"查看下载进度"按钮(从左侧滑入/滑出)"""
        if visible and not self.progress_button_visible:
            self.ProgressButton.place(x=-200, y=530)
            animation.MoveTkWidget(
                self.ProgressButton,
                (215, 0),
                500,
                fps=60,
                controller=animation.smooth,
            ).start()
            self.progress_button_visible = True
        elif not visible and self.progress_button_visible:
            animation.MoveTkWidget(
                self.ProgressButton,
                (-215, 0),
                500,
                fps=60,
                controller=animation.smooth,
            ).start()
            self.progress_button_visible = False

    def set_current_page(self, page):
        """记录当前页面, 用于决定下载进度按钮要不要显示"""
        self.current_page = page
        self.refresh_progress_button()

    def refresh_progress_button(self):
        """只有正在下载且在主界面/下载页/进度页时才显示进度按钮"""
        visible = bool(self.downloading) and self.current_page in (
            "main",
            "download",
            "progress",
        )
        self.set_progress_button_visible(visible)

    def start_download_ui(self, version="", mod_loader=""):
        """开始下载时重置进度并显示"查看下载进度"按钮"""
        self.downloading = True
        self.status = "正在准备下载..."
        self.current_progress = 0
        self.current_max = 0
        if version:
            self.progress_version_var.set(f"版本: {version}（{mod_loader}）")
        else:
            self.progress_version_var.set("")
        self.DownloadButton.config(state=tk.DISABLED)
        self.refresh_progress_button()
        self.update_progress_ui()

    def finish_download_ui(self, success):
        self.downloading = False
        self.DownloadButton.config(state=tk.NORMAL)
        self.status = "下载完成" if success else "下载失败"
        self.update_progress_ui()
        self.refresh_progress_button()

    def create_progress_page(self):
        """滑入下载进度页"""
        animation.MoveTkWidget(
            self.Menu_Butt_progress,
            (50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.ProgressDescription,
            (-1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()

    def delete_progress_page(self):
        """滑出下载进度页"""
        animation.MoveTkWidget(
            self.Menu_Butt_progress,
            (-50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.ProgressDescription,
            (1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()

    def from_download_to_progress_page(self):
        """从下载页切换到下载进度页"""
        if self.progress_page_open:
            return
        self.progress_page_open = True
        animation.MoveTkWidget(
            self.Menu_Butt_download,
            (-50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.version_listbox,
            (0, -500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.VersionDescription,
            (1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        self.create_progress_page()
        self.set_current_page("progress")
        self.update_progress_ui()

    def from_main_to_progress_page(self):
        """从主界面直接打开下载进度页(下载时点外面的进度按钮)"""
        self.delete_main()
        self.create_progress_page()
        self.progress_page_open = True
        self.set_current_page("progress")
        self.update_progress_ui()

    def from_progress_to_download_page(self):
        """从下载进度页返回(回到下载页或主界面)"""
        if not self.progress_page_open:
            return
        self.progress_page_open = False
        self.delete_progress_page()
        if self.download_page_open:
            self.create_download()
            self.set_current_page("download")
        else:
            self.create_main()

    def show_download_progress(self):
        """查看下载进度(切换到下载进度页)"""
        if self.progress_page_open:
            return
        if self.download_page_open:
            self.from_download_to_progress_page()
        else:
            self.from_main_to_progress_page()

    def update_progress_ui(self):
        maximum = self.current_max or 0
        value = self.current_progress or 0
        if maximum > 0:
            percent = value / maximum * 100
            self.progress_bar.config(maximum=maximum)
            self.progress_value_var.set(min(value, maximum))
            self.progress_percent_var.set(f"{value}/{maximum} ({percent:.0f}%)")
        else:
            self.progress_bar.config(maximum=100)
            self.progress_value_var.set(0)
            self.progress_percent_var.set("正在准备...")
        self.progress_status_var.set(getattr(self, "status", "") or "正在下载...")

    def download_version(
        self,
        version=_NOT_GIVEN,
        mod_loader=_NOT_GIVEN,
        loader_version=_NOT_GIVEN,
        java_path=_NOT_GIVEN,
    ):
        """下载/安装指定版本

        参数在界面线程中读取后传入, 避免在子线程里访问 Tk 变量。
        """
        if version is _NOT_GIVEN:
            version = self.download_version_to
        if mod_loader is _NOT_GIVEN:
            mod_loader = self.ModLoader.get()
        if loader_version is _NOT_GIVEN:
            loader_version = self.ModLoaderVersion.get()
        loader_version = (loader_version or "").strip()
        if loader_version == "最新版本":
            loader_version = ""
        if java_path is _NOT_GIVEN:
            java_path = self.get_launch_java()

        if not version:
            self.ui_call(
                tkinter.messagebox.showerror, "错误!", "你没有选择任何版本!"
            )
            self.ui_call(self.finish_download_ui, False)
            return
        self.callback = {
            "setStatus": self.set_status,
            "setProgress": self.set_progress,
            "setMax": self.set_max,
        }
        try:
            os.makedirs(os.path.join(self.minecraft_dir, "versions"), exist_ok=True)
            if mod_loader == "原版":
                mll.install.install_minecraft_version(
                    version, self.minecraft_dir, self.callback
                )
            elif mod_loader == "Forge":
                forge_version = self.get_forge_version_id(loader_version, version)
                if not forge_version:
                    self.ui_call(
                        tkinter.messagebox.showerror,
                        "错误!",
                        f"没有找到 {version} 可用的 Forge 版本!\n"
                        "可以点开“选择Mod加载器版本”手动填写, 例如 47.2.0",
                    )
                    self.ui_call(self.finish_download_ui, False)
                    return
                install_options = {"callback": self.callback}
                if java_path and supports_java_argument(
                    mll.forge.install_forge_version
                ):
                    install_options["java"] = java_path
                mll.forge.install_forge_version(
                    forge_version, self.minecraft_dir, **install_options
                )
            elif mod_loader == "Fabric":
                install_options = {"callback": self.callback}
                if java_path and supports_java_argument(mll.fabric.install_fabric):
                    install_options["java"] = java_path
                mll.fabric.install_fabric(
                    version,
                    self.minecraft_dir,
                    loader_version if loader_version else None,
                    **install_options,
                )
            else:
                self.ui_call(
                    tkinter.messagebox.showerror, "错误!", "你没有选择任何模组加载器!"
                )
                self.ui_call(self.finish_download_ui, False)
                return
        except Exception as exp:
            print(f"[ERROR] 下载失败: {exp}")
            self.ui_call(
                tkinter.messagebox.showerror,
                "下载失败",
                f"{version} 下载失败：{exp}",
            )
            self.ui_call(self.finish_download_ui, False)
            return

        self.reload_versions()
        self.ui_call(self.reload_mod_tkinter)
        self.ui_call(self.finish_download_ui, True)
        self.ui_call(
            tkinter.messagebox.showinfo,
            "下载完成",
            f"{version}（{mod_loader}）下载完成！",
        )

    def resolve_server_jar(self, server_path):
        """把配置里的路径解析成服务器核心 jar 的绝对路径, 找不到返回 None"""
        server_path = str(server_path or "").strip()
        if server_path == "":
            return None
        server_path = os.path.abspath(server_path.replace("\\", "/")).replace("\\", "/")
        if os.path.isdir(server_path):
            try:
                jars = [
                    i for i in os.listdir(server_path) if i.lower().endswith(".jar")
                ]
            except OSError:
                return None
            if not jars:
                return None
            preferred = [
                i
                for i in jars
                if any(
                    key in i.lower()
                    for key in ("server", "forge", "paper", "spigot", "fabric", "purpur")
                )
            ]
            return os.path.join(server_path, (preferred or jars)[0])
        if os.path.isfile(server_path) and server_path.lower().endswith(".jar"):
            return server_path
        return None

    def get_server_java(self):
        """服务器使用控制台版 java.exe"""
        java_path = self.get_launch_java()
        if not java_path:
            return "java"
        if os.path.basename(java_path).lower() == "javaw.exe":
            console_java = os.path.join(os.path.dirname(java_path), "java.exe")
            if os.path.isfile(console_java):
                return console_java
        return java_path

    @staticmethod
    def is_eula_line(line):
        """判断一行配置是不是有效的 eula=true"""
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            return False
        key = value = ""
        for separator in ("=", ":"):
            if separator in line:
                key, value = line.split(separator, 1)
                break
        else:
            parts = line.split(None, 1)
            if len(parts) != 2:
                return False
            key, value = parts
        # Minecraft 读取的是 eula 这个键(区分大小写), 值 true 不区分大小写
        return key.strip() == "eula" and value.strip().lower() == "true"

    def is_eula_agreed(self, directory):
        """检查目录下的 eula.txt 是否能被服务器正确读取"""
        path = os.path.join(directory, "eula.txt")
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as exp:
            print(f"[WARN] 无法读取 eula.txt: {exp}")
            return False
        # 带 BOM 或 UTF-16 的文件 Java 无法正确解析, 需要重写成纯文本
        if raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
            print("[WARN] eula.txt 带有 BOM 或为 UTF-16 编码, 服务器可能读不到")
            return False
        for encoding in ("utf-8", "gbk"):
            try:
                text = raw.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
            return any(self.is_eula_line(line) for line in text.splitlines())
        return False

    def ensure_eula(self, directory):
        """确保 eula.txt 为 eula=true, 返回是否可以继续启动服务器"""
        path = os.path.join(directory, "eula.txt")
        print(f"[INFO] 检查 EULA 文件: {path}")
        if self.is_eula_agreed(directory):
            return True
        if os.path.isfile(path):
            detail = "现有 eula.txt 里没有服务器能识别的 eula=true（可能是编码/BOM 或键名大小写问题）。"
        else:
            detail = "这个目录下还没有 eula.txt。"
        if not tkinter.messagebox.askyesno(
            "EULA",
            "启动服务器前需要同意 Minecraft EULA。\n"
            f"配置文件位置: {path}\n"
            f"{detail}\n"
            "是否自动写入 eula=true 并继续启动?",
        ):
            return False
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("eula=true\n")
        except OSError as exp:
            tkinter.messagebox.showerror("错误", f"无法写入 eula.txt:{exp}")
            return False
        print(f"[INFO] 已写入 EULA: {path}")
        return True

    def run_server(self):
        self.selected_server = self.server_listbox.curselection()
        if self.selected_server == ():
            tkinter.messagebox.showerror("错误!", "你没有选择服务器!")
            return
        index = self.selected_server[0]
        if index >= len(self.ServerPath):
            tkinter.messagebox.showerror("错误!", "找不到这个服务器的位置!")
            return
        server_jar = self.resolve_server_jar(self.ServerPath[index])
        if server_jar is None:
            answer = tkinter.messagebox.askyesno(
                "错误!",
                "找不到服务器核心文件!\n"
                f"当前记录的位置是: {self.ServerPath[index]!r}\n"
                "是否现在选择服务器核心(.jar 文件)?",
            )
            if answer:
                chosen = tkinter.filedialog.askopenfilename(
                    title="选择服务器核心文件", filetypes=[("jar文件", "*.jar")]
                )
                if chosen:
                    self.ServerPath[index] = os.path.abspath(chosen).replace(
                        "\\", "/"
                    )
                    self.save_all()
                    self.change_server()
                    return self.run_server()
            return
        working_dir = os.path.dirname(server_jar)
        if not os.path.isdir(working_dir):
            tkinter.messagebox.showerror("错误!", "服务器位置不存在!")
            return
        print(f"[INFO] 服务器目录: {working_dir}")
        if not self.ensure_eula(working_dir):
            return
        java_exe = self.get_server_java()
        memory_args = ["-Xms1024M", "-Xmx4096M"]

        # OpenP2P 联机功能暂时停用, 需要恢复时取消下面整段注释
        # if self.Enable_Start_OpenP2P_var.get() == 1:
        #     node = (
        #         self.ServerList[index]
        #         if index < len(self.ServerList)
        #         else str(index)
        #     )
        #
        #     def run_openp2p():
        #         os.system(
        #             f"./PML/openp2p.exe -d -node {node} -token {self.Token}"
        #         )
        #
        #     if not self.Token:
        #         webbrowser.open("https://console.openp2p.cn")
        #         self.Token = pymsgbox.prompt(
        #             "在打开的网站中注册或登录账号(如果已经有的话)\n复制你的Token并粘贴到这个框里\n复制完成后点击确定以继续",
        #             "Pixel Minecraft Launcher|获取Token",
        #         )
        #         self.save_all()
        #     t3 = threading.Thread(target=run_openp2p, daemon=True)
        #     t3.start()

        def runs():
            try:
                subprocess.call(
                    [java_exe] + memory_args + ["-jar", server_jar],
                    cwd=working_dir,
                )
            except FileNotFoundError:
                self.ui_call(
                    tkinter.messagebox.showerror,
                    "错误!",
                    "找不到 java, 请安装 Java 或在设置里手动添加。",
                )
            except Exception as exp:
                print(f"[ERROR] 启动服务器失败: {exp}")
                self.ui_call(
                    tkinter.messagebox.showerror, "错误!", f"启动服务器失败:{exp}"
                )

        t2 = threading.Thread(target=runs, daemon=True)
        t2.start()

    def load_log(self):
        logpath = os.path.join(self.sever_path, "server.properties")
        self.ServerLog.delete(1.0, tk.END)
        try:
            with open(logpath, encoding="utf-8", errors="replace") as f:
                self.ServerLog.insert(tk.END, f.read())
        except FileNotFoundError:
            self.ServerLog.insert(tk.END, "还没有服务器配置文件!")
        except OSError as exp:
            self.ServerLog.insert(tk.END, f"无法读取服务器配置文件:{exp}")

    def delete_server_settings(self):
        animation.MoveTkWidget(
            self.Menu_Butt_Server,
            (-50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Add_Server, (-50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.Delete_Server,
            (-50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.server_listbox,
            (0, -500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.ServerDescription,
            (1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        self.create_main()

    def change_server(self, *args):
        selection = self.server_listbox.curselection()
        if selection == () or selection[0] >= len(self.ServerPath):
            return
        server_path = self.ServerPath[selection[0]]
        server_jar = self.resolve_server_jar(server_path)
        if server_jar is not None:
            self.sever_path = os.path.dirname(server_jar)
            self.ServerPath_Label.config(text=f"服务器核心位置:{server_jar}")
        else:
            self.sever_path = os.path.abspath(
                os.path.dirname(str(server_path)) or "."
            )
            self.ServerPath_Label.config(
                text=f"服务器核心位置:无效({server_path!r})"
            )
        self.load_log()

    def save_prop(self, *args):
        try:
            logpath = os.path.join(self.sever_path, "server.properties")
            with open(logpath, "w", encoding="utf-8") as f:
                f.write(self.ServerLog.get(1.0, tk.END))
            tkinter.messagebox.showinfo("成功", "已保存配置文件修改")
            self.load_log()
        except Exception as exp:
            print(f"无法完成操作:{exp}")

    def create_server_page(self):
        animation.MoveTkWidget(
            self.Menu_Butt_Server,
            (50, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.Add_Server, (50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.Delete_Server, (50, 0), 500, fps=60, controller=animation.smooth
        ).start()
        animation.MoveTkWidget(
            self.server_listbox,
            (0, 500),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()
        animation.MoveTkWidget(
            self.ServerDescription,
            (-1000, 0),
            500,
            fps=60,
            controller=animation.smooth,
        ).start()

    def from_menu_to_server_page(self):
        self.set_current_page("server")
        self.delete_main()
        self.create_server_page()
        # 列表控件是复用的, 每次进入页面都要先清空, 否则会重复插入
        self.server_listbox.delete(0, tk.END)
        for i in self.ServerList:
            if i != "" and not i.isspace():
                self.server_listbox.insert(tk.END, i)

    def get_forge_versions(self, version: str):
        """返回该 Minecraft 版本的 Forge 版本列表(新版本在前, 去掉 Minecraft 版本前缀)"""
        output = []
        try:
            all_forge_versions = mll.forge.list_forge_versions()
        except Exception as exp:
            print(f"[WARN] 无法从官方源获取 Forge 版本列表: {type(exp).__name__}")
            all_forge_versions = self.fetch_forge_versions_from_mirror(version)
            if all_forge_versions is None:
                all_forge_versions = []
        prefix = f"{version}-"
        for i in all_forge_versions:
            if i.startswith(prefix):
                short_version = i[len(prefix) :]
                if short_version not in output:
                    output.append(short_version)
        output.sort(key=forge_version_key, reverse=True)
        return output

    def fetch_forge_versions_from_mirror(self, version: str):
        """从 BMCLAPI 镜像获取某个 Minecraft 版本的 Forge 版本, 网络失败返回 None"""
        try:
            url = BMCLAPI_FORGE_URL.format(version=version)
            with urllib.request.urlopen(url, timeout=15) as response:
                data = json.load(response)
            versions = []
            for item in data:
                try:
                    versions.append(f"{version}-{item['version']}")
                except (KeyError, TypeError):
                    continue
            return versions
        except Exception as exp:
            print(f"[ERROR] 镜像也无法获取 Forge 版本列表: {type(exp).__name__}")
            return None

    def fabric_supported_by_mirror(self, version: str):
        """通过镜像判断 Fabric 是否支持该版本, 网络失败返回 None"""
        try:
            with urllib.request.urlopen(BMCLAPI_FABRIC_GAME_URL, timeout=15) as response:
                data = json.load(response)
            return any(item.get("version") == version for item in data)
        except Exception as exp:
            print(f"[ERROR] 镜像检查 Fabric 支持失败: {type(exp).__name__}")
            return None

    def get_forge_version_id(self, selected_version=None, minecraft_version=None):
        """返回要安装的完整 Forge 版本号(形如 1.20.1-47.2.0)"""
        minecraft_version = (
            self.download_version_to if minecraft_version is None else minecraft_version
        )
        if selected_version is None:
            selected_version = self.ModLoaderVersion.get()
        selected_version = (selected_version or "").strip()
        if selected_version in ("", "最新版本"):
            forge_versions = self.get_forge_versions(minecraft_version)
            if forge_versions:
                return f"{minecraft_version}-{forge_versions[0]}"
            try:
                return mll.forge.find_forge_version(minecraft_version)
            except Exception as exp:
                print(f"[ERROR] 无法获取 Forge 版本: {exp}")
                return None
        if selected_version.startswith(f"{minecraft_version}-"):
            return selected_version
        return f"{minecraft_version}-{selected_version}"

    def get_fabric_versions(self, version: str):
        """返回可用的 Fabric 加载器版本列表(新版本在前)"""
        try:
            all_fabric_versions = mll.fabric.get_all_loader_versions()
        except Exception as exp:
            print(f"[WARN] 无法从官方源获取 Fabric 版本列表: {exp}")
            try:
                with urllib.request.urlopen(
                    BMCLAPI_FABRIC_LOADER_URL, timeout=15
                ) as response:
                    all_fabric_versions = json.load(response)
            except Exception as mirror_exp:
                print(f"[ERROR] 镜像也无法获取 Fabric 版本列表: {mirror_exp}")
                return []
        output = []
        for i in all_fabric_versions:
            try:
                fabric_version = i["version"]
            except (KeyError, TypeError):
                continue
            if fabric_version not in output:
                output.append(fabric_version)
        return output

    def load_mod_loader_version(self, loader=_NOT_GIVEN, version=_NOT_GIVEN):
        """后台获取模组加载器版本列表(参数在界面线程中读取后传入)"""
        if loader is _NOT_GIVEN:
            loader = self.ModLoader.get()
        if version is _NOT_GIVEN:
            version = self.download_version_to
        values = []
        if version and loader in ("Forge", "Fabric"):
            self.ui_call(self.set_mod_loader_version_hint, "正在获取版本列表...")
            try:
                if loader == "Forge":
                    values = self.get_forge_versions(version)
                else:
                    values = self.get_fabric_versions(version)
            except Exception as exp:
                print(f"[ERROR] 加载模组加载器版本失败: {exp}")
                values = []
        self.ui_call(self.apply_mod_loader_versions, values, loader)

    def set_mod_loader_version_hint(self, message):
        """在版本下拉框中显示提示文字"""
        self.ModLoaderVersionOption.config(values=[message])
        self.ModLoaderVersion.set(message)

    def apply_mod_loader_versions(self, values, loader):
        if not values:
            if loader in ("Forge", "Fabric"):
                # 网络获取失败时仍然保留一个可用的默认选项, 也可以手动输入版本
                self.ModLoaderVersionOption.config(values=["最新版本"])
                self.ModLoaderVersion.set("最新版本")
            else:
                self.ModLoaderVersionOption.config(values=[])
                self.ModLoaderVersion.set("")
            return
        self.ModLoaderVersionOption.config(values=values)
        current = (self.ModLoaderVersion.get() or "").strip()
        if current not in values:
            self.ModLoaderVersion.set(values[0])

    def get_mod_loader_version_theard(self, *args):
        loader = self.ModLoader.get()
        version = self.download_version_to
        if not version:
            tkinter.messagebox.showerror("错误!", "请先选择一个Minecraft版本!")
            return
        threading.Thread(
            target=self.load_mod_loader_version,
            args=(loader, version),
            daemon=True,
        ).start()

    def from_menu_to_download_page(self):
        self.create_download()
        self.delete_main()
        self.download_page_open = True
        self.set_current_page("download")

        def gtv():
            versionlist = self.get_version_list()
            self.ui_call(self.reload_version_listbox, versionlist)

        threading.Thread(target=gtv, daemon=True).start()

    def reload_version_listbox(self, versionlist):
        self.version_listbox.delete(0, tk.END)
        if not versionlist:
            self.version_listbox.insert(tk.END, "网络不畅，请稍后重试。")
        for i in versionlist:
            self.version_listbox.insert(tk.END, i["id"])
        self.version_listbox.bind("<<ListboxSelect>>", self.check_support)


MinecraftLauncher()
