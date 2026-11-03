# 把一款 Switch 游戏移植到 iOS：标准工作流

这份文档是从 **SD GUNDAM G GENERATION CROSS RAYS**（SDK 9.4.1，CRIWARE + 自研引擎）的实战中提炼出来的。
它描述的是 [nxnative](https://github.com/seedds/nxnative) 那条路线的完整流程：**原生执行**，不是模拟器。

文中所有 "Cross Rays" 的具体数字都是**真实验证过的基准**，来自
[G1n-maker/crossrays-mobile](https://github.com/G1n-maker/crossrays-mobile)——那个项目从零到双端可玩用了约 16 小时。
它们留在这里是为了对照：当新游戏的某个数字和这些基准差很远时，那就是要小心的地方。

> 前提认知：游戏自己的 ARM64 代码直接在 Apple 芯片上跑，只有 Apple 内核跑不了的指令被重写
> （`svc`、`mrs tpidr*`、`x18`、独占窗口、系统寄存器）；Host 顶替 Horizon 系统服务；NVN 图形 API 重建在 Metal 上。

---

## 目录

0. [Switch 2 游戏的额外一步](#0-switch-2-游戏的额外一步)
1. [总览：五个阶段](#1-总览五个阶段)
2. [阶段 0：可行性判断](#2-阶段-0可行性判断)
3. [阶段 1：Survey](#3-阶段-1survey)
4. [阶段 2：提取与 profile](#4-阶段-2提取与-profile)
5. [阶段 3：Bring-up 循环](#5-阶段-3bring-up-循环重点)
6. [阶段 4：打包与设备安装](#6-阶段-4打包与设备安装)
7. [阶段 5：验证清单](#7-阶段-5验证清单)
8. [诊断方法手册](#8-诊断方法手册)
9. [实战中的通用修复](#9-实战中的通用修复)
10. [环境搭建（从零）](#10-环境搭建从零)
11. [常见陷阱](#11-常见陷阱)

---

## 0. Switch 2 游戏的额外一步

Switch 2 的游戏（SDK 20 以上、NPDM 的 program ID 以 `0x04` 开头）多了一个**可能致命**的前置问题：

**游戏是否依赖 DLSS / CUDA？**

```bash
# main 链接了哪些模块：找动态段附近的 .nss 字符串
strings -a exefs/main | grep -o '[a-z]*\.nss' | sort -u
# → dlss.nss | cuda.nss | movie.nss | nnSdk.nss     ← 有 dlss 就要查
```

Apple 芯片**没有 Tensor Core、没有 CUDA**，也没有能保持帧率的软件 DLSS。所以：

| 情况 | 判断 |
|---|---|
| `main` 直接调 `ngxEvaluate` 等 NGX API | ❌ **不可移植**，除非有非 DLSS 分支 |
| `main` 只在配置字符串里提到 DLSS，实际调用在 `gfx` 里且可关闭 | ⚠️ 有希望，要确认画质设置能否钉到"关" |
| 完全不引用 `ngx`/`NGX` | ✅ 可能根本没用 |

**最快的验证手段：随游戏附带的 PC 模拟器**（eden / Ryujinx 等）。
它跑在没有 Tensor Core 的 PC 上——如果游戏在那上面能出画面，就证明**存在一条不依赖 DLSS 的路径**。
先读它的配置和日志，比反编译快得多。

**另一个常见障碍**：Switch 2 的 shader 可能是编译好的 SASS 而非可重编译的 NVN 中间码。
如果 `Shaders/` 里全是不可识别的二进制，且 `main` 里找不到 GLSLC 输出，就先确认这一点再投入。

---

## 1. 总览：五个阶段

```
阶段 0  可行性判断          30 分钟    失败就止损
   ↓
阶段 1  Survey              5 分钟     产出 survey.md
   ↓
阶段 2  提取 + profile      15 分钟    产出可运行的 Mac host
   ↓
阶段 3  Bring-up 循环       ★ 主要工作量：几天到几周
   ↓
阶段 4  打包 + 装机         30 分钟
   ↓
阶段 5  验证清单            1 小时
```

**工时分布的现实预期**：阶段 3 占 90% 以上的时间。前两个阶段是流水线，阶段 3 是真正的移植工作。

---

## 2. 阶段 0：可行性判断

**目标**：在投入大量时间前，判断这个游戏值不值得做。

### 快速判断表（30 分钟内能做完）

拿到一个新游戏，按顺序问这五个问题。**任何一个答案是"红线"就止损。**

| # | 问题 | 怎么查 | 绿灯 | 黄灯 | 红线 |
|---|---|---|---|---|---|
| 1 | **是 64 位 ARM 吗？** | `main.npdm` 的 META+0xc bit 0 | 置位 | — | 清零（32 位，无解） |
| 2 | **SDK 版本？** | `sdk` 里的 `NintendoSDK_nnSdk-<ver>` 字符串 | 6–16 | 17–20 | <6 或 >22 |
| 3 | **图形 API？** | `main` 导入表 | NVN | Vulkan / OpenGL | 三者皆无 |
| 4 | **有同构先例吗？** | 引擎标记 + 中间件 | 同引擎或同中间件已跑通 | 有中间件先例但引擎不同 | 完全自研且无先例 |
| 5 | **shader 在哪？** | RomFS 有无 `BNSH`/`BAHS`/`UnityFS`，或 `main` 里的 `0x19866891` | 静态文件或内嵌 main | 在压缩容器里 | 运行时才生成 |

**五问全绿 → 预计 1–3 天**（Cross Rays 属于此列：SDK 9.4.1 / NVN / 与 13 Sentinels 同构 / GLSLC 内嵌 main）。

**一两个黄灯 → 1–2 周。**

**任何红线 → 先解决那一条，否则不要开始。**

### 为什么第 4 问权重最高

Cross Rays 的 shader 环节**一次通过**（1090 个 GLSLC，SPIR-V 和 MSL 各 639/639 零失败），
不是因为这个游戏简单，而是因为 **13 Sentinels: Aegis Rim 已经把这条路径踩平了**。

两者都是：SDK 9–11 + NVN + CRIWARE + **GLSLC 输出内嵌在 `main` 的只读段**。

**移植前花 30 分钟在 `nxnative/dm/games/` 里找同构游戏，能省掉几天试错。**

### 详细检查项

```bash
# 从 XCI/NSP 头直接读（无需 keys）
xxd -l 512 "game.xci" | head -20     # 0x100 处应是 "HEAD"
```

| 检查项 | 方法 | 红线 |
|---|---|---|
| **64 位 ARM** | `main.npdm` 的 META+0xc bit 0 | 32 位（Pikmin 3 Deluxe）**无解**，Apple 芯片跑不了 |
| **SDK 版本** | `sdk` 里的字符串 `NintendoSDK_nnSdk-<ver>` | 已验证区间 **6–20**；<6 或 >22 要谨慎 |
| **图形 API** | `main` 的导入表：`nvnBootstrapLoader` / `vkCreateInstance` / `eglGetProcAddress` | 三者皆无 = 非标准渲染，先查清 |
| **引擎** | 字符串标记：`UnityEngine`、`global-metadata.dat`、`++UE4`、`sead`/`agl` | 有先例的引擎风险最低 |
| **shader 位置** | RomFS 里有无 `BNSH`/`BAHS`/`UnityFS`，或 `main` 里的 GLSLC magic `0x19866891` | 运行时才编译 shader 的（需 capture）最麻烦 |
| **DLC** | 卡片分区或 NSP 是否含多个 title | 多 DLC 要额外验证 `nn::aoc` |

### 风险分级

| 等级 | 特征 | 预期工时 |
|---|---|---|
| **低** | SDK 8–16 + NVN + 有先例引擎（Unity/UE/EPD）+ shader 静态内嵌 | 1–3 天 |
| **中** | 自研引擎但有 CRIWARE/Wwise 等中间件先例 + shader 可静态提取 | 1–2 周 |
| **高** | 运行时生成 shader / 32 位 / 无先例中间件 / 大量自定义 GPU 路径 | 数周，且可能失败 |

**Cross Rays 属于"中"**：自研引擎，但结构（CRIWARE + GLSLC 内嵌 main + NVN）与已跑通的 13 Sentinels 同构。

---

## 3. 阶段 1：Survey

**目标**：拿到这个游戏的全貌，产出一份可对照的报告。

```bash
./run_nxnative.sh <game_folder> -k keys/prod.keys --survey-only
```

产出：`<game_folder>/<title_id>_survey/survey.md`

### 报告里要看什么

| 字段 | 意义 | 判断 |
|---|---|---|
| `display version` | 游戏版本 | 记下来，profile 要用 |
| 模块表 | main / sdk / subsdk0 / rtld + build ID | 每个模块的 build ID 是 profile 的 key |
| **指令普查** | `svc` / `x18` / `mrs tpidr*` 计数 | `main` 里 **0 个 svc** 最理想（系统调用全在 sdk） |
| **导入 vs hook** | host 有 1040 个 hook，多少能在这个游戏的 `sdk` 里找到 | >60% 可接受；<40% 要评估缺口 |
| RomFS | 文件数、总大小、top-level 分布 | 决定 `--romfs bundle` 还是 `separate` |
| **shader 容器** | 有无 BNSH/BAHS/UnityFS，或 GLSLC magic 数 | 决定 shader 拆分策略 |

### Cross Rays 的实测值（作为基准）

```
SDK 9_4_1 | NVN | CRIWARE
main:  1994881 条指令, x18=2019, svc=0        ← 极干净
sdk:   1378343 条指令, x18=11300, svc=61
RomFS: 22100 文件, 18.91 GB
shader: main 里 1090 个 GLSLC 输出 (magic 0x19866891)
导入: 658 个, host hook 覆盖 776/1040 (75%)
```

---

## 4. 阶段 2：提取与 profile

```bash
./run_nxnative.sh <game_folder> -k keys/prod.keys --platform mac
```

一条命令走完：**提取 → 重写 → shader 拆分 → 编译 shader → 构建 Mac host**。

### 4.1 自动生成的 provisional profile

没有现成 profile 时，脚本会生成 `<build>/profile/<title_id>/game.tsv`。它是猜的，**必须人工核对**。

关键字段：

```tsv
title_id        010055700CEA8000
program_id      010055700CEA8000
modules         main subsdk0 sdk          # 加载顺序，main → subsdk* → sdk
romfs_marker    Data.bin                  # 用来验证数据完整性的文件
mem_reserve     0x100000000               # 4 GB guest 地址空间
mem_alias       0x10000000                # 256 MB alias 区
mem_stack       0x10000000                # 256 MB 栈区
app_pool        0xCD500000                # 应用内存池（4 GB Switch 标准值）
mem_used        0x8000000                 # ★ host 报告给游戏的"已用内存"
sys_resource    0x0                       # NPDM 声明的系统资源
```

### 4.2 `mem_used` 是最容易踩的坑

游戏通常这样要内存：

```c
heap_size = application_pool - used_memory;   // 用 QueryMemoryInfo 拿
SetHeapSize(heap_size);
AllocateMemoryBlock(&block, heap_size);       // 整个 heap 块
```

`used_memory` 是 host 报的。默认 64 MB，但**模块本身的大小也算在内**。

如果 `mem_used` < 模块实际大小 + 余量，`SetHeapSize` 会失败，`AllocateMemoryBlock` 返回 0，游戏不检查就写入 null → **启动即崩**。

**判断方法**：日志里看
```
[mem] SetHeapSize 0xc9400000 + modules 0x7800000 > app pool 0xcd500000
```
`heap + modules > pool` 就是不够。设 `mem_used` 为 `modules` 大小 + 余量（Cross Rays: 120 MB → 设 128 MB）。

### 4.3 shader 拆分验证

```bash
# 手动跑一次，看通过率
DM_GAME=<id> .venv/bin/python nxnative/dm/gfx/tools/shader_split.py \
  <romfs.img> <exefs/main> <out_pkg> <map.tsv> <facts.tsv> <pairs.tsv> <pso_pairs.tsv>
```

**通过率标准**：

| 结果 | 判断 |
|---|---|
| magic 数 == 接受数 | ✅ 完美（Cross Rays: 1090/1090） |
| 差几个 | 通常可接受，记录在案 |
| 差很多 | shader 容器结构不标准，需要单独分析 |

### 4.4 翻译链验证（在依赖 Xcode 之前）

```bash
# 1. SPIR-V 翻译（最快，能筛掉大部分问题）
#    手写 job JSON，调 dmsh_xlate
#    → 期望 100% 成功

# 2. SPIRV-Cross → MSL
#    注意必须带 --msl-argument-buffers --msl-texture-buffer-native --msl-pad-fragment-output
#    → 期望 100% 成功

# 3. Metal 编译（需要 Xcode + MetalToolchain）
DM_GAME=<id> .venv/bin/python nxnative/dm/gfx/tools/own_compilers.py <pkg> <out>
```

**Cross Rays 的实测**：
```
1090 GLSLC → 639 唯一 (127 vs + 512 ps)
           → SPIR-V: 639 ok / 0 failed  (1.3 s)
           → MSL:    639 ok / 0 failed  (2.1 s)
           → metallib (mac): 1273 编译, 0 失败
           → metallib (ios): 1272 编译, 0 失败
```

---

## 5. 阶段 3：Bring-up 循环（重点）

**这是移植工作的主体。** 每次循环：

```
启动 → 崩/黑/卡 → 读日志 → 定位 → 修 → 重试
```

### 5.1 启动方式（关键：进程不能被回收）

```python
# /tmp/run_once.py —— 用 Python 的 start_new_session 脱离会话
import os, subprocess
env = dict(os.environ)
env.update({'DM_ROOT': '<build>', 'DM_ROMFS': '<romfs.img>', ...,
            'DM_WINDOW': '1', 'DM_AUDIO': '1'})
with open('<log>','wb') as log:
    p = subprocess.Popen(['<build>/tools/dmhost', '<build>/patched_v<ver>'],
                         env=env, stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    try: p.wait(timeout=90)
    except subprocess.TimeoutExpired: p.terminate(); p.wait(timeout=5)
```

> `nohup ... &` 会在父 shell 退出时被 SIGKILL。必须用 `start_new_session`。

### 5.2 三类崩溃的诊断路径

#### A. 启动即崩（在 `nninitStartup` 附近）

**症状**：`[dm] >>> nninitStartup` 之后 SIGSEGV

**诊断**：
```bash
# 1. 反汇编崩溃点
objdump -d --start-address=$((pc-0x40)) --stop-address=$((pc+0x20)) /tmp/main.elf

# 2. 看是否写/读 null
#    str x10, [x8]  with x8=0  → 某个分配返回值没检查
```

**常见根因**：内存不足（`mem_used` 太小）、初始化顺序。

#### B. 卡在 `nnMain` 早期（系统服务）

**症状**：进了 `nnMain`，在 `sdk+0x...` 崩

**诊断**：
```bash
# 1. 反汇编 sdk
objdump -d --start-address=$((pc-0x30)) --stop-address=$((pc+0x10)) /tmp/sdk.elf

# 2. 看指令类型
#    ldr w8, [x0, #0x24]  → x0 是个对象指针，值是垃圾
#    → 说明调用者传了个无效指针进来

# 3. 回溯调用链，找到 main 侧的调用点
#    看它传给 sdk 的参数是什么

# 4. 解析 main 的 GOT 槽，确认调用的是哪个导入函数
```

**GOT 槽解析脚本**（`readelf -d` 拿偏移）：

```python
import struct, sys
sys.path.insert(0,'nxnative/dm/tools'); import nso
img = nso.read('<exefs>/main').image
RELA, RELASZ = 0x79d058, 0x135900        # 从 readelf -d 拿
JMPREL, PLTRELSZ = 0x8d2958, 0x34e0
SYMTAB, STRTAB = 0x8d74c8, 0x8db548
def symname(sym):
    st = struct.unpack_from('<I', img, SYMTAB+sym*24)[0]
    e = img.find(b'\0', STRTAB+st)
    return img[STRTAB+st:e].decode(errors='replace')
for name, off, sz in (('JMPREL',JMPREL,PLTRELSZ),('RELA',RELA,RELASZ)):
    for k in range(sz//24):
        r_off, r_info, r_add = struct.unpack_from('<QQq', img, off+k*24)
        if r_off == 0x156a460:                       # 目标 GOT 槽
            print(f'{r_off:#x} <- {symname(r_info>>32)}')
```

**Cross Rays 靠这个找到根因**：
```
main 导入 nn::fs::ReadFile(FileHandle, s64, void*, size_t, const ReadOption&)
host 只 hook 了 ReadFile(size_t*, FileHandle, ...)   ← 少了一个重载
→ 调用落到 sdk 自己的实现，它把 handle 当 FileAccessor* 解引用 → SIGSEGV
```

**修法**：在 `dm/host/hle_fs.c` 补 `HLE_FORCE`。

#### C. 能跑但画面不对

**这是最难的一类。** 症状分类：

| 症状 | 常见根因 |
|---|---|
| **全黑，但有文字** | 纹理没上传（见下） |
| 全黑，什么都没有 | 渲染目标没建 / 没 present |
| 花屏 / 颜色错 | 格式映射错（RGB/BGR 反了） |
| 贴图错位 | block-linear 反交错错 |
| 特定物体不显示 | shader 变体缺失 / 顶点格式不匹配 |
| 闪一下就崩 | 内存耗尽 / pipeline 编译失败 |

**"全黑但有文字"的诊断流程**（Cross Rays 实战）：

```bash
# 1. 数纹理创建：有多少个？
grep -oE "TextureInitialize=[0-9]+" log.txt | tail -1
#    Cross Rays: 74（正常应几百上千）

# 2. 看有没有上传
grep "packaged textures" log.txt | tail -1
#    Cross Rays: "first uploads 0" ← 一个都没上传

# 3. 加诊断：每个纹理创建时，检查它绑定的内存有没有非零数据
#    在 host 的 tex_init_fill() 入口加：
MLOG("[dbgtex] ser=%llu %ux%u fmt=%#x tflags=%#x pflags=%#x flushed=%d any=%d nz=%llu",
     serial, w, h, format, tflags, pool_flags, flushed, mem_any(mem,size), nonzero_count);

# 4. 结果解读
#    tflags=0x8  →  NVN_TEXTURE_FLAGS_COMPRESSIBLE
#    any=1       →  内存里有数据
#    fill=0      →  ★ 有数据但没上传 = 找到了
```

**Cross Rays 的根因**：
```c
// dm/gfx/nvn/nvn_mtl.m tex_init_fill()
if (t->d.samples > 1 || (t->d.flags & NVN_TEXTURE_FLAGS_COMPRESSIBLE) || ...) return 0;
//                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ Cross Rays 给所有纹理都设了这个
```

`COMPRESSIBLE`（0x8）是 **Switch 的内存压缩提示**，不是数据格式。Host 从不实现池压缩，所以这个条件对 host 是多余的，但它挡住了所有纹理的上传。

**修法**：去掉这个排除条件（保留真正需要的：multisampled、depth 格式）。

### 5.3 加诊断日志的正确方式

**不要**用 `printf` 刷屏。用 env 变量控制的探针：

```c
static int dbg = -1;
if (dbg < 0) { const char *e = getenv("DM_DBGTEX"); dbg = e && atoi(e); }
if (dbg) MLOG("[dbgtex] ...");
```

好处：
- 平时零开销
- 需要时 `DM_DBGTEX=1` 打开
- 不污染正常日志

**Cross Rays 用过的探针**：

| Env | 位置 | 看什么 |
|---|---|---|
| `DM_SVC=1` | `hle_svc.c` | 每个系统调用、SetHeapSize 的请求 |
| `DM_DBGTEX=1` | `nvn_mtl.m` `tex_init_fill` | 每个纹理的参数 + 内存内容 |
| `DM_DBGFS=1` | `hle_fs.c` | 每次 OpenFile/ReadFile 的路径和大小 |
| `DM_NVN_FLUSH_FILL=0` | `nvn_mtl.m` | 关掉 storage 填充（对比测试） |

### 5.4 对照已跑通的游戏

**这是最省时间的做法。** 同 SDK / 同中间件的游戏是最好的参考。

| 你要查的 | 参考游戏 |
|---|---|
| SDK 9 的内存布局 | Hyrule Warriors: Age of Calamity (9.6.0) |
| CRIWARE + GLSLC 内嵌 main | 13 Sentinels: Aegis Rim (11.4.3) |
| 纹理 CPU 写入上传 | The Great Ace Attorney Chronicles |
| 大 bss 处理 | Metroid Dread |
| Unreal 引擎 | Octopath Traveler II (4.27) / DRAGON QUEST VII |

**查法**：
```bash
cd nxnative/dm/games/<参考游戏>/ && cat README.md
# 尤其是 "What it needs" 表格和 "Resolved" 段落
```

---

## 6. 阶段 4：打包与设备安装

### 6.1 决定 RomFS 打包方式

| 方式 | IPA 大小 | 侧载 | 适用 |
|---|---|---|---|
| `--romfs bundle`（默认） | 游戏大小 + 200 MB | 小游戏可以 | < 4 GB |
| **`--romfs separate`** | ~150–300 MB | ✅ 大游戏必须 | ≥ 4 GB |

**Cross Rays**：18.91 GB → 必须 separate。

```bash
./run_nxnative.sh <game_folder> -k keys/prod.keys --romfs separate
```

### 6.2 有开发者账号：直接签名装机

```bash
# 1. 生成 Xcode 工程（保留提取的文件）
./run_nxnative.sh <game_folder> -k keys/prod.keys --prepare-xcode --team-id <TEAM_ID>

# 2. ★ 清 derived data —— 否则可能打进旧代码（本次实战踩过两次）
rm -rf <build>/xcode-derived-data

# 3. 归档（关键：DM_COPY_ROMFS=NO 把游戏数据排除在外，保留 shader）
cd <build>/xcode
DM_COPY_ROMFS=NO xcodebuild -project DmIOS.xcodeproj \
  -scheme "<game name> (<title_id>)" -configuration Release \
  -destination "generic/platform=iOS" \
  -archivePath /tmp/out.xcarchive archive \
  DEVELOPMENT_TEAM=<TEAM_ID> CODE_SIGN_STYLE=Automatic \
  -allowProvisioningUpdates

# 4. 装机（配对过之后无线也行）
xcrun devicectl device install app --device <UDID> \
  /tmp/out.xcarchive/Products/Applications/DmIOS.app
```

**⚠️ 坑 1：`DM_COPY_GAME_RESOURCES=NO` 会把 shader 库也排除掉**
用 `DM_COPY_ROMFS=NO`（只排除游戏数据），不要用 `DM_COPY_GAME_RESOURCES=NO`。

**⚠️ 坑 2：改了 host 代码后 archive 可能打进旧二进制**
验证方法：
```bash
strings <app>/DmIOS | grep "<你新加的日志字符串>"
# 返回 1 = 新代码进去了；0 = 还是旧的，清 derived data 重来
```

**验证签名和权限**：
```bash
codesign -d --entitlements - <app> 2>&1 | grep -E "memory|team"
# 必须有：com.apple.developer.kernel.increased-memory-limit = true
```

### 6.3 推游戏数据（大文件必读）

**`devicectl copy to` 在 >10 GB 时会静默截断**，导致镜像校验失败（`errno=22`）。

**可靠做法：Finder**

1. Finder → 左侧选 iPhone → **文件** 标签
2. 展开 app，进 `Documents`
3. 把 `RomFS.img` 拖进去
4. 等进度条走完

**验证**：
```bash
xcrun devicectl device info files --device <UDID> \
  --domain-type appDataContainer --domain-identifier <bundle_id> | grep -i romfs
# 大小必须精确等于本地文件（不是 "18.91 GB" 这种约数）
```

### 6.4 免费账号 vs 开发者账号

| | 免费 | 付费开发者 |
|---|---|---|
| 证书有效期 | 7 天 | 1 年 |
| **Increased Memory Limit** | ❌ | ✅ |
| 可玩游戏规模 | 小 | 大 |

**需要 3 GB+ heap 的游戏，免费账号基本跑不起来。**

---

## 7. 阶段 5：验证清单

```
基础
□ 标题画面完整（无黑块、文字正常）
□ 能进入主菜单
□ 菜单导航正常（按键映射对）

游戏性
□ 进入实际游戏场景
□ 3D 模型渲染正确（不是黑块/白模）
□ 贴图完整（不是纯色）
□ 特效正常（粒子、光效）
□ 战斗/交互可操作
□ 存档、读档

音频
□ BGM 播放
□ 音效
□ 语音（如有）

高级
□ DLC 内容可访问
□ 视频播放（开场动画）
□ 60 秒无崩溃
□ 5 分钟内存无持续增长

iOS 特有
□ 触屏操作可用
□ 内存不触发 iOS 看门狗
□ 后台切换不崩
```

---

## 8. 诊断方法手册

### 8.1 日志里该看什么

| 日志行 | 含义 | 正常值 |
|---|---|---|
| `[RED] ...` | 明确的问题标记 | **0 条** |
| `>>> nnMain` | 进入了游戏主函数 | 必须有 |
| `Metal device <name>` | 图形设备创建成功 | 必须有 |
| `packaged textures: first uploads N` | 纹理上传数 | **>0** |
| `on-screen: N frames, dropped 0` | 实际呈现帧数 | dropped 应为 0 |
| `footprint N MiB` | 内存占用 | 应稳定 |
| `frame time p50 16.6x ms` | 帧时间 | 60 fps = 16.67 |

### 8.2 反汇编速查

```bash
# NSO → ELF
.venv/bin/python nxnative/dm/tools/nso2elf.py <exefs>/main /tmp/main.elf

# 反汇编一个区域
objdump -d --start-address=0x5cc4c0 --stop-address=0x5cc520 /tmp/main.elf

# 常见指令含义
#   adrp x16, 0x156a000     → 页基址
#   ldr  x17, [x16, #0x6d8] → 读 GOT 槽（导入函数指针）
#   br   x17                → 调用导入
#   str  xN, [xM]           → 写内存（xM=0 就是崩溃点）
```

### 8.3 快速判断"是不是 host 的锅"

```bash
# 1. 这个导入 host 有没有 hook？
grep -o '"<mangled_name>"' nxnative/dm/host/*.c

# 2. 没有 → 大概率是它
# 3. 有 → 看实现是否完整（尤其返回值）
```

---

## 9. 本次实战的全部修复

五个修复，按发现顺序。三个是启动/画面的硬阻塞，两个是体验优化。

### 修复 1：`mem_used` 太小（配置）

**症状**
```
[mem] SetHeapSize 0xc9400000 + modules 0x7800000 > app pool 0xcd500000
[dm] CRASH sig=11 pc=main+0x5cc508  x8=0
```

**根因**：`nninitStartup` 用 `pool - used` 算 heap，`used` 报的 64 MB 小于模块实际（120 MB），`SetHeapSize` 失败 → `AllocateMemoryBlock` 返回 0 → 游戏不检查直接写 null。

**修法**：`game.tsv` 加
```tsv
mem_used	0x8000000
```

**通用性**：任何模块 > 64 MB 且用 `SetHeapSize` 的游戏都需要。参考 Age of Calamity（`0x4800000`）。

---

### 修复 2：`ReadFile` 缺一个重载（host 代码）

**症状**
```
[dm] CRASH sig=11 pc=sdk+0x62a78  x0=0x4000000000000390
     （ldr w8, [x0, #0x24] —— x0 是垃圾值）
```

**根因**：`main` 导入 `nn::fs::ReadFile(FileHandle, s64, void*, size_t, const ReadOption&)`，host 只 hook 了带 `<size_t*>` 的孪生版本。调用落到 `sdk` 自己的实现，它把 handle 当 `FileAccessor*` 解引用。而 host 的 handle 是合成的（`1<<58 | mount<<32 | index`），不是真指针。

**修法**：`dm/host/hle_fs.c`
```c
HLE_FORCE("_ZN2nn2fs8ReadFileENS0_10FileHandleElPvmRKNS0_10ReadOptionE",
          "fsp-srv → pread(2) (overload with read options and no bytes-read output)",
          Result, h_fs_ReadFileOpt2,
          uint64_t h, int64_t off, void *buf, size_t sz, const void *opt) {
    (void)opt; size_t got = 0; return h_fs_ReadFile(&got, h, off, buf, sz);
}
```

**通用性**：SDK 9 引入了这个重载。任何 SDK 9+ 且用它的游戏都会中招。

---

### 修复 3：`COMPRESSIBLE` 挡住纹理上传（host 通用 bug）★

**症状**：游戏跑 60 fps、62 draws/帧、零错误，但**全屏黑，只有文字**。

**诊断**
```
packaged textures: first uploads 0        ← 一个都没上传
TextureInitialize=74                       ← 但创建了 74 个
[dbgtex] ser=214 fmt=0x44 tflags=0x8 any=1 fill=0
                  BC3        有数据    但不上传
```

**根因**
```c
// dm/gfx/nvn/nvn_mtl.m  tex_init_fill()
if (t->d.samples > 1 || (t->d.flags & NVN_TEXTURE_FLAGS_COMPRESSIBLE) || ...) return 0;
```
```c
NVN_TEXTURE_FLAGS_COMPRESSIBLE = 0x8   // Switch 的内存压缩提示，不是数据格式
```

Cross Rays **给所有纹理都设了这个标志**。Host 从不实现池压缩，所以这个条件对 host 没有实际保护作用，却把所有纹理的上传挡掉了。

**修法**
```c
// COMPRESSIBLE 是 Switch 的内存压缩提示，不是数据格式：游戏仍然把普通纹素写进池。
// Host 从不实现池压缩，所以跳过填充只会让"给所有纹理都设这个标志"的游戏全部拿到 0 内容
// ——整屏黑，只有文字。只保留真正的排除条件（多重采样、深度格式）。
if (t->d.samples > 1 || ((int)mt.pixelFormat >= 250 && (int)mt.pixelFormat <= 262)) return 0;
```

**结果**：`fill=0` → `fill=1`，BC3 贴图成功上传，**画面完全恢复**。

**通用性**：★ **这是最有价值的一条**。任何"给所有纹理设 COMPRESSIBLE + 用 SetStorage 自己写内存"的游戏都能受益，不限于 Cross Rays。

#### COMPRESSIBLE 到底是什么

它是 Switch GPU 的一个**内存压缩开关**，和贴图格式无关。两者容易混淆：

| 概念 | 是什么 | 改变数据吗 |
|---|---|---|
| **BC3 / DXT5**（`fmt = 0x44`） | 贴图的**压缩格式** | ✅ 数据本身就是压缩块，必须解码 |
| **COMPRESSIBLE**（`0x8`） | 内存的**压缩提示** | ❌ 数据还是普通纹素 |

`COMPRESSIBLE` 只是告诉驱动"这块显存允许你压得紧一点，省内存"。游戏写进去的仍然是普通像素；
没有这个压缩硬件，直接读原始数据完全正确。

原作者加这个排除条件的理由写在注释里："their memory is meaningless without the compression tags"
（没有压缩标签，它们的内存是没有意义的）。这在**真的启用了硬件压缩**时成立——那时内存里存的是带
标签的压缩数据，当纹素读出来就是乱的。

**Cross Rays 不是这种情况。** 它给所有贴图都设了这个标志（大概是引擎的默认值），实际写的却是普通纹素。
于是：游戏写对了数据 → host 看到标志就拒绝上传 → 所有贴图都是 0 → 全屏黑，只剩文字
（文字走另一条路径，不受影响）。

去掉是安全的，因为 host **从来没有实现过**内存压缩——"内存里有压缩标签"这种情况在 host 上不可能发生，
那个排除条件没有任何保护作用，只会误伤。

打个比方：BC3 像把衣服真空压缩袋装好（**必须拆袋才能穿**，真的变了形态）；
COMPRESSIBLE 像在箱子上贴"此箱可压缩"的标签（**衣服还是原来的衣服**，只是搬运工有权决定压不压）。
原来的逻辑是"看到标签就当已经压扁了，不拆开"——结果把好好的衣服当成了压缩袋。

---

### 修复 4：全屏——黑边有两层（iOS 前端）

**症状**：手机屏幕 2622x1206（2.174:1），游戏 1920x1080（1.778:1），左右各 239 px 黑边。
改了 Metal viewport 完全没反应。

**根因**：黑边是**两层**的。

```objc
// dm/ios/Sources/front_ios.m —— 第一层：整个游戏视图被约束成 16:9
static CGRect fit_16_9(CGRect b) {
    if (w / h > 16.0 / 9.0) w = h * 16.0 / 9.0;   // 宽度被砍
    ...
}
```

所以 drawable 只有 **2144x1206**。黑边是**屏幕上的空白**，不是渲染结果。
第二层才是 Metal viewport 在 16:9 内部居中。

**只改第二层永远看不出效果——第一层已经决定了可用区域。**

**修法**：两层都要改。

```objc
// front_ios.m
static BOOL present_fill_on(void) { const char *e = getenv("DM_PRESENT_FILL"); return e && *e; }
static CGRect game_rect(CGRect b) { return present_fill_on() ? b : fit_16_9(b); }
```

```c
// nvn_mtl.m present_viewport()
static int fill = -1; if (fill < 0) {
    const char *e = getenv("DM_PRESENT_FILL"); if (!e || !*e) e = DM_GAME_PRESENT_FILL;
    fill = !e || !*e ? 0 : !strcmp(e, "crop") ? 1 : !strcmp(e, "stretch") ? 2 : 0;
}
if (fill == 2) return (MTLViewport){0, 0, dw, dh, 0, 1};        // stretch
double s = fill == 1 ? fmax(dw/cw, dh/ch) : fmin(dw/cw, dh/ch); // crop : letterbox
```

**教训**：画面尺寸问题，**先查 view/layer 层的尺寸**，再查渲染层的 viewport。
日志里看 `canvas` 的实际值就能分辨：canvas 等于屏幕尺寸 = 渲染问题；
canvas 小于屏幕 = 布局问题。

---

### 修复 5：触屏控件贴边（iOS 触控布局）

**症状**：肩键 ZL/L/ZR/R 离屏幕边缘太远，而方向键和 ABXY 位置合适。

**根因**：两类控件用了不同的安全区矩形。

```objc
- (CGRect)safe   { return UIEdgeInsetsInsetRect(self.bounds, self.safeAreaInsets); }   // 扣满
- (CGRect)corner { ... i.left *= K_CORNER_IN; ... }                                    // 只扣 50%

- (CGPoint)faceCenter { CGRect s = self.corner; ... }   // ABXY 用 corner ✅
- (CGPoint)dropCenter { CGRect s = self.safe; ... }     // 肩键用 safe ❌
```

横屏时左右 `safeAreaInsets` 约 59pt，所以肩键实际距屏幕边缘 `59 + 44` ≈ 87pt。

**修法**：`dropCenter` / `clickCenter` 改用 `corner`，并把 `K_ZL_X` 从 44 降到 30。

**教训**：iOS 的 `safeAreaInsets` 在横屏有 59pt，是很多"位置不对"的隐形原因。

---

## 10. 环境搭建（从零）

**目标**：不污染系统，全部装在项目目录。

```bash
cd <project>

# Python 3.12 + 依赖
export UV_INSTALL_DIR="$PWD/.tools/uv"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$PWD/.tools/uv:$PATH"
uv python install 3.12 && uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python lz4 "capstone>=5,<6" fonttools nsz zbic backports.zstd

# .NET SDK 10（nx_extract 和 shader 翻译器需要）
curl -sSL https://dot.net/v1/dotnet-install.sh -o .tools/dotnet-install.sh
chmod +x .tools/dotnet-install.sh
./.tools/dotnet-install.sh --channel 10.0 --install-dir "$PWD/.tools/dotnet" --no-path

# JDK 21（Ghidra 需要）
curl -sL -o .tools/jdk.tar.gz "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/aarch64/mac/OpenJDK21U-jdk_aarch64_mac_hotspot_21.0.13_9.tar.gz"
tar xzf .tools/jdk.tar.gz -C .tools

# XcodeGen（生成 iOS 工程）
curl -sL -o .tools/xcodegen.zip https://github.com/yonaskolb/XcodeGen/releases/download/2.46.0/xcodegen.zip
unzip -oq .tools/xcodegen.zip -d .tools

# zstd（shader 拆分用）
curl -sL -o .tools/zstd-src.tar.gz https://github.com/facebook/zstd/releases/download/v1.5.7/zstd-1.5.7.tar.gz
tar xzf .tools/zstd-src.tar.gz -C .tools && make -j8 -C .tools/zstd-1.5.7/programs zstd
mkdir -p .tools/bin && cp .tools/zstd-1.5.7/programs/zstd .tools/bin/

# glslang（OpenGL 游戏的 shader）
curl -sL -o .tools/glslang.zip "https://github.com/KhronosGroup/glslang/releases/download/16.6.0/glslang-16.6.0-macos-universal-release.zip"
unzip -oq .tools/glslang.zip -d .tools
```

**Xcode（必须手动，需要 Apple ID）**

```bash
# App Store 装 Xcode 27.2，然后：
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
xcodebuild -downloadComponent MetalToolchain    # ★ SDK 26+ 不再自带
xcodebuild -downloadPlatform iOS

# 验证
xcrun -sdk macosx  metal --version    # 必须匹配 dmsh_chain.lock
xcrun -sdk iphoneos metal --version
xcrun --sdk iphoneos --show-sdk-version
```

**包装脚本** `run_nxnative.sh`：

```bash
#!/bin/zsh
ROOT="$(cd "$(dirname "$0")" && pwd)"
export DOTNET_ROOT="$ROOT/.tools/dotnet"
export PATH="$ROOT/.tools/uv:$ROOT/.tools/dotnet:$ROOT/.tools/xcodegen/bin:$ROOT/.tools/glslang/bin:$ROOT/.tools/bin:$PATH"
exec "$ROOT/.venv/bin/python" "$ROOT/nxnative/scripts/build_ipa_from_nsp.py" "$@"
```

---

## 11. 常见陷阱

### 环境相关

| 陷阱 | 现象 | 解法 |
|---|---|---|
| `nohup ... &` 进程被杀 | 日志停在某处，无错误 | 用 `start_new_session` / Python 启动 |
| Xcode 只装 CommandLineTools | `xcrun -f metal` 找不到 | 必须装完整 Xcode |
| MetalToolchain 未装 | `cannot execute tool 'metal' due to missing Metal Toolchain` | `xcodebuild -downloadComponent MetalToolchain` |
| Metal 版本不匹配 lock | `translation chain tools do not match the lock file` | 装对版本，或 `--allow-other-metal` |
| `prod.keys` 有坏行 | `Unable to decrypt NCA header` | 剔掉长度异常的行（如 34 字符的 `master_kek_source_*`） |
| 沙箱限制网络 | 下载超时 | 用 `required_permissions: ["full_network"]` |

### shader_split 相关

| 陷阱 | 现象 | 解法 |
|---|---|---|
| 传目录而非 `.img` | `IsADirectoryError` in `zip_jobs` | 第一个参数传 `<ver>/RomFS.img` |
| 缺 `shader_map.tsv.conflicts.tsv` | `FileNotFoundError` | 建空占位（带表头两行） |
| 缺 `pso_manifest.tsv` | `cp: No such file` | 建空占位（带表头） |

### 打包相关

| 陷阱 | 现象 | 解法 |
|---|---|---|
| `DM_COPY_GAME_RESOURCES=NO` | app 里没有 `msl/`，运行时 `failed to load shader` | 用 `DM_COPY_ROMFS=NO` |
| `devicectl copy to` 大文件 | 镜像 `errno=22` 校验失败 | 用 Finder 拖 |
| IPA 太大无法侧载 | 安装失败 | `--romfs separate` |
| 免费账号 | 拿不到 Increased Memory Limit | 付费开发者账号 |

### 运行时相关

| 陷阱 | 现象 | 解法 |
|---|---|---|
| `mem_used` 太小 | `SetHeapSize ... > app pool`，启动崩 | 设为模块大小 + 余量 |
| 漏 hook 一个重载 | 调用落到 SDK 实现，解引用假 handle | 逐个核对导入符号 vs `HLE_FORCE` 列表 |
| `COMPRESSIBLE` | 全黑但有文字，`first uploads 0` | 去掉 `tex_init_fill` 里的该条件 |
| 编码线程 | `Metal encoding runs on its own thread` | 必要时 `DM_NVN_ENC_THREAD=0` 对比 |

### 画面尺寸相关

| 陷阱 | 现象 | 解法 |
|---|---|---|
| **iOS `fit_16_9`** | 改了 viewport，全屏没反应 | 也要改 view 层的 `game_rect`；看日志里 `canvas` 是否等于屏幕尺寸 |
| **`safeAreaInsets`** | 触屏控件离边缘太远 | 用 `corner`（只扣 50%）而不是 `safe`（扣满） |
| 黑边分不清哪层 | — | `canvas == 屏幕尺寸` → 渲染问题；`canvas < 屏幕` → 布局问题 |

### 构建缓存相关

| 陷阱 | 现象 | 解法 |
|---|---|---|
| **derived data 缓存** | 改了 host 代码，app 行为没变 | `rm -rf <build>/xcode-derived-data` 再 archive |
| 改完源码立刻 archive | 打进旧代码 | 同上；验证方法是 `strings <app>/DmIOS \| grep <新加的日志字符串>` |

---

## 附录：Cross Rays 的完整 profile

`nxnative/dm/games/010055700CEA8000/game.tsv`

```tsv
title_id        010055700CEA8000
program_id      010055700CEA8000
name            SD GUNDAM G GENERATION CROSS RAYS
modules         main subsdk0 sdk
romfs_marker    Data.bin
mem_reserve     0x100000000
mem_alias       0x10000000
mem_stack       0x10000000
app_pool        0xCD500000
mem_used        0x8000000        ← 修复 1
sys_resource    0x0
tex_flush_upload  on              ← 试过，非必需
tex_dirty_upload  on
present_fill    crop              ← 修复 4（全屏）
shader_groups   /=romfs
```

加上这些 host 改动：

- `dm/host/hle_fs.c`：`ReadFile` 重载（修复 2）
- `dm/gfx/nvn/nvn_mtl.m`：`tex_init_fill` 的 `COMPRESSIBLE` 条件（修复 3）、`present_viewport` 的 fill 模式（修复 4）
- `dm/ios/Sources/front_ios.m`：`game_rect`（修复 4）
- `dm/ios/Sources/DmGamepad.m`：肩键布局（修复 5）
- `dm/games/game.py`：`present_fill` profile 键
- `dm/games/settings.tsv`：`DM_PRESENT_FILL` 启动器设置

---

## 检查清单：下一个游戏直接照着走

### 开干前

- [ ] 确认 64 位 ARM（`main.npdm` META+0xc bit 0）
- [ ] 确认 SDK 版本（6–20 是已验证区间）
- [ ] 确认图形 API（NVN / Vulkan / OpenGL）
- [ ] **找同 SDK / 同中间件的已跑通游戏**（省掉大量试错）

### 阶段 1-2

- [ ] `--survey-only` 产出 survey.md
- [ ] 检查 `main` 的 svc 数量（0 最好）
- [ ] 检查导入 vs hook 覆盖率（> 60%）
- [ ] shader 拆分通过率（接近 100%）
- [ ] **SPIR-V + MSL 手动验证**（不依赖 Xcode，最快筛问题）

### 阶段 3（bring-up）

- [ ] 用 Python `start_new_session` 启动（不要 `nohup &`）
- [ ] 每崩一次：反汇编 → 找 GOT 槽 → 对 hook 列表
- [ ] 加 env 控制的诊断探针（比反编译快 10 倍）
- [ ] `mem_used` 按模块大小 + 余量设
- [ ] 全黑有文字 → 查 `packaged textures: first uploads`
- [ ] 全黑无文字 → 查渲染目标 / present

### 阶段 4（打包）

- [ ] `--romfs separate`（大游戏）
- [ ] **`rm -rf xcode-derived-data`** 再 archive
- [ ] `DM_COPY_ROMFS=NO`（不是 `DM_COPY_GAME_RESOURCES=NO`）
- [ ] `strings <app>/DmIOS | grep <新日志>` 验证二进制
- [ ] `codesign -d --entitlements` 确认 `increased-memory-limit`
- [ ] 19 GB 数据用 **Finder** 拖（devicectl 会截断）

### 阶段 5（验证 + 打磨）

- [ ] 标题 → 菜单 → 战斗 → 存档 全走一遍
- [ ] 画面尺寸：`canvas` 是否等于屏幕？（不等 → 改 view 层）
- [ ] 触屏控件位置：`safeAreaInsets` 是否是元凶？
- [ ] 60 秒无崩溃、内存无持续增长
